# ImageEntryGUI3 ビルド手順

## 概要
PythonスクリプトをWindows実行可能ファイル（.exe）に変換する手順です。

## 前提条件
- Python 3.13以上
- PyInstallerがインストール済み
- 仮想環境が有効化されていること

## ビルド手順

### 1. 仮想環境の有効化
```powershell
& C:\Users\hiyok\oracleConnect\.venv\Scripts\Activate.ps1
```

### 2. PyInstallerでビルド
```powershell
pyinstaller ImageEntryGUI3.spec --clean
```

### 3. ビルド完了
ビルドが成功すると、`dist`フォルダに以下の2つが生成されます：

#### ワンファイル版（推奨）
- **場所**: `dist\ImageEntryGUI3.exe`
- **サイズ**: 約50MB
- **特徴**: 単一の実行ファイル。起動は少し遅いが配布が簡単

#### ワンフォルダ版
- **場所**: `dist\ImageEntryGUI3\ImageEntryGUI3.exe`
- **特徴**: 実行ファイル + `_internal`フォルダ。起動が速い

## specファイルの説明

`ImageEntryGUI3.spec`には以下の最適化が含まれています：

### 除外モジュール
- **EasyOCR関連**: torch, torchvision, cv2, numpy（別配置版として除外）
- **PaddleOCR**: paddleocr, paddlepaddle
- **その他**: matplotlib, scipy, pandas, django, flask

### 含まれるモジュール
- **必須**: PySide6 (GUI), PIL (画像処理)
- **オプション**: pytesseract (OCR機能)

### バイトコード最適化
- `optimize=2`: 最高レベルの最適化
- `console=False`: コンソールウィンドウを非表示

## トラブルシューティング

### ビルドエラーが発生した場合
1. キャッシュをクリア:
   ```powershell
   pyinstaller ImageEntryGUI3.spec --clean
   ```

2. buildフォルダを削除:
   ```powershell
   Remove-Item -Path build -Recurse -Force
   Remove-Item -Path dist -Recurse -Force
   ```

### 実行時エラーが発生した場合
1. 警告ログを確認:
   ```
   build\ImageEntryGUI3\warn-ImageEntryGUI3.txt
   ```

2. デバッグモードでビルド:
   - specファイルの`debug=True`に変更
   - `console=True`に変更してコンソール出力を確認

## 配布方法

### 単独配布（推奨）
`dist\ImageEntryGUI3.exe`を配布

### フォルダ配布
`dist\ImageEntryGUI3\`フォルダ全体をZIP圧縮して配布

### 必要なファイル（実行時）
- 納税義務者情報CSV（オプション）
- 画像フォルダ
- 設定ファイルは自動生成されます

## 注意事項

### OCR機能について
- **Tesseract OCR**: 別途インストールが必要
- **EasyOCR**: 除外されています（サイズ削減のため）
- OCR機能を使用しない場合、pytesseractのインストールは不要

### ファイルサイズ
- ワンファイル版: 約50MB
- PySide6が大部分を占めます
- さらに削減するには不要なPySide6モジュールを除外

### セキュリティ
- Windows Defenderが誤検知する場合があります
- その場合は例外リストに追加してください

## ビルド情報
- **PyInstaller**: 6.17.0
- **Python**: 3.13.9
- **最終ビルド日**: 2026/01/20
