"""Oracle接続アプリケーションのサンプル.

データベース接続のテストとCRUD操作のデモンストレーション。
"""

import sys
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.oracle_client import OracleClient
from src.config.database_config import DatabaseConfig


def test_connection_example():
    """接続テストの例."""
    print("=" * 60)
    print("Oracle 接続テスト")
    print("=" * 60)

    # 設定ファイルから読み込み（環境変数でも可）
    config_path = project_root / "config" / "config.yaml"
    
    try:
        if config_path.exists():
            config = DatabaseConfig.from_yaml(str(config_path))
            print(f"設定ファイルから読み込み: {config_path}")
        else:
            config = DatabaseConfig.from_env()
            print("環境変数から読み込み")

        print(f"接続情報: {config.to_dict()}")

        # クライアント作成と接続テスト
        with OracleClient(
            user=config.user,
            password=config.password,
            host=config.host,
            port=config.port,
            service_name=config.service_name,
            min_pool_size=config.min_pool_size,
            max_pool_size=config.max_pool_size,
            increment=config.increment,
        ) as client:
            if client.test_connection():
                print("✓ 接続成功!")
                return client
            else:
                print("✗ 接続失敗")
                return None

    except Exception as e:
        print(f"✗ エラー: {e}")
        return None


def select_example(client: OracleClient):
    """SELECT クエリの例."""
    print("\n" + "=" * 60)
    print("SELECT クエリの例")
    print("=" * 60)

    try:
        # DUAL テーブルからの基本的なSELECT
        query = "SELECT SYSDATE as current_date, USER as current_user FROM dual"
        results = client.execute_query(query)

        print("\n実行したクエリ:")
        print(query)
        print("\n結果:")
        for row in results:
            print(row)

        # パラメータ付きクエリの例（テーブルが存在する場合）
        print("\n--- パラメータ付きクエリの例 ---")
        param_query = """
            SELECT table_name, tablespace_name 
            FROM user_tables 
            WHERE table_name LIKE :prefix || '%'
            ORDER BY table_name
        """
        param_results = client.execute_query(
            param_query, {"prefix": "JXT"}
        )

        print(f"\n実行したクエリ: table_name LIKE 'JXT%'")
        print(f"結果: {len(param_results)}件のテーブル")
        for row in param_results[:5]:  # 最初の5件のみ表示
            print(f"  - {row['TABLE_NAME']} ({row['TABLESPACE_NAME']})")
        if len(param_results) > 5:
            print(f"  ... 他 {len(param_results) - 5}件")

    except Exception as e:
        print(f"✗ エラー: {e}")


def insert_example(client: OracleClient):
    """INSERT クエリの例（テストテーブルを使用）."""
    print("\n" + "=" * 60)
    print("INSERT クエリの例")
    print("=" * 60)

    try:
        # テストテーブルを作成
        print("テストテーブルを作成中...")
        create_table_query = """
            CREATE TABLE test_table (
                id NUMBER PRIMARY KEY,
                name VARCHAR2(100),
                created_date DATE DEFAULT SYSDATE
            )
        """
        
        try:
            client.execute_dml(create_table_query)
            print("✓ テストテーブルを作成しました")
        except Exception as e:
            if "ORA-00955" in str(e):  # テーブルが既に存在
                print("✓ テストテーブルは既に存在します")
            else:
                raise

        # データを挿入
        print("\nデータを挿入中...")
        insert_query = """
            INSERT INTO test_table (id, name) 
            VALUES (:id, :name)
        """
        rowcount = client.execute_dml(
            insert_query, {"id": 1, "name": "テストデータ1"}
        )
        print(f"✓ {rowcount}行を挿入しました")

        # バッチインサートの例
        print("\nバッチインサート中...")
        batch_data = [
            {"id": 2, "name": "テストデータ2"},
            {"id": 3, "name": "テストデータ3"},
            {"id": 4, "name": "テストデータ4"},
        ]
        rowcount = client.execute_many(insert_query, batch_data)
        print(f"✓ {rowcount}行をバッチ挿入しました")

        # 挿入したデータを確認
        print("\n挿入したデータを確認:")
        results = client.execute_query("SELECT * FROM test_table ORDER BY id")
        for row in results:
            print(f"  ID: {row['ID']}, NAME: {row['NAME']}, DATE: {row['CREATED_DATE']}")

    except Exception as e:
        print(f"✗ エラー: {e}")


def update_example(client: OracleClient):
    """UPDATE クエリの例."""
    print("\n" + "=" * 60)
    print("UPDATE クエリの例")
    print("=" * 60)

    try:
        update_query = """
            UPDATE test_table 
            SET name = :new_name 
            WHERE id = :id
        """
        rowcount = client.execute_dml(
            update_query, {"new_name": "更新されたデータ", "id": 1}
        )
        print(f"✓ {rowcount}行を更新しました")

        # 更新結果を確認
        results = client.execute_query(
            "SELECT * FROM test_table WHERE id = :id", {"id": 1}
        )
        print("\n更新後のデータ:")
        for row in results:
            print(f"  ID: {row['ID']}, NAME: {row['NAME']}")

    except Exception as e:
        print(f"✗ エラー: {e}")


def delete_example(client: OracleClient):
    """DELETE クエリの例."""
    print("\n" + "=" * 60)
    print("DELETE クエリの例")
    print("=" * 60)

    try:
        delete_query = "DELETE FROM test_table WHERE id = :id"
        rowcount = client.execute_dml(delete_query, {"id": 4})
        print(f"✓ {rowcount}行を削除しました")

        # 削除後のデータを確認
        results = client.execute_query("SELECT COUNT(*) as cnt FROM test_table")
        print(f"\n残りのレコード数: {results[0]['CNT']}件")

    except Exception as e:
        print(f"✗ エラー: {e}")


def cleanup_example(client: OracleClient):
    """テストテーブルをクリーンアップ."""
    print("\n" + "=" * 60)
    print("クリーンアップ")
    print("=" * 60)

    try:
        drop_query = "DROP TABLE test_table"
        client.execute_dml(drop_query)
        print("✓ テストテーブルを削除しました")
    except Exception as e:
        print(f"✗ エラー: {e}")


def main():
    """メイン処理."""
    print("\n" + "=" * 60)
    print("Oracle Connect サンプルアプリケーション")
    print("=" * 60)

    # 接続テスト
    client = test_connection_example()
    
    if client is None:
        print("\n接続できませんでした。")
        print("\n確認事項:")
        print("1. Oracleデータベースが起動しているか")
        print("2. config/config.yaml の設定が正しいか")
        print("3. 環境変数が正しく設定されているか")
        return

    try:
        # SELECT の例
        select_example(client)

        # ユーザーに確認
        print("\n" + "=" * 60)
        response = input("\nCRUD操作のデモを実行しますか？ (y/n): ")
        
        if response.lower() == "y":
            # INSERT の例
            insert_example(client)

            # UPDATE の例
            update_example(client)

            # DELETE の例
            delete_example(client)

            # クリーンアップ
            response = input("\nテストテーブルを削除しますか？ (y/n): ")
            if response.lower() == "y":
                cleanup_example(client)

    except KeyboardInterrupt:
        print("\n\n処理を中断しました")
    except Exception as e:
        print(f"\n✗ 予期しないエラー: {e}")
    finally:
        print("\n" + "=" * 60)
        print("アプリケーション終了")
        print("=" * 60)


if __name__ == "__main__":
    main()
