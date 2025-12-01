"""複数データベース接続管理モジュール.

複数のOracleデータベースへの接続を一元管理し、
データベースやスキーマを切り替えて使用できます。
"""

from typing import Dict, Optional
import logging
from src.database.oracle_client import OracleClient
from src.config.database_config import DatabaseConfig

logger = logging.getLogger(__name__)


class ConnectionManager:
    """複数データベース接続を管理するクラス.
    
    複数のOracleデータベース接続を管理し、名前でアクセスできるようにします。
    """

    def __init__(self):
        """ConnectionManagerを初期化します."""
        self._clients: Dict[str, OracleClient] = {}
        self._configs: Dict[str, DatabaseConfig] = {}
        self._active_db: Optional[str] = None

    def add_database(self, config: DatabaseConfig) -> None:
        """データベース接続設定を追加します.

        Args:
            config: データベース設定
        """
        if config.name in self._clients:
            logger.warning(f"データベース '{config.name}' は既に存在します。上書きします。")
            self._clients[config.name].close_pool()

        client = OracleClient(
            user=config.user,
            password=config.password,
            host=config.host,
            port=config.port,
            service_name=config.service_name,
            schema=config.schema,
            min_pool_size=config.min_pool_size,
            max_pool_size=config.max_pool_size,
            increment=config.increment,
        )
        
        self._clients[config.name] = client
        self._configs[config.name] = config
        
        if self._active_db is None:
            self._active_db = config.name
        
        logger.info(f"データベース '{config.name}' を追加しました")

    def load_from_yaml(self, config_path: str) -> None:
        """YAMLファイルから全てのデータベース設定を読み込みます.

        Args:
            config_path: 設定ファイルのパス
        """
        configs = DatabaseConfig.load_all_from_yaml(config_path)
        for config in configs.values():
            self.add_database(config)
        logger.info(f"{len(configs)}件のデータベース設定を読み込みました")

    def get_client(self, db_name: Optional[str] = None) -> OracleClient:
        """指定されたデータベースのクライアントを取得します.

        Args:
            db_name: データベース名（省略時はアクティブなデータベース）

        Returns:
            OracleClient: データベースクライアント

        Raises:
            ValueError: 指定されたデータベースが存在しない場合
        """
        name = db_name or self._active_db
        if name is None:
            raise ValueError("データベースが設定されていません")
        
        if name not in self._clients:
            raise ValueError(f"データベース '{name}' が見つかりません")
        
        return self._clients[name]

    def switch_database(self, db_name: str) -> None:
        """アクティブなデータベースを切り替えます.

        Args:
            db_name: 切り替え先のデータベース名

        Raises:
            ValueError: 指定されたデータベースが存在しない場合
        """
        if db_name not in self._clients:
            raise ValueError(f"データベース '{db_name}' が見つかりません")
        
        self._active_db = db_name
        logger.info(f"アクティブデータベースを '{db_name}' に切り替えました")

    def get_active_database(self) -> Optional[str]:
        """現在アクティブなデータベース名を取得します.

        Returns:
            Optional[str]: アクティブなデータベース名
        """
        return self._active_db

    def list_databases(self) -> list[str]:
        """登録されている全てのデータベース名を取得します.

        Returns:
            list[str]: データベース名のリスト
        """
        return list(self._clients.keys())

    def get_database_info(self, db_name: Optional[str] = None) -> dict:
        """データベースの接続情報を取得します.

        Args:
            db_name: データベース名（省略時はアクティブなデータベース）

        Returns:
            dict: データベース接続情報
        """
        name = db_name or self._active_db
        if name is None or name not in self._configs:
            raise ValueError(f"データベース '{name}' が見つかりません")
        
        return self._configs[name].to_dict()

    def test_all_connections(self) -> Dict[str, bool]:
        """全てのデータベース接続をテストします.

        Returns:
            Dict[str, bool]: データベース名と接続結果のマップ
        """
        results = {}
        for db_name, client in self._clients.items():
            try:
                results[db_name] = client.test_connection()
            except Exception as e:
                logger.error(f"データベース '{db_name}' の接続テスト失敗: {e}")
                results[db_name] = False
        
        return results

    def close_all(self) -> None:
        """全てのデータベース接続をクローズします."""
        for db_name, client in self._clients.items():
            try:
                client.close_pool()
                logger.info(f"データベース '{db_name}' の接続をクローズしました")
            except Exception as e:
                logger.error(f"データベース '{db_name}' のクローズ中にエラー: {e}")
        
        self._clients.clear()
        self._configs.clear()
        self._active_db = None

    def __enter__(self):
        """コンテキストマネージャーのエントリーポイント."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャーの終了処理."""
        self.close_all()
