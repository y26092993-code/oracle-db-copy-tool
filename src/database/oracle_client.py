"""Oracle データベース接続クライアント.

このモジュールは Oracle データベースへの接続を管理し、
CRUD操作のための基本的なメソッドを提供します。

Copyright (c) 2025 Oracle Connect Project.
"""

from typing import Any, Optional
import oracledb
from contextlib import contextmanager
import logging

# ロガー設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OracleClient:
    """Oracle データベース接続クライアントクラス.
    
    接続プーリングを使用して効率的なデータベース接続を管理します。
    """

    def __init__(
        self,
        user: str,
        password: str,
        host: str = "localhost",
        port: int = 1521,
        service_name: str = "jx",
        schema: Optional[str] = None,
        min_pool_size: int = 1,
        max_pool_size: int = 10,
        increment: int = 1,
    ):
        """OracleClient を初期化します.

        Args:
            user: データベースユーザー名
            password: データベースパスワード
            host: データベースホスト名
            port: データベースポート番号
            service_name: Oracle サービス名
            schema: スキーマ名（未指定の場合はuserと同じ）
            min_pool_size: 接続プールの最小サイズ
            max_pool_size: 接続プールの最大サイズ
            increment: 接続プールの増分
        """
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.service_name = service_name
        self.schema = schema or user
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.increment = increment
        self._pool: Optional[oracledb.ConnectionPool] = None
        self._current_schema: Optional[str] = None

    def _get_dsn(self) -> str:
        """DSN (Data Source Name) を生成します.

        Returns:
            str: Oracle接続用のDSN文字列
        """
        return f"{self.host}:{self.port}/{self.service_name}"

    def create_pool(self) -> None:
        """接続プールを作成します."""
        if self._pool is None:
            try:
                self._pool = oracledb.create_pool(
                    user=self.user,
                    password=self.password,
                    dsn=self._get_dsn(),
                    min=self.min_pool_size,
                    max=self.max_pool_size,
                    increment=self.increment,
                )
                logger.info(f"接続プールを作成しました: {self._get_dsn()}")
            except oracledb.Error as e:
                logger.error(f"接続プールの作成に失敗しました: {e}")
                raise

    def close_pool(self) -> None:
        """接続プールをクローズします."""
        if self._pool is not None:
            try:
                self._pool.close()
                self._pool = None
                logger.info("接続プールをクローズしました")
            except oracledb.Error as e:
                logger.error(f"接続プールのクローズに失敗しました: {e}")
                raise

    @contextmanager
    def get_connection(self, schema: Optional[str] = None):
        """コンテキストマネージャーとして接続を取得します.

        Args:
            schema: 使用するスキーマ名（指定しない場合はデフォルトスキーマ）

        Yields:
            oracledb.Connection: データベース接続オブジェクト
        """
        if self._pool is None:
            self.create_pool()

        connection = None
        try:
            connection = self._pool.acquire()
            logger.debug("データベース接続を取得しました")
            
            # スキーマの設定
            target_schema = schema or self.schema
            if target_schema and target_schema.upper() != self.user.upper():
                cursor = connection.cursor()
                cursor.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {target_schema}")
                cursor.close()
                self._current_schema = target_schema
                logger.debug(f"スキーマを {target_schema} に設定しました")
            
            yield connection
        except oracledb.Error as e:
            logger.error(f"データベース接続エラー: {e}")
            raise
        finally:
            if connection:
                connection.close()
                logger.debug("データベース接続をクローズしました")

    def execute_query(
        self, query: str, params: Optional[dict] = None, schema: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """SELECT クエリを実行して結果を返します.

        Args:
            query: 実行するSQLクエリ
            params: バインド変数のディクショナリ
            schema: 使用するスキーマ名

        Returns:
            list[dict[str, Any]]: クエリ結果のリスト
        """
        with self.get_connection(schema) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, params or {})
                columns = [col[0] for col in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                logger.info(f"クエリを実行しました: {len(results)}件の結果")
                return results
            except oracledb.Error as e:
                logger.error(f"クエリ実行エラー: {e}")
                raise
            finally:
                cursor.close()

    def execute_dml(
        self, query: str, params: Optional[dict] = None, commit: bool = True, schema: Optional[str] = None
    ) -> int:
        """INSERT/UPDATE/DELETE クエリを実行します.

        Args:
            query: 実行するSQLクエリ
            params: バインド変数のディクショナリ
            commit: True の場合、自動的にコミットします
            schema: 使用するスキーマ名

        Returns:
            int: 影響を受けた行数
        """
        with self.get_connection(schema) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, params or {})
                rowcount = cursor.rowcount
                if commit:
                    conn.commit()
                    logger.info(f"DMLを実行してコミットしました: {rowcount}行")
                else:
                    logger.info(f"DMLを実行しました: {rowcount}行（コミット保留）")
                return rowcount
            except oracledb.Error as e:
                if commit:
                    conn.rollback()
                    logger.error(f"DML実行エラー（ロールバック済み）: {e}")
                else:
                    logger.error(f"DML実行エラー: {e}")
                raise
            finally:
                cursor.close()

    def execute_many(
        self, query: str, params_list: list[dict], commit: bool = True, schema: Optional[str] = None
    ) -> int:
        """バッチ処理でDMLクエリを実行します.

        Args:
            query: 実行するSQLクエリ
            params_list: バインド変数のディクショナリのリスト
            commit: True の場合、自動的にコミットします
            schema: 使用するスキーマ名

        Returns:
            int: 影響を受けた総行数
        """
        with self.get_connection(schema) as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(query, params_list)
                rowcount = cursor.rowcount
                if commit:
                    conn.commit()
                    logger.info(f"バッチDMLを実行してコミットしました: {rowcount}行")
                else:
                    logger.info(f"バッチDMLを実行しました: {rowcount}行（コミット保留）")
                return rowcount
            except oracledb.Error as e:
                if commit:
                    conn.rollback()
                    logger.error(f"バッチDML実行エラー（ロールバック済み）: {e}")
                else:
                    logger.error(f"バッチDML実行エラー: {e}")
                raise
            finally:
                cursor.close()

    def get_current_schema(self) -> str:
        """現在のスキーマを取得します.

        Returns:
            str: 現在のスキーマ名
        """
        try:
            result = self.execute_query("SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') as schema FROM dual")
            if result:
                return result[0]['SCHEMA']
            return self.schema
        except Exception as e:
            logger.error(f"スキーマ取得エラー: {e}")
            return self.schema

    def set_schema(self, schema: str) -> None:
        """デフォルトスキーマを変更します.

        Args:
            schema: 設定するスキーマ名
        """
        self.schema = schema
        logger.info(f"デフォルトスキーマを {schema} に変更しました")

    def test_connection(self) -> bool:
        """データベース接続をテストします.

        Returns:
            bool: 接続成功の場合 True
        """
        try:
            result = self.execute_query("SELECT * FROM dual")
            if result:
                logger.info("接続テストが成功しました")
                return True
            return False
        except Exception as e:
            logger.error(f"接続テスト失敗: {e}")
            return False

    def __enter__(self):
        """コンテキストマネージャーのエントリーポイント."""
        self.create_pool()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャーの終了処理."""
        self.close_pool()
