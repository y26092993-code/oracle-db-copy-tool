# Image Entry GUI OCR - EXE化手順

## 概要
`image_entry_gui3OCR.py` を実行可能なEXEファイルに変換する手順です。

## 前提条件

### 1. PyInstallerのインストール
```bash
# 仮想環境で実行
.venv\Scripts\activate
pip install pyinstaller
```

### 2. 必要なパッケージの確認
```bash
pip list | findstr "PySide6 pytesseract easyocr"
```

## ビルド方法

### 方法1: シンプルなビルド（推奨初回）
```bash
build_image_entry_gui.bat
```

このスクリプトは：
- 単一のEXEファイルを生成
- GUIアプリケーション（コンソールなし）
- 基本的な最適化を適用

### 方法2: Specファイル使用（カスタマイズ可能）
```bash
build_image_entry_with_spec.bat
```

このスクリプトは：
- `ImageEntryGUI.spec` を使用
- より細かい制御が可能
- 利用可能なOCRモジュールのみを含める

## 出力ファイル

ビルド成功後、以下の場所にEXEファイルが生成されます：
```
dist\ImageEntryGUI.exe
```

## 配布時の注意事項

### 1. 必要なファイル
EXEファイルと一緒に以下のファイルを配布してください：

- `納税義務者情報.csv` - 検索機能に必要（オプション）

### 2. OCRエンジン
各OCRエンジンは別途インストールが必要です：

#### Tesseract OCR
- ダウンロード: https://github.com/UB-Mannheim/tesseract/wiki
- インストール後、環境変数PATHに追加

#### EasyOCR
- EXEには含まれません
- 実行環境で `pip install easyocr` が必要

#### PaddleOCR
- EXEには含まれません
- 実行環境で `pip install paddleocr` が必要

#### Yomitoku
- EXEには含まれません
- 実行環境で `pip install yomitoku` が必要

### 3. 初回実行時
EasyOCRを使用する場合、初回実行時にモデルファイルがダウンロードされます（数百MB）。

## トラブルシューティング

### ビルドエラー: モジュールが見つからない
```bash
# 不足パッケージをインストール
pip install -r requirements.txt
```

### EXEサイズが大きい
`ImageEntryGUI.spec` を編集して不要なモジュールを除外：
```python
excludes = [
    'matplotlib',  # 使用していない場合は除外
    'scipy',
    # ... その他
]
```

### 実行時エラー: DLLが見つからない
Visual C++ 再頒布可能パッケージをインストール：
https://aka.ms/vs/17/release/vc_redist.x64.exe

### OCRが動作しない
1. OCRエンジンがインストールされているか確認
2. 環境変数PATHにTesseractのパスが含まれているか確認
3. コンソールモードでビルドして詳細なエラーを確認：
   ```
   # ImageEntryGUI.spec の console=False を console=True に変更
   ```

## ファイルサイズ削減のヒント

### 1. 仮想環境をクリーンに
```bash
# 新しい仮想環境を作成
python -m venv .venv_build
.venv_build\Scripts\activate
pip install PySide6 openpyxl pandas chardet
# 必要最小限のパッケージのみ
```

### 2. UPX圧縮（オプション）
```bash
# UPXをダウンロード: https://upx.github.io/
# ImageEntryGUI.spec で upx=True に変更
```

### 3. 不要なOCRエンジンを除外
使用しないOCRエンジンは `hiddenimports` から削除

## 推奨ビルド手順

1. 仮想環境をアクティベート
   ```bash
   .venv\Scripts\activate
   ```

2. PyInstallerがインストールされているか確認
   ```bash
   pip show pyinstaller
   ```

3. ビルド実行
   ```bash
   build_image_entry_with_spec.bat
   ```

4. テスト実行
   ```bash
   dist\ImageEntryGUI.exe
   ```

5. 配布用パッケージ作成
   ```
   MyApp/
   ├── ImageEntryGUI.exe
   ├── 納税義務者情報.csv
   └── README.txt（使用方法を記載）
   ```

## 参考情報

- PyInstaller公式ドキュメント: https://pyinstaller.org/
- PySide6ドキュメント: https://doc.qt.io/qtforpython/
