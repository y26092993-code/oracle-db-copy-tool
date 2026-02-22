"""ワイルドカードフィルタのテストスクリプト（Oracle形式）."""

import fnmatch
from typing import List


def oracle_pattern_to_fnmatch(pattern: str) -> str:
    """Oracle形式のパターンをfnmatch形式に変換。
    
    Args:
        pattern: Oracle形式のパターン（%, _）
        
    Returns:
        fnmatch形式のパターン（*, ?）
    """
    return pattern.replace('%', '*').replace('_', '?')


def test_wildcard_filter():
    """ワイルドカードフィルタのテスト。"""
    
    # テスト用のオブジェクト名リスト
    object_names = [
        "USER_TABLE1",
        "USER_TABLE2",
        "CUSTOMER_DATA",
        "ORDER_MASTER",
        "ORDER_DETAIL",
        "TEMP_TABLE1",
        "TEMP_TABLE2",
        "TEST_PROCEDURE",
        "PROD_VIEW1",
        "BACKUP_TABLE",
    ]
    
    print("=" * 60)
    print("ワイルドカードフィルタテスト（Oracle LIKE 形式）")
    print("=" * 60)
    print(f"\nテスト対象オブジェクト: {len(object_names)} 件")
    for name in object_names:
        print(f"  - {name}")
    
    # テストケース（Oracle形式）
    test_cases = [
        (["USER_%"], "USER_で始まる"),
        (["%_TABLE%"], "_TABLEを含む"),
        (["ORDER_%"], "ORDER_で始まる"),
        (["%_MASTER", "%_DETAIL"], "_MASTERまたは_DETAILで終わる"),
        (["TEMP_%", "TEST_%"], "TEMP_またはTEST_で始まる"),
        (["PROD_%", "BACKUP_%"], "PROD_またはBACKUP_で始まる"),
        (["%VIEW%"], "VIEWを含む"),
    ]
    
    for patterns, description in test_cases:
        print(f"\n{'=' * 60}")
        print(f"パターン（Oracle形式）: {', '.join(patterns)}")
        print(f"説明: {description}")
        print("-" * 60)
        
        matched = []
        for name in object_names:
            for pattern in patterns:
                # Oracle形式をfnmatch形式に変換
                fnmatch_pattern = oracle_pattern_to_fnmatch(pattern)
                if fnmatch.fnmatch(name.upper(), fnmatch_pattern.upper()):
                    matched.append(name)
                    break
        
        print(f"マッチ数: {len(matched)} 件")
        for name in matched:
            print(f"  ✓ {name}")
        
        if not matched:
            print("  (マッチなし)")
    
    print(f"\n{'=' * 60}")
    print("テスト完了")
    print("=" * 60)


if __name__ == "__main__":
    test_wildcard_filter()
