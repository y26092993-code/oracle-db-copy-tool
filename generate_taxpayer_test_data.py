#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
納税義務者情報テストデータ生成スクリプト

20万件の納税義務者情報CSVを生成します。
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

# 日本の姓・名のサンプル
LAST_NAMES = [
    '佐藤', '鈴木', '高橋', '田中', '伊藤', '渡辺', '山本', '中村', '小林', '加藤',
    '吉田', '山田', '佐々木', '山口', '松本', '井上', '木村', '林', '斎藤', '清水',
    '山崎', '森', '池田', '橋本', '阿部', '石川', '中島', '前田', '藤田', '小川',
    '後藤', '岡田', '長谷川', '村上', '近藤', '石井', '遠藤', '青木', '坂本', '斉藤',
    '福田', '太田', '西村', '藤井', '金子', '岡本', '中川', '中野', '原田', '竹内'
]

FIRST_NAMES_MALE = [
    '太郎', '次郎', '三郎', '健', '誠', '隆', '学', '博', '修', '明',
    '浩', '和也', '大輔', '拓也', '翔太', '健太', '翔', '大樹', '颯太', '蓮'
]

FIRST_NAMES_FEMALE = [
    '花子', '幸子', '恵子', '美香', '由美', '直美', '真由美', '陽子', '裕子', '智子',
    '美穂', '優子', '愛', '葵', '結衣', 'さくら', '美咲', '彩', '七海', '凜'
]

# 都道府県と市区町村
PREFECTURES = {
    '東京都': ['千代田区', '中央区', '港区', '新宿区', '文京区', '台東区', '墨田区', '江東区', '品川区', '目黒区',
              '大田区', '世田谷区', '渋谷区', '中野区', '杉並区', '豊島区', '北区', '荒川区', '板橋区', '練馬区'],
    '神奈川県': ['横浜市', '川崎市', '相模原市', '横須賀市', '平塚市', '鎌倉市', '藤沢市', '小田原市', '茅ヶ崎市', '厚木市'],
    '大阪府': ['大阪市', '堺市', '岸和田市', '豊中市', '池田市', '吹田市', '泉大津市', '高槻市', '貝塚市', '守口市'],
    '愛知県': ['名古屋市', '豊橋市', '岡崎市', '一宮市', '瀬戸市', '半田市', '春日井市', '豊川市', '津島市', '碧南市'],
    '北海道': ['札幌市', '函館市', '小樽市', '旭川市', '室蘭市', '釧路市', '帯広市', '北見市', '夕張市', '岩見沢市'],
    '福岡県': ['福岡市', '北九州市', '久留米市', '直方市', '飯塚市', '田川市', '柳川市', '八女市', '筑後市', '大川市'],
}

TOWNS = [
    '本町', '中央', '東', '西', '南', '北', '旭町', '緑町', '新町', '栄町',
    '幸町', '寿町', '宮前', '神田', '上野', '浅草', '銀座', '赤坂', '青山', '表参道'
]

def generate_kana(name: str) -> str:
    """簡易的な振り仮名生成（実際は固定マッピング）"""
    kana_map = {
        '佐藤': 'サトウ', '鈴木': 'スズキ', '高橋': 'タカハシ', '田中': 'タナカ', '伊藤': 'イトウ',
        '渡辺': 'ワタナベ', '山本': 'ヤマモト', '中村': 'ナカムラ', '小林': 'コバヤシ', '加藤': 'カトウ',
        '太郎': 'タロウ', '次郎': 'ジロウ', '花子': 'ハナコ', '健': 'タケシ', '誠': 'マコト',
        '美香': 'ミカ', '由美': 'ユミ', '直美': 'ナオミ', '愛': 'アイ', '葵': 'アオイ'
    }
    return kana_map.get(name, 'ナマエ')

def generate_birth_date() -> str:
    """ランダムな生年月日を生成（昭和30年〜平成20年）"""
    start_date = date(1955, 1, 1)  # 昭和30年
    end_date = date(2008, 12, 31)  # 平成20年
    
    days_between = (end_date - start_date).days
    random_days = random.randint(0, days_between)
    birth = start_date + timedelta(days=random_days)
    
    return birth.strftime('%Y%m%d')

def generate_postal_code() -> str:
    """ランダムな郵便番号を生成"""
    return f"{random.randint(100, 999):03d}-{random.randint(0, 9999):04d}"

def generate_address_number() -> str:
    """ランダムな番地号表記を生成"""
    patterns = [
        f"{random.randint(1, 30)}丁目{random.randint(1, 50)}番{random.randint(1, 30)}号",
        f"{random.randint(1, 500)}番地",
        f"{random.randint(1, 100)}-{random.randint(1, 50)}",
        f"{random.randint(1, 50)}-{random.randint(1, 30)}-{random.randint(1, 20)}",
    ]
    return random.choice(patterns)

def generate_addressee_number(index: int, year: int) -> str:
    """宛名番号を生成（年度ごとにユニーク）"""
    # 基本番号（6桁） + チェックデジット（1桁）
    base = (index % 999999) + 1
    base_str = f"{base:06d}"
    
    # チェックデジット計算（checkdeji2アルゴリズム）
    weights = [7, 6, 5, 4, 3, 2]
    digits = [int(d) for d in base_str]
    applied_weights = [weights[i % len(weights)] for i in range(len(digits))]
    weighted_sum = sum(d * w for d, w in zip(digits, applied_weights))
    remainder = weighted_sum % 11
    check_digit = 11 - remainder
    if remainder == 0 or check_digit == 11:
        check_digit = 1
    
    return base_str + str(check_digit)

def generate_test_data(num_records: int = 200000, output_path: str = 'CSV/納税義務者情報_テストデータ_20万件.csv'):
    """テストデータを生成"""
    print(f"納税義務者情報テストデータ生成開始: {num_records:,}件")
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 年度は2024年（令和6年）を中心に分散
    years = [2022, 2023, 2024, 2025, 2026]
    year_weights = [10, 20, 40, 20, 10]  # 2024年を中心に分布
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = [
            '市区町村コード',
            '課税年度',
            '宛名番号',
            '郵便番号',
            '住所_都道府県',
            '住所_市区郡町村名',
            '住所_町字',
            '住所_番地号表記',
            '住所_方書',
            '氏名（振り仮名）',
            '氏名',
            '生年月日'
        ]
        
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for i in range(num_records):
            # 進捗表示
            if (i + 1) % 10000 == 0:
                print(f"  生成中: {i+1:,} / {num_records:,} ({(i+1)/num_records*100:.1f}%)")
            
            # ランダムに都道府県と市区町村を選択
            prefecture = random.choice(list(PREFECTURES.keys()))
            city = random.choice(PREFECTURES[prefecture])
            town = random.choice(TOWNS)
            
            # 性別をランダムに決定
            is_male = random.random() > 0.5
            last_name = random.choice(LAST_NAMES)
            first_name = random.choice(FIRST_NAMES_MALE if is_male else FIRST_NAMES_FEMALE)
            full_name = last_name + first_name
            
            # 振り仮名
            last_kana = generate_kana(last_name)
            first_kana = generate_kana(first_name)
            full_kana = last_kana + ' ' + first_kana
            
            # 年度選択
            year = random.choices(years, weights=year_weights)[0]
            
            # 方書（10%の確率で付与）
            other_info = ''
            if random.random() < 0.1:
                other_info = random.choice([
                    'アパート101号室', 'マンション205号', '第一ビル3F', 
                    'コーポ202', 'ハイツA棟', 'メゾン1階'
                ])
            
            row = {
                '市区町村コード': f"{random.randint(10000, 99999):05d}",
                '課税年度': str(year),
                '宛名番号': generate_addressee_number(i, year),
                '郵便番号': generate_postal_code(),
                '住所_都道府県': prefecture,
                '住所_市区郡町村名': city,
                '住所_町字': town,
                '住所_番地号表記': generate_address_number(),
                '住所_方書': other_info,
                '氏名（振り仮名）': full_kana,
                '氏名': full_name,
                '生年月日': generate_birth_date()
            }
            
            writer.writerow(row)
    
    print(f"\n完了: {output_file} に {num_records:,}件のデータを生成しました")
    print(f"ファイルサイズ: {output_file.stat().st_size / (1024*1024):.2f} MB")

if __name__ == '__main__':
    # 20万件のテストデータを生成
    generate_test_data(200000)
    
    # 動作確認用に小規模データも生成
    print("\n動作確認用データ（1000件）も生成します...")
    generate_test_data(1000, 'CSV/納税義務者情報_テストデータ_1000件.csv')
