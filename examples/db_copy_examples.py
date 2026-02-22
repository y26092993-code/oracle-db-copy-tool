"""Oracle DB オブジェクトコピーツールの使用例."""

import oracledb
from src.utils.tnsnames_parser import TnsNamesParser
from src.database.object_manager import DatabaseObjectManager, ObjectType
from src.database.object_copier import ObjectCopier


def example1_list_tns_entries():
    """例1: tnsnames.oraのエントリ一覧を表示."""
    print("\n=== 例1: TNSエントリ一覧 ===")
    
    parser = TnsNamesParser()  # 自動検索
    # または明示的にパスを指定:
    # parser = TnsNamesParser("C:/oracle/network/admin/tnsnames.ora")
    
    entries = parser.get_entries()
    
    for name, entry in entries.items():
        print(f"{name}: {entry}")


def example2_compare_databases():
    """例2: 2つのデータベースを比較."""
    print("\n=== 例2: データベース比較 ===")
    
    # tnsnames.oraから接続情報を取得
    parser = TnsNamesParser()
    entries = parser.get_entries()
    
    source_entry = entries['DEV']
    target_entry = entries['TEST']
    
    # 接続
    source_conn = oracledb.connect(
        user='scott',
        password='tiger',
        dsn=f"{source_entry.host}:{source_entry.port}/{source_entry.service_name}",
        encoding="UTF-8",
        nencoding="UTF-8"
    )
    
    target_conn = oracledb.connect(
        user='scott',
        password='tiger',
        dsn=f"{target_entry.host}:{target_entry.port}/{target_entry.service_name}",
        encoding="UTF-8",
        nencoding="UTF-8"
    )
    
    try:
        # ObjectCopierを使用して比較
        copier = ObjectCopier(source_conn, target_conn)
        
        # ストアドプロシージャとファンクションを比較
        comparison = copier.compare_databases([
            ObjectType.PROCEDURE,
            ObjectType.FUNCTION
        ])
        
        print(f"ソースのみ: {len(comparison['only_source'])} 件")
        for obj in comparison['only_source']:
            print(f"  + {obj}")
        
        print(f"\nターゲットのみ: {len(comparison['only_target'])} 件")
        for obj in comparison['only_target']:
            print(f"  - {obj}")
        
        print(f"\n共通: {len(comparison['common'])} 件")
    
    finally:
        source_conn.close()
        target_conn.close()


def example3_copy_procedures():
    """例3: ストアドプロシージャをコピー."""
    print("\n=== 例3: ストアドプロシージャのコピー ===")
    
    # tnsnames.oraから接続情報を取得
    parser = TnsNamesParser()
    entries = parser.get_entries()
    
    source_entry = entries['DEV']
    target_entry = entries['TEST']
    
    # 接続
    source_conn = oracledb.connect(
        user='scott',
        password='tiger',
        dsn=f"{source_entry.host}:{source_entry.port}/{source_entry.service_name}",
        encoding="UTF-8",
        nencoding="UTF-8"
    )
    
    target_conn = oracledb.connect(
        user='scott',
        password='tiger',
        dsn=f"{target_entry.host}:{target_entry.port}/{target_entry.service_name}",
        encoding="UTF-8",
        nencoding="UTF-8"
    )
    
    try:
        # ObjectCopierを使用してコピー
        copier = ObjectCopier(source_conn, target_conn)
        
        # ストアドプロシージャをコピー（DROP付き）
        results = copier.copy_objects(
            object_types=[ObjectType.PROCEDURE],
            drop_before_create=True
        )
        
        # レポートを表示
        report = copier.generate_copy_report(results)
        print(report)
    
    finally:
        source_conn.close()
        target_conn.close()


def example4_copy_specific_objects():
    """例4: 特定のオブジェクトのみコピー."""
    print("\n=== 例4: 特定のオブジェクトのコピー ===")
    
    parser = TnsNamesParser()
    entries = parser.get_entries()
    
    source_entry = entries['DEV']
    target_entry = entries['TEST']
    
    source_conn = oracledb.connect(
        user='scott',
        password='tiger',
        dsn=f"{source_entry.host}:{source_entry.port}/{source_entry.service_name}",
        encoding="UTF-8",
        nencoding="UTF-8"
    )
    
    target_conn = oracledb.connect(
        user='scott',
        password='tiger',
        dsn=f"{target_entry.host}:{target_entry.port}/{target_entry.service_name}",
        encoding="UTF-8",
        nencoding="UTF-8"
    )
    
    try:
        copier = ObjectCopier(source_conn, target_conn)
        
        # 特定のストアドプロシージャのみをコピー
        results = copier.copy_objects(
            object_types=[ObjectType.PROCEDURE, ObjectType.FUNCTION],
            object_names=['MY_PROC1', 'MY_FUNC1'],  # コピーするオブジェクトを指定
            drop_before_create=True
        )
        
        # 結果を表示
        for result in results:
            print(result)
    
    finally:
        source_conn.close()
        target_conn.close()


def example5_copy_all_objects():
    """例5: 全てのオブジェクトをコピー."""
    print("\n=== 例5: 全オブジェクトのコピー ===")
    
    parser = TnsNamesParser()
    entries = parser.get_entries()
    
    source_entry = entries['DEV']
    target_entry = entries['TEST']
    
    source_conn = oracledb.connect(
        user='scott',
        password='tiger',
        dsn=f"{source_entry.host}:{source_entry.port}/{source_entry.service_name}",
        encoding="UTF-8",
        nencoding="UTF-8"
    )
    
    target_conn = oracledb.connect(
        user='scott',
        password='tiger',
        dsn=f"{target_entry.host}:{target_entry.port}/{target_entry.service_name}",
        encoding="UTF-8",
        nencoding="UTF-8"
    )
    
    try:
        copier = ObjectCopier(source_conn, target_conn)
        
        # 全てのオブジェクトタイプをコピー
        results = copier.copy_objects(
            object_types=[
                ObjectType.TABLE,
                ObjectType.VIEW,
                ObjectType.PACKAGE,
                ObjectType.PACKAGE_BODY,
                ObjectType.FUNCTION,
                ObjectType.PROCEDURE,
                ObjectType.TRIGGER
            ],
            drop_before_create=True,
            cascade=True  # テーブル削除時にCASCADEを使用
        )
        
        # レポートを表示
        report = copier.generate_copy_report(results)
        print(report)
        
        # レポートをファイルに保存
        with open('copy_report.txt', 'w', encoding='utf-8') as f:
            f.write(report)
        print("\nレポートを copy_report.txt に保存しました。")
    
    finally:
        source_conn.close()
        target_conn.close()


def example6_get_object_ddl():
    """例6: オブジェクトのDDLを取得."""
    print("\n=== 例6: オブジェクトDDLの取得 ===")
    
    parser = TnsNamesParser()
    entries = parser.get_entries()
    entry = entries['DEV']
    
    conn = oracledb.connect(
        user='scott',
        password='tiger',
        dsn=f"{entry.host}:{entry.port}/{entry.service_name}",
        encoding="UTF-8",
        nencoding="UTF-8"
    )
    
    try:
        manager = DatabaseObjectManager(conn)
        
        # ストアドプロシージャのDDLを取得
        ddl = manager.get_object_ddl(
            ObjectType.PROCEDURE,
            'MY_PROCEDURE',
            'SCOTT'
        )
        
        if ddl:
            print(f"DDL:\n{ddl}")
        else:
            print("DDLの取得に失敗しました")
    
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 80)
    print("Oracle DB オブジェクトコピーツール - 使用例")
    print("=" * 80)
    
    # 実行したい例をコメント解除してください
    
    # example1_list_tns_entries()
    # example2_compare_databases()
    # example3_copy_procedures()
    # example4_copy_specific_objects()
    # example5_copy_all_objects()
    # example6_get_object_ddl()
    
    print("\n使用例の実行を有効にするには、該当する関数のコメントを解除してください。")
