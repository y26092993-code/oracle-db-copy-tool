# CSV to Excel 変換ツール

PySide6を使用したGUIベースのCSV→Excel変換アプリケーション

![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)
![PySide6](https://img.shields.io/badge/PySide6-6.6+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## 📋 概要

複数のCSVファイルをExcelファイルに簡単に変換できるデスクトップアプリケーションです。ドラッグ&ドロップで直感的に操作でき、様々な文字エンコーディングに対応しています。

## ✨ 主な機能

### 基本機能
- 🖱️ **ドラッグ&ドロップ対応** - CSVファイルを直接ドロップして追加
- 🌐 **多様なエンコーディング対応**
  - Shift_JIS (SJIS)
  - UTF-8 (BOM付き/BOM無し)
  - その他の文字コードも自動検出
- 📊 **3つの変換モード**
  - モードA: 1CSV → 1Excelファイル
  - モードB: 複数CSV → 1Excelファイル (各シート)
  - モードC: 複数CSV → 1Excelファイル (1シートにマージ)
- ⚙️ **ヘッダー設定** - CSVの1行目をヘッダーとして扱うか選択可能
- 📁 **柔軟な出力先** - デフォルトはCSVと同じフォルダ、変更も可能

### 高度な機能
- ⚡ **並列処理による高速変換** - 最大4つのファイルを同時処理
- 🔒 **ダブルクォーテーション処理** - すべての項目を文字列として扱う
- 🗑️ **空ファイル自動スキップ** - 空のCSVファイルは自動的に除外
- 📝 **シート名の最適化**
  - 31文字制限に自動対応
  - 使用できない文字の自動置換 (`\`, `/`, `*`, `?`, `[`, `]`, `:`)
  - 重複シート名の自動連番付与

## 🚀 インストール

### 必要要件
- Python 3.13以上
- pip

### セットアップ

1. リポジトリをクローン
```bash
git clone https://github.com/yourusername/oracleConnect.git
cd oracleConnect
```

2. 仮想環境を作成
```bash
python -m venv .venv
.venv\Scripts\activate
```

3. 依存パッケージをインストール
```bash
pip install -r requirements.txt
```

## 💻 使用方法

### Pythonスクリプトとして実行

```bash
python Conv_Csv_To_Excel.py
```

### EXEファイルの作成

最適化されたEXEファイルをビルド:
```bash
.\build_with_spec.bat
```

生成されるファイル: `dist\CsvToExcel.exe` (約66MB)

## 📖 使い方

1. **アプリケーションを起動**
2. **CSVファイルを追加**
   - ドラッグ&ドロップ、または「ファイルを選択」ボタン
3. **オプションを設定**
   - ヘッダー設定: 1行目をヘッダーとして扱うか選択
   - 変換モード: A/B/Cから選択
4. **出力先を確認/変更** (必要に応じて)
5. **「Excel変換を実行」をクリック**

### 変換モードの詳細

#### モードA: 1CSV → 1Excelファイル
各CSVファイルを個別のExcelファイルに変換します。
- `売上データ.csv` → `売上データ.xlsx`
- `顧客リスト.csv` → `顧客リスト.xlsx`

#### モードB: 複数CSV → 1Excel (各シート)
複数のCSVを1つのExcelファイルにまとめ、各CSVが別々のシートになります。
- 出力: `merged_sheets.xlsx`
  - シート1: 売上データ
  - シート2: 顧客リスト

#### モードC: 複数CSV → 1Excel (1シートにマージ)
複数のCSVを1つのシートに結合します。各行の先頭にファイル名が追加されます。
- 出力: `merged_single_sheet.xlsx`
  - 1シート内にすべてのデータ、各行にファイル名列あり

## 🏗️ プロジェクト構成

```
oracleConnect/
├── Conv_Csv_To_Excel.py          # メインアプリケーション
├── requirements.txt               # Python依存パッケージ
├── build_spec_optimized.spec     # PyInstaller設定(最適化版)
├── build_with_spec.bat           # EXEビルドスクリプト
├── build_exe.bat                 # 標準ビルドスクリプト
├── build_exe_simple.bat          # フォルダ形式ビルド
├── BUILD_README.md               # ビルド手順の詳細
└── README_CsvToExcel.md          # このファイル
```

## 🛠️ 技術スタック

- **GUI**: PySide6 (Qt6)
- **Excel生成**: openpyxl
- **データ処理**: pandas
- **エンコーディング検出**: chardet
- **並列処理**: concurrent.futures

## ⚡ パフォーマンス

### 並列処理による高速化
- モードA: **3-4倍高速** (ファイル数が多いほど効果大)
- モードB: **1.6-2倍高速**
- モードC: **1.6-2倍高速**

※10ファイル程度の場合の目安

## 📝 開発情報

### 開発環境のセットアップ

```bash
# 開発用パッケージを含めてインストール
pip install -r requirements.txt

# コードフォーマット
black Conv_Csv_To_Excel.py

# 型チェック
mypy Conv_Csv_To_Excel.py

# リンター
flake8 Conv_Csv_To_Excel.py
pylint Conv_Csv_To_Excel.py
```

### ビルド方法

詳細は `BUILD_README.md` を参照してください。

```bash
# 最適化ビルド (推奨)
.\build_with_spec.bat

# 標準ビルド
.\build_exe.bat

# フォルダ形式 (高速起動)
.\build_exe_simple.bat
```

## 🐛 既知の問題

- 非常に大きなCSVファイル(100MB以上)の場合、メモリ使用量が増加する可能性があります
- 一部のセキュリティソフトでEXEファイルが誤検知される場合があります

## 🤝 コントリビューション

プルリクエストを歓迎します！大きな変更の場合は、まずissueを開いて変更内容を議論してください。

## 📄 ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 👤 作成者

Your Name

## 🙏 謝辞

- PySide6チーム
- pandas開発者
- openpyxl開発者

---

⭐ このプロジェクトが役に立った場合は、スターをつけていただけると�励みになります！
