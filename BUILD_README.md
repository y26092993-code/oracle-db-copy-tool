# CSV to Excel 変換ツール - EXE化手順

## 概要
PythonアプリケーションをWindows実行可能ファイル(.exe)に変換する手順です。

## 前提条件
- Python仮想環境が有効化されていること
- 必要なパッケージがインストールされていること

## ビルド方法

### 方法1: 単一EXEファイル（推奨）
すべてが1つのEXEファイルにまとめられます。配布が簡単ですが、起動が少し遅くなります。

```batch
build_exe.bat
```

**出力場所**: `dist\CsvToExcel.exe`

### 方法2: フォルダ形式（高速）
複数ファイルで構成されます。起動が高速ですが、フォルダごと配布する必要があります。

```batch
build_exe_simple.bat
```

**出力場所**: `dist\CsvToExcel\CsvToExcel.exe`（フォルダごと配布）

## 手動ビルド（コマンドライン）

### 単一EXEファイル
```powershell
C:\Users\hiyok\oracleConnect\.venv\Scripts\pyinstaller.exe --name="CsvToExcel" --onefile --windowed Conv_Csv_To_Excel.py
```

### フォルダ形式
```powershell
C:\Users\hiyok\oracleConnect\.venv\Scripts\pyinstaller.exe --name="CsvToExcel" --onedir --windowed Conv_Csv_To_Excel.py
```

## PyInstallerオプション説明

- `--name="CsvToExcel"`: 出力ファイル名を指定
- `--onefile`: 単一の実行可能ファイルを作成
- `--onedir`: フォルダ形式で作成（複数ファイル）
- `--windowed`: コンソールウィンドウを表示しない（GUIアプリ用）
- `--icon=icon.ico`: アイコンファイルを指定（オプション）

## トラブルシューティング

### エラー: ModuleNotFoundError
必要なモジュールが見つからない場合:
```batch
pip install PySide6 openpyxl pandas chardet pyinstaller
```

### EXEが起動しない
1. コンソール付きでビルドして確認:
   ```powershell
   C:\Users\hiyok\oracleConnect\.venv\Scripts\pyinstaller.exe --name="CsvToExcel" --onefile Conv_Csv_To_Excel.py
   ```
   （`--windowed`を外す）

2. ビルドファイルをクリーンアップ:
   ```batch
   rd /s /q build dist
   del Conv_Csv_To_Excel.spec
   ```

### ファイルサイズが大きい
フォルダ形式（`--onedir`）を使用すると、起動は高速になりますが、
配布時はフォルダごと渡す必要があります。

## 配布方法

### 単一EXEファイルの場合
`dist\CsvToExcel.exe` を配布するだけでOK

### フォルダ形式の場合
`dist\CsvToExcel\` フォルダ全体を配布してください

## ファイルサイズ削減のヒント

### 通常ビルドとの比較
- **通常ビルド**: 約 65-70 MB
- **最適化ビルド**: 約 50-60 MB（不要モジュール除外）
- **フォルダ形式**: 合計 100-150 MB（起動は高速）

### 最適化ビルドを使用
```batch
build_with_spec.bat
```
または
```powershell
C:\Users\hiyok\oracleConnect\.venv\Scripts\pyinstaller.exe build_spec_optimized.spec
```

最適化specファイルは以下を除外します:
- matplotlib, scipy（グラフ描画ライブラリ）
- IPython, jupyter（対話型環境）
- tkinter（別のGUIライブラリ）
- テスト関連モジュール

### さらなるサイズ削減（上級者向）

1. **軽量なCSV処理ライブラリを使用**
   - Pandasの代わりに標準のcsvモジュールを使用
   - ただし、エンコーディング処理が複雑になります

2. **UPX圧縮を使用**
   - UPXツールをインストール: https://upx.github.io/
   - `--upx-dir=<UPXのパス>` でビルド
   - 30-40%のサイズ削減が可能
   - ただし、ウイルス誤検知の可能性が高くなります

3. **フォルダ形式を使用**
   - `--onedir` オプション
   - 起動が高速
   - フォルダごと配布が必要

## 注意事項

- 初回起動時は少し時間がかかる場合があります
- セキュリティソフトによってはウイルス誤検知される可能性があります
  （Python EXEは誤検知されやすい傾向があります）
- Windows以外のOSでは動作しません（OS固有のビルドが必要）
- 最適化ビルドでも動作に問題がないことを十分にテストしてください
