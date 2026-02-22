# PDF→TIFF オフライン手順（実行PCにPythonなし）

このガイドは、ビルドPCでEXEを作成し、Pythonの無いオフラインPCで実行する手順です。

## 1) ビルドPC（オンライン、または必要パッケージが準備済み）

1. 仮想環境の作成/有効化（推奨）:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. ビルド依存のインストール:
   ```powershell
   python -m pip install pyinstaller pymupdf pillow
   ```

3. EXEをビルド:
   ```powershell
   build_pdf.bat
   ```

4. EXEをオフラインPCへコピー:
   - dist\PDFtoTIFF.exe

## 2) オフラインPC（Python不要）

1. EXEを実行:
   - dist\PDFtoTIFF.exe をダブルクリック

2. GUIでPDF、出力フォルダ、DPIを選択して「変換」を実行
   - 2値化する場合は「2値化(1bit)」をON、しきい値（0〜255）を設定
   - 圧縮方式はプルダウンから選択（詳細は「詳細」ボタン）

## 注意

- ビルドPCと実行PCは同じOS/アーキテクチャ（Windows 64bit）で作成してください。
- コマンドラインで使う場合:
  ```powershell
   PDFtoTIFF.exe input.pdf output_dir --dpi 300 --bilevel --threshold 128 --compression group4
  ```
- 出力フォルダにCSVログが生成されます: <prefix>_log.csv
- 変換完了時にダイアログで完了通知します
