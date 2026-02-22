# Image Entry GUI - 軽量化版の使用方法

## 軽量化の成果

- **削減前**: 257.75 MB
- **削減後**: 43.18 MB
- **削減率**: **83.2%**

## 軽量化の方法

### 1. 除外したモジュール
以下の大容量モジュールをEXEから除外しました：

- **機械学習/科学計算**: torch, tensorflow, numpy, scipy
- **OCRエンジン**: pytesseract, easyocr, paddleocr, yomitoku
- **画像処理**: PIL/Pillow
- **データ分析**: pandas, openpyxl
- **Web関連**: requests, urllib3

### 2. 最適化設定
- バイトコード最適化レベル2
- シンボル情報の削除（strip=True）
- UPX圧縮の有効化

## 使用方法

### 基本機能（EXE単体で動作）
- ✅ 画像ファイルの読み込み・表示
- ✅ ファイル一覧の管理
- ✅ 宛名番号、帳票No、年度などの入力
- ✅ CSV出力
- ✅ 納税義務者情報の検索（CSVファイルが必要）

### OCR機能を使用する場合
OCR機能を使用するには、実行環境にOCRエンジンをインストールする必要があります：

#### オプション1: Tesseract OCR（推奨）
```bash
# 1. Tesseractをインストール
# https://github.com/UB-Mannheim/tesseract/wiki からダウンロード

# 2. Pythonラッパーをインストール
pip install pytesseract Pillow
```

#### オプション2: EasyOCR
```bash
pip install easyocr Pillow
```

#### オプション3: PaddleOCR
```bash
pip install paddleocr Pillow
```

#### オプション4: Yomitoku
```bash
pip install yomitoku Pillow
```

## 配布方法

### シンプル配布（推奨）
```
配布フォルダ/
├── ImageEntryGUI.exe       （43MB）
├── 納税義務者情報.csv      （検索機能用）
└── README.txt              （使い方説明）
```

### OCR付き配布
OCR機能も使いたい場合：
1. EXEファイル
2. 納税義務者情報.csv
3. OCRセットアップ手順書
4. Python環境（または仮想環境）
5. requirements_ocr.txt

## トラブルシューティング

### Q: OCRボタンを押してもエラーが出る
**A**: OCRエンジンがインストールされていません。上記の「OCR機能を使用する場合」を参照してください。

### Q: 「モジュールが見つかりません」エラー
**A**: 必要なPythonパッケージをインストール：
```bash
pip install PySide6
```

### Q: EXEが起動しない
**A**: Visual C++ 再頒布可能パッケージをインストール：
https://aka.ms/vs/17/release/vc_redist.x64.exe

### Q: もっと軽量化できますか？
**A**: 可能です。以下の方法があります：

1. **PySide6の最小化**: 使用していないQtモジュールをさらに除外
2. **Python埋め込み版**: Pythonランタイムを最小限に
3. **7-Zip圧縮**: EXEファイル自体を圧縮して配布

## さらなる軽量化

もしさらに小さくしたい場合は、以下の方法があります：

### 1. カスタムPython環境
```bash
# 軽量なPython環境を作成
python -m venv .venv_minimal --without-pip
.venv_minimal\Scripts\activate
# 最小限のパッケージのみインストール
python -m ensurepip
pip install PySide6
```

### 2. Qtの最小化
ImageEntryGUI.spec を編集して、使用していないQtモジュールを除外：
```python
excludes += [
    'PySide6.QtNetwork',
    'PySide6.QtSql',
    'PySide6.QtXml',
    # ...
]
```

### 3. 2段階配布
- **ランチャー**: 5MB程度の小さなEXE（Python不要）
- **メインロジック**: Pythonスクリプト（.pycファイル）

## パフォーマンス

軽量化によるパフォーマンスへの影響：
- ✅ 起動速度: ほぼ同じ
- ✅ 動作速度: 変化なし
- ⚠️ OCR初回実行: モデルダウンロードが必要（EasyOCR使用時）

## まとめ

### 軽量化版の利点
- ✅ ファイルサイズが83%削減
- ✅ 配布が容易
- ✅ 基本機能は完全動作
- ✅ 必要に応じてOCR追加可能

### 注意点
- ⚠️ OCR機能は外部依存
- ⚠️ 初回使用時に追加セットアップが必要（OCR使用の場合）
- ℹ️ Python環境があればOCRもすぐ使える

## 技術詳細

### ビルド設定
```python
# ImageEntryGUI.spec
excludes = [
    'torch', 'tensorflow', 'numpy', 'scipy',
    'matplotlib', 'pandas', 'openpyxl',
    'pytesseract', 'easyocr', 'paddleocr', 'yomitoku',
    'PIL', 'Pillow',
    # ... 他多数
]

exe = EXE(
    # ...
    strip=True,      # シンボル削除
    upx=True,        # UPX圧縮
    optimize=2,      # 最適化レベル
)
```

### 動的ロード
OCRエンジンは実行時に動的にインポート：
```python
try:
    pytesseract = __import__('pytesseract')
except ImportError:
    # OCR利用不可を通知
    pass
```

これにより、EXEサイズを大幅に削減しながら、機能の柔軟性を維持しています。
