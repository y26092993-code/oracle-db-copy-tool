"""Oracle データベース接続とオブジェクト管理モジュール.

Oracle DBのオブジェクトを管理し、別のDBへコピーする機能を提供。
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Tuple
import logging
import fnmatch

try:
    import oracledb
except ImportError:
    try:
        import cx_Oracle as oracledb
    except ImportError:
        raise ImportError("oracledb または cx_Oracle のインストールが必要です")


class ObjectType(Enum):
    """データベースオブジェクトの種類。"""
    TABLE = "TABLE"
    VIEW = "VIEW"
    PROCEDURE = "PROCEDURE"
    FUNCTION = "FUNCTION"
    PACKAGE = "PACKAGE"
    PACKAGE_BODY = "PACKAGE BODY"
    TRIGGER = "TRIGGER"
    SEQUENCE = "SEQUENCE"
    SYNONYM = "SYNONYM"
    TYPE = "TYPE"


@dataclass
class ConnectionConfig:
    """データベース接続設定。"""
    host: str
    port: int
    service: str
    username: str
    password: str
    
    def get_dsn(self) -> str:
        """DSN文字列を取得。
        
        Returns:
            DSN文字列
        """
        return f"{self.host}:{self.port}/{self.service}"


@dataclass
class DatabaseObject:
    """データベースオブジェクト。"""
    name: str
    object_type: ObjectType
    owner: str
    status: Optional[str] = None
    created: Optional[str] = None
    last_ddl_time: Optional[str] = None


@dataclass
class CopyResult:
    """コピー結果。"""
    object_name: str
    object_type: ObjectType
    success: bool
    error_message: Optional[str] = None


class DatabaseManager:
    """データベース接続とオブジェクト管理クラス。"""
    
    def __init__(
        self,
        source_config: ConnectionConfig,
        target_config: ConnectionConfig
    ):
        """初期化。
        
        Args:
            source_config: ソースDB接続設定
            target_config: ターゲットDB接続設定
        """
        self.source_config = source_config
        self.target_config = target_config
        self.source_conn: Optional[oracledb.Connection] = None
        self.target_conn: Optional[oracledb.Connection] = None
        
        logging.info("DatabaseManager初期化完了")
    
    def connect_source(self) -> oracledb.Connection:
        """ソースDBに接続。
        
        Returns:
            接続オブジェクト
        """
        if not self.source_conn:
            logging.info(f"ソースDB接続: {self.source_config.get_dsn()}")
            self.source_conn = oracledb.connect(
                user=self.source_config.username,
                password=self.source_config.password,
                dsn=self.source_config.get_dsn(),
                encoding="UTF-8",
                nencoding="UTF-8"
            )
            logging.info("ソースDB接続成功")
        return self.source_conn
    
    def connect_target(self) -> oracledb.Connection:
        """ターゲットDBに接続。
        
        Returns:
            接続オブジェクト
        """
        if not self.target_conn:
            logging.info(f"ターゲットDB接続: {self.target_config.get_dsn()}")
            self.target_conn = oracledb.connect(
                user=self.target_config.username,
                password=self.target_config.password,
                dsn=self.target_config.get_dsn(),
                encoding="UTF-8",
                nencoding="UTF-8"
            )
            logging.info("ターゲットDB接続成功")
        return self.target_conn
    
    def disconnect(self) -> None:
        """両方のDB接続を切断。"""
        if self.source_conn:
            self.source_conn.close()
            self.source_conn = None
            logging.info("ソースDB切断")
        
        if self.target_conn:
            self.target_conn.close()
            self.target_conn = None
            logging.info("ターゲットDB切断")
    
    def test_connections(self) -> bool:
        """接続テストを実行。
        
        Returns:
            両方の接続が成功した場合True
        """
        try:
            # ソース接続テスト
            source_conn = self.connect_source()
            cursor = source_conn.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.fetchone()
            cursor.close()
            logging.info("ソースDB接続テスト成功")
            
            # ターゲット接続テスト
            target_conn = self.connect_target()
            cursor = target_conn.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.fetchone()
            cursor.close()
            logging.info("ターゲットDB接続テスト成功")
            
            return True
        
        except Exception as e:
            logging.error(f"接続テスト失敗: {e}", exc_info=True)
            return False
    
    def filter_objects_by_pattern(
        self,
        objects: List[DatabaseObject],
        patterns: Optional[List[str]] = None
    ) -> List[DatabaseObject]:
        """ワイルドカードパターンでオブジェクトをフィルタリング。
        
        Args:
            objects: オブジェクト一覧
            patterns: ワイルドカードパターンのリスト
                     Noneまたは空リストの場合は全件返す
            
        Returns:
            フィルタリングされたオブジェクト一覧
        
        Examples:
            patterns = ["USER_%", "%_TMP"]
            → USER_で始まるまたは_TMPで終わるオブジェクト
        
        Note:
            Oracleスタイルのワイルドカードを使用:
            - % : 任意の文字列（0文字以上）
            - _ : 任意の1文字
        """
        if not patterns:
            return objects
        
        filtered = []
        for obj in objects:
            # いずれかのパターンにマッチすれば含める
            for pattern in patterns:
                # Oracleスタイル(%, _)をfnmatchスタイル(*, ?)に変換
                fnmatch_pattern = pattern.replace('%', '*').replace('_', '?')
                if fnmatch.fnmatch(obj.name.upper(), fnmatch_pattern.upper()):
                    filtered.append(obj)
                    break
        
        logging.info(f"フィルタ適用: {len(objects)} 件 → {len(filtered)} 件")
        return filtered
    
    def get_source_objects(
        self,
        object_types: List[ObjectType],
        name_patterns: Optional[List[str]] = None
    ) -> List[DatabaseObject]:
        """ソースDBのオブジェクト一覧を取得。
        
        Args:
            object_types: 取得するオブジェクトタイプ
            name_patterns: オブジェクト名のフィルタパターン
                          例: ["USER_%", "%_TMP"]
            
        Returns:
            オブジェクト一覧
        """
        conn = self.connect_source()
        cursor = conn.cursor()
        
        objects: List[DatabaseObject] = []
        
        for obj_type in object_types:
            try:
                # オブジェクトタイプに応じたクエリ
                if obj_type == ObjectType.PACKAGE:
                    # パッケージとパッケージボディを両方取得
                    query = """
                        SELECT object_name, object_type, owner, status,
                               TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS') as created,
                               TO_CHAR(last_ddl_time, 'YYYY-MM-DD HH24:MI:SS') as last_ddl_time
                        FROM user_objects
                        WHERE object_type IN ('PACKAGE', 'PACKAGE BODY')
                        ORDER BY object_name, object_type
                    """
                else:
                    query = f"""
                        SELECT object_name, object_type, owner, status,
                               TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS') as created,
                               TO_CHAR(last_ddl_time, 'YYYY-MM-DD HH24:MI:SS') as last_ddl_time
                        FROM user_objects
                        WHERE object_type = '{obj_type.value}'
                        ORDER BY object_name
                    """
                
                cursor.execute(query)
                
                for row in cursor:
                    obj_name, obj_type_str, owner, status, created, last_ddl_time = row
                    
                    # object_typeの変換
                    try:
                        obj_type_enum = ObjectType(obj_type_str)
                    except ValueError:
                        obj_type_enum = obj_type
                    
                    objects.append(DatabaseObject(
                        name=obj_name,
                        object_type=obj_type_enum,
                        owner=owner,
                        status=status,
                        created=created,
                        last_ddl_time=last_ddl_time
                    ))
                
                logging.info(f"{obj_type.value}: {len([o for o in objects if o.object_type == obj_type])} 件")
            
            except Exception as e:
                logging.error(f"{obj_type.value}の取得エラー: {e}")
        
        cursor.close()
        
        # フィルタ適用
        if name_patterns:
            objects = self.filter_objects_by_pattern(objects, name_patterns)
        
        return objects
    
    def get_object_ddl(
        self,
        object_name: str,
        object_type: ObjectType
    ) -> Optional[str]:
        """オブジェクトのDDLを取得。
        
        Args:
            object_name: オブジェクト名
            object_type: オブジェクトタイプ
            
        Returns:
            DDL文字列、取得失敗時はNone
        """
        conn = self.connect_source()
        cursor = conn.cursor()
        
        try:
            if object_type in [ObjectType.PROCEDURE, ObjectType.FUNCTION, ObjectType.PACKAGE, ObjectType.TRIGGER]:
                # ストアドプログラムの場合、user_sourceから取得
                query = """
                    SELECT text
                    FROM user_source
                    WHERE name = :name
                    AND type = :type
                    ORDER BY line
                """
                cursor.execute(query, {
                    'name': object_name.upper(),
                    'type': object_type.value
                })
                
                lines = [row[0] for row in cursor]
                
                if lines:
                    ddl = "".join(lines)
                    return f"CREATE OR REPLACE {ddl}"
                else:
                    return None
            
            elif object_type == ObjectType.VIEW:
                # ビューの場合
                query = """
                    SELECT text
                    FROM user_views
                    WHERE view_name = :name
                """
                cursor.execute(query, {'name': object_name.upper()})
                row = cursor.fetchone()
                
                if row:
                    return f"CREATE OR REPLACE VIEW {object_name} AS\n{row[0]}"
                else:
                    return None
            
            elif object_type == ObjectType.SEQUENCE:
                # シーケンスの場合
                query = """
                    SELECT min_value, max_value, increment_by, cycle_flag, cache_size
                    FROM user_sequences
                    WHERE sequence_name = :name
                """
                cursor.execute(query, {'name': object_name.upper()})
                row = cursor.fetchone()
                
                if row:
                    min_val, max_val, incr, cycle, cache = row
                    ddl = f"CREATE SEQUENCE {object_name}\n"
                    ddl += f"  MINVALUE {min_val}\n"
                    ddl += f"  MAXVALUE {max_val}\n"
                    ddl += f"  INCREMENT BY {incr}\n"
                    ddl += f"  {'CYCLE' if cycle == 'Y' else 'NOCYCLE'}\n"
                    ddl += f"  CACHE {cache}"
                    return ddl
                else:
                    return None
            
            else:
                # その他の場合はDBMS_METADATAを使用
                query = """
                    SELECT DBMS_METADATA.GET_DDL(:type, :name) FROM DUAL
                """
                cursor.execute(query, {
                    'type': object_type.value,
                    'name': object_name.upper()
                })
                row = cursor.fetchone()
                
                if row and row[0]:
                    # CLOBを文字列に変換
                    ddl = row[0].read() if hasattr(row[0], 'read') else str(row[0])
                    return ddl
                else:
                    return None
        
        except Exception as e:
            logging.error(f"DDL取得エラー ({object_name}): {e}", exc_info=True)
            return None
        
        finally:
            cursor.close()
    
    def drop_object(
        self,
        object_name: str,
        object_type: ObjectType
    ) -> Tuple[bool, Optional[str]]:
        """ターゲットDBのオブジェクトを削除。
        
        Args:
            object_name: オブジェクト名
            object_type: オブジェクトタイプ
            
        Returns:
            (成功フラグ, エラーメッセージ)
        """
        conn = self.connect_target()
        cursor = conn.cursor()
        
        try:
            # DROP文を作成
            if object_type == ObjectType.PACKAGE:
                # パッケージの場合、BODYを先に削除
                drop_sql = f"DROP PACKAGE {object_name}"
            else:
                drop_sql = f"DROP {object_type.value} {object_name}"
            
            logging.info(f"実行: {drop_sql}")
            cursor.execute(drop_sql)
            conn.commit()
            
            return True, None
        
        except Exception as e:
            # オブジェクトが存在しない場合のエラーは無視
            error_str = str(e).upper()
            if "ORA-04043" in error_str or "NOT EXIST" in error_str:
                logging.info(f"{object_name} は存在しません（スキップ）")
                return True, None
            else:
                logging.error(f"DROP失敗 ({object_name}): {e}")
                return False, str(e)
        
        finally:
            cursor.close()
    
    def create_object(
        self,
        ddl: str,
        object_name: str
    ) -> Tuple[bool, Optional[str]]:
        """ターゲットDBにオブジェクトを作成。
        
        Args:
            ddl: DDL文
            object_name: オブジェクト名（ログ用）
            
        Returns:
            (成功フラグ, エラーメッセージ)
        """
        conn = self.connect_target()
        cursor = conn.cursor()
        
        try:
            logging.info(f"オブジェクト作成: {object_name}")
            cursor.execute(ddl)
            conn.commit()
            
            return True, None
        
        except Exception as e:
            logging.error(f"CREATE失敗 ({object_name}): {e}")
            return False, str(e)
        
        finally:
            cursor.close()
    
    def copy_objects(
        self,
        object_types: List[ObjectType],
        drop_before_create: bool = True,
        skip_errors: bool = True,
        name_patterns: Optional[List[str]] = None,
        specific_objects: Optional[List[DatabaseObject]] = None
    ) -> List[CopyResult]:
        """オブジェクトをコピー。
        
        Args:
            object_types: コピーするオブジェクトタイプ
            drop_before_create: 作成前に削除するか
            skip_errors: エラー発生時も続行するか
            name_patterns: オブジェクト名のフィルタパターン
            specific_objects: 特定のオブジェクトリスト（指定された場合はこれを使用）
            
        Returns:
            コピー結果のリスト
        """
        results: List[CopyResult] = []
        
        # オブジェクト一覧取得（specific_objectsが指定されていない場合）
        if specific_objects is not None:
            objects = specific_objects
        else:
            objects = self.get_source_objects(object_types, name_patterns)
        
        logging.info(f"コピー対象: {len(objects)} 件")
        
        for obj in objects:
            logging.info(f"処理中: {obj.object_type.value} {obj.name}")
            
            try:
                # DDL取得
                ddl = self.get_object_ddl(obj.name, obj.object_type)
                
                if not ddl:
                    results.append(CopyResult(
                        object_name=obj.name,
                        object_type=obj.object_type,
                        success=False,
                        error_message="DDLの取得に失敗しました"
                    ))
                    
                    if not skip_errors:
                        break
                    continue
                
                # DROP実行（オプション）
                if drop_before_create:
                    success, error = self.drop_object(obj.name, obj.object_type)
                    if not success and not skip_errors:
                        results.append(CopyResult(
                            object_name=obj.name,
                            object_type=obj.object_type,
                            success=False,
                            error_message=f"DROP失敗: {error}"
                        ))
                        break
                
                # CREATE実行
                success, error = self.create_object(ddl, obj.name)
                
                results.append(CopyResult(
                    object_name=obj.name,
                    object_type=obj.object_type,
                    success=success,
                    error_message=error
                ))
                
                if not success and not skip_errors:
                    break
            
            except Exception as e:
                error_msg = f"予期しないエラー: {e}"
                logging.error(error_msg, exc_info=True)
                
                results.append(CopyResult(
                    object_name=obj.name,
                    object_type=obj.object_type,
                    success=False,
                    error_message=error_msg
                ))
                
                if not skip_errors:
                    break
        
        return results
    
    def __del__(self):
        """デストラクタ。"""
        self.disconnect()
