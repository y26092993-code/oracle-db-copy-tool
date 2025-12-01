"""データベース設定管理モジュール.

環境変数や設定ファイルからデータベース接続情報を管理します。
複数のデータベース/スキーマ設定に対応しています。
"""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import yaml
from pathlib import Path


@dataclass
class DatabaseConfig:
    """データベース接続設定クラス."""

    user: str
    password: str
    host: str = "localhost"
    port: int = 1521
    service_name: str = "jx"
    schema: Optional[str] = None  # スキーマ名（指定しない場合はユーザー名と同じ）
    min_pool_size: int = 1
    max_pool_size: int = 10
    increment: int = 1
    name: str = "default"  # 接続設定の識別名

    @classmethod
    def from_env(cls, prefix: str = "ORACLE") -> "DatabaseConfig":
        """環境変数から設定を読み込みます.

        Args:
            prefix: 環境変数のプレフィックス（例: "ORACLE", "ORACLE_DEV"）

        Returns:
            DatabaseConfig: データベース設定オブジェクト
        """
        return cls(
            user=os.getenv(f"{prefix}_USER", "jx"),
            password=os.getenv(f"{prefix}_PASSWORD", "jx"),
            host=os.getenv(f"{prefix}_HOST", "localhost"),
            port=int(os.getenv(f"{prefix}_PORT", "1521")),
            service_name=os.getenv(f"{prefix}_SERVICE_NAME", "jx"),
            schema=os.getenv(f"{prefix}_SCHEMA"),
            min_pool_size=int(os.getenv(f"{prefix}_MIN_POOL_SIZE", "1")),
            max_pool_size=int(os.getenv(f"{prefix}_MAX_POOL_SIZE", "10")),
            increment=int(os.getenv(f"{prefix}_INCREMENT", "1")),
            name=prefix.lower(),
        )

    @classmethod
    def from_yaml(cls, config_path: str, db_name: str = "default") -> "DatabaseConfig":
        """YAMLファイルから設定を読み込みます.

        Args:
            config_path: 設定ファイルのパス
            db_name: 読み込むデータベース設定名（databases内のキー）

        Returns:
            DatabaseConfig: データベース設定オブジェクト
        """
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        # 複数データベース設定の場合
        if "databases" in config_data:
            db_config = config_data["databases"].get(db_name, {})
            if not db_config:
                raise ValueError(f"データベース設定 '{db_name}' が見つかりません")
        # 単一データベース設定の場合（後方互換性）
        else:
            db_config = config_data.get("database", {})

        return cls(
            user=db_config.get("user", "jx"),
            password=db_config.get("password", "jx"),
            host=db_config.get("host", "localhost"),
            port=db_config.get("port", 1521),
            service_name=db_config.get("service_name", "jx"),
            schema=db_config.get("schema"),
            min_pool_size=db_config.get("min_pool_size", 1),
            max_pool_size=db_config.get("max_pool_size", 10),
            increment=db_config.get("increment", 1),
            name=db_name,
        )

    @classmethod
    def load_all_from_yaml(cls, config_path: str) -> Dict[str, "DatabaseConfig"]:
        """YAMLファイルから全てのデータベース設定を読み込みます.

        Args:
            config_path: 設定ファイルのパス

        Returns:
            Dict[str, DatabaseConfig]: データベース名をキーとした設定の辞書
        """
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        configs = {}
        if "databases" in config_data:
            for db_name in config_data["databases"].keys():
                configs[db_name] = cls.from_yaml(config_path, db_name)
        else:
            # 単一設定の場合
            configs["default"] = cls.from_yaml(config_path)

        return configs

    def to_dict(self) -> dict:
        """設定を辞書形式に変換します.

        Returns:
            dict: 設定の辞書
        """
        return {
            "name": self.name,
            "user": self.user,
            "password": "***",  # セキュリティのためマスク
            "host": self.host,
            "port": self.port,
            "service_name": self.service_name,
            "schema": self.schema or self.user,
            "min_pool_size": self.min_pool_size,
            "max_pool_size": self.max_pool_size,
            "increment": self.increment,
        }
