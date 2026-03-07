"""Oracle データベース接続とオブジェクト管理モジュール.

Oracle DBのオブジェクトを管理し、別のDBへコピーする機能を提供。
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Tuple, Callable, Any
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
        self.last_connection_error: Optional[str] = None
        
        logging.info("DatabaseManager初期化完了")

    def _format_connection_error(self, error: Exception) -> str:
        """接続エラーをユーザー向けメッセージに整形。"""
        error_text = str(error)

        if "DPY-3016" in error_text and "x509" in error_text:
            return (
                "DPY-3016: oracledb thin mode で cryptography.x509 の読み込みに失敗しました。\n"
                "対処方法:\n"
                "1. 仮想環境で `pip install -U cryptography pyinstaller` を実行\n"
                "2. `build` / `dist` を削除して再ビルド\n"
                "3. `pyinstaller db_copy_tool.spec` で exe を再生成"
            )

        return error_text

    def _create_connection(self, config: ConnectionConfig) -> oracledb.Connection:
        """ドライバ互換性を考慮してDB接続を作成。
        
        thin mode (デフォルト) では encoding パラメータは不要。
        thick mode の場合のみエンコーディングパラメータを追加。
        """
        connect_kwargs: Dict[str, Any] = {
            "user": config.username,
            "password": config.password,
            "dsn": config.get_dsn(),
        }

        # thick mode の場合のみエンコーディングパラメータを追加
        try:
            if hasattr(oracledb, 'is_thin_mode') and not oracledb.is_thin_mode():
                connect_kwargs['encoding'] = 'UTF-8'
                connect_kwargs['nencoding'] = 'UTF-8'
        except Exception:
            # is_thin_mode が使えない場合は安全のため追加を試みる
            pass

        try:
            return oracledb.connect(**connect_kwargs)
        except TypeError as exc:
            error_text = str(exc)
            if "unexpected keyword argument 'encoding'" in error_text or "unexpected keyword argument 'nencoding'" in error_text:
                logging.info("DBドライバが encoding/nencoding 未対応のため、標準設定で再接続します")
                connect_kwargs.pop("encoding", None)
                connect_kwargs.pop("nencoding", None)
                return oracledb.connect(**connect_kwargs)
            raise
    
    def connect_source(self) -> oracledb.Connection:
        """ソースDBに接続。
        
        Returns:
            接続オブジェクト
        """
        if not self.source_conn:
            logging.info(f"ソースDB接続: {self.source_config.get_dsn()}")
            self.source_conn = self._create_connection(self.source_config)
            logging.info("ソースDB接続成功")
        return self.source_conn
    
    def connect_target(self) -> oracledb.Connection:
        """ターゲットDBに接続。
        
        Returns:
            接続オブジェクト
        """
        if not self.target_conn:
            logging.info(f"ターゲットDB接続: {self.target_config.get_dsn()}")
            self.target_conn = self._create_connection(self.target_config)
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
        self.last_connection_error = None

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
            self.last_connection_error = self._format_connection_error(e)
            logging.error(f"接続テスト失敗: {self.last_connection_error}", exc_info=True)
            return False
