"""複数データベース/スキーマ切り替えのサンプルアプリケーション.

複数のデータベースへの接続と、スキーマの切り替え方法を示します。
"""

import sys
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection_manager import ConnectionManager
from src.database.oracle_client import OracleClient
from src.config.database_config import DatabaseConfig


def demo_multiple_databases():
    """複数データベース接続のデモ."""
    print("=" * 60)
    print("複数データベース接続のデモ")
    print("=" * 60)

    config_path = project_root / "config" / "config.yaml"

    # ConnectionManagerを使用
    with ConnectionManager() as manager:
        # 設定ファイルから全てのデータベースを読み込み
        manager.load_from_yaml(str(config_path))

        # 登録されているデータベース一覧
        print("\n登録されているデータベース:")
        for db_name in manager.list_databases():
            info = manager.get_database_info(db_name)
            print(f"  - {db_name}: {info['user']}@{info['host']}:{info['port']}/{info['service_name']} (スキーマ: {info['schema']})")

        # 全データベース接続テスト
        print("\n全データベース接続テスト:")
        results = manager.test_all_connections()
        for db_name, success in results.items():
            status = "✓ 成功" if success else "✗ 失敗"
            print(f"  {db_name}: {status}")

        # アクティブなデータベースを表示
        print(f"\nアクティブなデータベース: {manager.get_active_database()}")

        # デフォルトDBでクエリ実行
        try:
            client = manager.get_client()
            print("\n--- デフォルトDBでクエリ実行 ---")
            result = client.execute_query("SELECT USER, SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') as schema FROM dual")
            print(f"ユーザー: {result[0]['USER']}")
            print(f"スキーマ: {result[0]['SCHEMA']}")
        except Exception as e:
            print(f"エラー: {e}")

        # データベースを切り替え
        print("\n--- データベース切り替え (dev) ---")
        try:
            manager.switch_database("dev")
            client = manager.get_client()
            result = client.execute_query("SELECT USER, SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') as schema FROM dual")
            print(f"ユーザー: {result[0]['USER']}")
            print(f"スキーマ: {result[0]['SCHEMA']}")
        except Exception as e:
            print(f"エラー: {e}")


def demo_schema_switching():
    """スキーマ切り替えのデモ."""
    print("\n" + "=" * 60)
    print("スキーマ切り替えのデモ")
    print("=" * 60)

    config_path = project_root / "config" / "config.yaml"

    try:
        # 単一のデータベース接続を使用
        config = DatabaseConfig.from_yaml(str(config_path), "default")
        
        with OracleClient(
            user=config.user,
            password=config.password,
            host=config.host,
            port=config.port,
            service_name=config.service_name,
            schema=config.schema,
            min_pool_size=config.min_pool_size,
            max_pool_size=config.max_pool_size,
        ) as client:
            # デフォルトスキーマで実行
            print("\n--- デフォルトスキーマで実行 ---")
            result = client.execute_query("SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') as schema FROM dual")
            print(f"現在のスキーマ: {result[0]['SCHEMA']}")

            # スキーマを切り替えて実行（クエリごとに指定）
            print("\n--- スキーマを切り替えて実行 (SYS) ---")
            try:
                result = client.execute_query(
                    "SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') as schema FROM dual",
                    schema="SYS"
                )
                print(f"切り替え後のスキーマ: {result[0]['SCHEMA']}")
            except Exception as e:
                print(f"エラー（権限不足の可能性）: {e}")

            # デフォルトスキーマを変更
            print("\n--- デフォルトスキーマを変更 ---")
            client.set_schema("PUBLIC")
            result = client.execute_query("SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') as schema FROM dual")
            print(f"変更後のデフォルトスキーマ: {result[0]['SCHEMA']}")

            # スキーマ内のテーブル一覧を取得
            print("\n--- 現在のスキーマのテーブル一覧 ---")
            tables = client.execute_query(
                "SELECT table_name FROM user_tables ORDER BY table_name"
            )
            if tables:
                print(f"テーブル数: {len(tables)}件")
                for i, table in enumerate(tables[:5], 1):
                    print(f"  {i}. {table['TABLE_NAME']}")
                if len(tables) > 5:
                    print(f"  ... 他 {len(tables) - 5}件")
            else:
                print("テーブルが見つかりません")

    except Exception as e:
        print(f"エラー: {e}")


def demo_cross_schema_query():
    """異なるスキーマ間でのクエリ実行デモ."""
    print("\n" + "=" * 60)
    print("異なるスキーマ間でのクエリ実行デモ")
    print("=" * 60)

    config_path = project_root / "config" / "config.yaml"

    try:
        config = DatabaseConfig.from_yaml(str(config_path), "default")
        
        with OracleClient(
            user=config.user,
            password=config.password,
            host=config.host,
            port=config.port,
            service_name=config.service_name,
            schema=config.schema,
        ) as client:
            print("\n--- 自スキーマと他スキーマのテーブルにアクセス ---")
            
            # 自スキーマのテーブル
            print("\n1. 自スキーマ (user_tables)")
            result = client.execute_query(
                "SELECT COUNT(*) as cnt FROM user_tables"
            )
            print(f"   テーブル数: {result[0]['CNT']}件")

            # 全スキーマのテーブル（権限があれば）
            print("\n2. 全スキーマ (all_tables)")
            try:
                result = client.execute_query(
                    """
                    SELECT owner, COUNT(*) as cnt 
                    FROM all_tables 
                    WHERE owner IN ('JX', 'JX_DEV', 'JX_TEST', 'PUBLIC')
                    GROUP BY owner 
                    ORDER BY owner
                    """
                )
                for row in result:
                    print(f"   {row['OWNER']}: {row['CNT']}件")
            except Exception as e:
                print(f"   エラー: {e}")

            # スキーマ名を明示的に指定してテーブルにアクセス
            print("\n3. スキーマ名を明示的に指定")
            print("   例: SELECT * FROM jx.some_table")
            print("   このようにスキーマ名をプレフィックスとして使用できます")

    except Exception as e:
        print(f"エラー: {e}")


def interactive_demo():
    """対話的なデモ."""
    print("\n" + "=" * 60)
    print("対話的なデモ")
    print("=" * 60)

    config_path = project_root / "config" / "config.yaml"

    with ConnectionManager() as manager:
        manager.load_from_yaml(str(config_path))

        while True:
            print("\n" + "-" * 60)
            print("選択してください:")
            print("1. データベース一覧表示")
            print("2. データベースを切り替え")
            print("3. 現在のデータベース情報表示")
            print("4. SQLクエリを実行")
            print("5. スキーマを変更")
            print("0. 終了")
            print("-" * 60)

            choice = input("選択 (0-5): ").strip()

            if choice == "0":
                print("終了します")
                break

            elif choice == "1":
                print("\n登録されているデータベース:")
                for db_name in manager.list_databases():
                    active = " (アクティブ)" if db_name == manager.get_active_database() else ""
                    info = manager.get_database_info(db_name)
                    print(f"  {db_name}{active}: {info['user']}@{info['host']}:{info['port']}/{info['service_name']}")

            elif choice == "2":
                db_list = manager.list_databases()
                print(f"\n利用可能なデータベース: {', '.join(db_list)}")
                db_name = input("データベース名: ").strip()
                try:
                    manager.switch_database(db_name)
                    print(f"✓ '{db_name}' に切り替えました")
                except ValueError as e:
                    print(f"✗ エラー: {e}")

            elif choice == "3":
                try:
                    active = manager.get_active_database()
                    info = manager.get_database_info()
                    client = manager.get_client()
                    
                    print(f"\n現在のデータベース: {active}")
                    print(f"接続情報: {info}")
                    
                    result = client.execute_query(
                        "SELECT USER, SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') as schema FROM dual"
                    )
                    print(f"ユーザー: {result[0]['USER']}")
                    print(f"スキーマ: {result[0]['SCHEMA']}")
                except Exception as e:
                    print(f"✗ エラー: {e}")

            elif choice == "4":
                query = input("\nSQLクエリを入力 (例: SELECT * FROM dual): ").strip()
                if query:
                    try:
                        client = manager.get_client()
                        results = client.execute_query(query)
                        print(f"\n結果: {len(results)}件")
                        for i, row in enumerate(results[:10], 1):
                            print(f"  {i}. {row}")
                        if len(results) > 10:
                            print(f"  ... 他 {len(results) - 10}件")
                    except Exception as e:
                        print(f"✗ エラー: {e}")

            elif choice == "5":
                schema = input("\nスキーマ名を入力: ").strip()
                if schema:
                    try:
                        client = manager.get_client()
                        client.set_schema(schema)
                        print(f"✓ デフォルトスキーマを '{schema}' に変更しました")
                    except Exception as e:
                        print(f"✗ エラー: {e}")

            else:
                print("無効な選択です")


def main():
    """メイン処理."""
    print("\n" + "=" * 60)
    print("複数データベース/スキーマ切り替えサンプル")
    print("=" * 60)

    # 各デモを実行
    demo_multiple_databases()
    demo_schema_switching()
    demo_cross_schema_query()

    # 対話的なデモを実行するか確認
    response = input("\n対話的なデモを実行しますか？ (y/n): ").strip().lower()
    if response == "y":
        interactive_demo()

    print("\n" + "=" * 60)
    print("サンプルアプリケーション終了")
    print("=" * 60)


if __name__ == "__main__":
    main()
