"""
CSV to Excel変換アプリケーション
PySide6を使用したGUIアプリケーション

機能:
- CSVファイルのドラッグ&ドロップ
- 文字エンコーディング自動検出 (SJIS, UTF-8 BOM付き/なし)
- ヘッダー有無の選択
- 3つの変換モード:
  a. CSV1ファイルにつき1Excelファイル
  b. 複数CSVを1Excelファイル(各CSV=各シート)
  c. 複数CSVを1Excelファイル(1シートにマージ)
"""

import sys
import os
from pathlib import Path
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import chardet
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QListWidget,
    QRadioButton,
    QCheckBox,
    QButtonGroup,
    QMessageBox,
    QFileDialog,
    QProgressBar,
)
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent


class CsvToExcelConverter(QMainWindow):
    """CSV to Excel変換アプリケーションのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.csv_files: List[str] = []
        self.output_dir: Optional[str] = None
        self.init_ui()

    def init_ui(self) -> None:
        """UIの初期化"""
        self.setWindowTitle("CSV to Excel 変換ツール")
        self.setGeometry(100, 100, 700, 600)

        # メインウィジェット
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # タイトル
        title_label = QLabel("CSV to Excel 変換ツール")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # ドラッグ&ドロップエリア
        drop_label = QLabel(
            "CSVファイルをここにドラッグ&ドロップ\nまたは下のボタンでファイル選択"
        )
        drop_label.setStyleSheet(
            """
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 5px;
                padding: 40px;
                background-color: #f5f5f5;
                font-size: 14px;
            }
            """
        )
        drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(drop_label)

        # ファイル選択ボタン
        btn_layout = QHBoxLayout()
        self.btn_add_files = QPushButton("ファイルを選択")
        self.btn_add_files.clicked.connect(self.select_files)
        self.btn_clear_files = QPushButton("リストをクリア")
        self.btn_clear_files.clicked.connect(self.clear_files)
        btn_layout.addWidget(self.btn_add_files)
        btn_layout.addWidget(self.btn_clear_files)
        layout.addLayout(btn_layout)

        # ファイルリスト
        list_label = QLabel("選択されたCSVファイル:")
        list_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(list_label)

        self.file_list = QListWidget()
        self.file_list.setStyleSheet("padding: 5px;")
        layout.addWidget(self.file_list)

        # オプション設定
        options_label = QLabel("変換オプション:")
        options_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(options_label)

        # ヘッダー設定
        header_group_label = QLabel("ヘッダー設定:")
        header_group_label.setStyleSheet("margin-left: 10px; margin-top: 5px;")
        layout.addWidget(header_group_label)
        
        self.header_button_group = QButtonGroup()
        
        self.header_yes = QRadioButton("CSVの1行目をヘッダーとして扱う")
        self.header_yes.setStyleSheet("margin-left: 20px;")
        self.header_button_group.addButton(self.header_yes, 0)
        layout.addWidget(self.header_yes)
        
        self.header_no = QRadioButton("ヘッダー無し(全ての行をデータとして扱う)")
        self.header_no.setStyleSheet("margin-left: 20px;")
        self.header_button_group.addButton(self.header_no, 1)
        layout.addWidget(self.header_no)
        
        self.header_yes.setChecked(True)

        # 変換モード選択
        mode_label = QLabel("変換モード:")
        mode_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(mode_label)

        self.mode_group = QButtonGroup()

        self.mode_a = QRadioButton("モードA: 1CSV → 1Excelファイル")
        self.mode_a.setToolTip("各CSVファイルを個別のExcelファイルに変換します")
        self.mode_group.addButton(self.mode_a, 0)
        layout.addWidget(self.mode_a)

        self.mode_b = QRadioButton("モードB: 複数CSV → 1Excel (各シート)")
        self.mode_b.setToolTip("複数のCSVを1つのExcelファイルにまとめ、各CSVを別シートに配置します")
        self.mode_group.addButton(self.mode_b, 1)
        layout.addWidget(self.mode_b)

        self.mode_c = QRadioButton("モードC: 複数CSV → 1Excel (1シートにマージ)")
        self.mode_c.setToolTip(
            "複数のCSVを1つのExcelファイルの1シートにマージします(ファイル名を先頭に追加)"
        )
        self.mode_group.addButton(self.mode_c, 2)
        layout.addWidget(self.mode_c)

        self.mode_a.setChecked(True)

        # 出力先設定
        output_label = QLabel("出力先:")
        output_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(output_label)

        output_info_layout = QHBoxLayout()
        self.output_dir_label = QLabel("CSVファイルと同じフォルダに出力されます")
        self.output_dir_label.setStyleSheet(
            "padding: 5px; background-color: #e8f4f8; border-radius: 3px;"
        )
        output_info_layout.addWidget(self.output_dir_label, 1)

        self.btn_change_output = QPushButton("出力先を変更")
        self.btn_change_output.setStyleSheet(
            "padding: 5px 15px; background-color: #2196F3; color: white; border-radius: 3px;"
        )
        self.btn_change_output.clicked.connect(self.change_output_directory)
        output_info_layout.addWidget(self.btn_change_output)
        layout.addLayout(output_info_layout)

        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 変換ボタン
        self.btn_convert = QPushButton("Excel変換を実行")
        self.btn_convert.setStyleSheet(
            """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
            """
        )
        self.btn_convert.clicked.connect(self.convert_to_excel)
        self.btn_convert.setEnabled(False)
        layout.addWidget(self.btn_convert)

        # ドラッグ&ドロップを有効化
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """ドラッグエンターイベント"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        """ドロップイベント"""
        mime_data: QMimeData = event.mimeData()
        if mime_data.hasUrls():
            for url in mime_data.urls():
                file_path = url.toLocalFile()
                if file_path.lower().endswith(".csv"):
                    if file_path not in self.csv_files:
                        self.csv_files.append(file_path)
                        self.file_list.addItem(os.path.basename(file_path))
            self.update_output_directory()
            self.update_convert_button()

    def select_files(self) -> None:
        """ファイル選択ダイアログを表示"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "CSVファイルを選択", "", "CSV Files (*.csv);;All Files (*)"
        )
        for file_path in files:
            if file_path not in self.csv_files:
                self.csv_files.append(file_path)
                self.file_list.addItem(os.path.basename(file_path))
        self.update_output_directory()
        self.update_convert_button()

    def clear_files(self) -> None:
        """ファイルリストをクリア"""
        self.csv_files.clear()
        self.file_list.clear()
        self.output_dir = None
        self.output_dir_label.setText("CSVファイルと同じフォルダに出力されます")
        self.update_convert_button()

    def update_convert_button(self) -> None:
        """変換ボタンの有効/無効を更新"""
        self.btn_convert.setEnabled(len(self.csv_files) > 0)

    def update_output_directory(self) -> None:
        """出力先ディレクトリを更新"""
        if self.csv_files and self.output_dir is None:
            # デフォルト出力先を最初のCSVファイルのディレクトリに設定
            default_dir = os.path.dirname(self.csv_files[0])
            self.output_dir = default_dir
            self.output_dir_label.setText(f"出力先: {self.output_dir}")

    def change_output_directory(self) -> None:
        """出力先ディレクトリを変更"""
        # 現在の出力先をデフォルトとして使用
        current_dir = self.output_dir if self.output_dir else ""
        if not current_dir and self.csv_files:
            current_dir = os.path.dirname(self.csv_files[0])

        new_dir = QFileDialog.getExistingDirectory(
            self, "出力先フォルダを選択", current_dir
        )
        if new_dir:
            self.output_dir = new_dir
            self.output_dir_label.setText(f"出力先: {self.output_dir}")

    def detect_encoding(self, file_path: str) -> str:
        """
        ファイルのエンコーディングを検出

        Args:
            file_path: CSVファイルパス

        Returns:
            検出されたエンコーディング名
        """
        with open(file_path, "rb") as f:
            raw_data = f.read()

        # BOM付きUTF-8をチェック
        if raw_data.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"

        # chardetで検出
        result = chardet.detect(raw_data)
        encoding = result["encoding"]

        # Shift_JISの変換
        if encoding and encoding.lower() in ["shift_jis", "shift-jis", "cp932"]:
            return "shift_jis"

        return encoding if encoding else "utf-8"

    def sanitize_sheet_name(self, name: str, max_length: int = 31) -> str:
        """
        Excelシート名として使用できるように文字列を正規化

        Args:
            name: 元の名前
            max_length: 最大長（デフォルト31文字）

        Returns:
            正規化されたシート名
        """
        # Excelシート名で使用できない文字: \ / * ? [ ] :
        invalid_chars = ['\\', '/', '*', '?', '[', ']', ':']
        
        # 無効な文字をアンダースコアに置換
        sanitized = name
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')
        
        # 先頭・末尾のスペースを削除
        sanitized = sanitized.strip()
        
        # 空文字列の場合はデフォルト名を使用
        if not sanitized:
            sanitized = "Sheet"
        
        # 最大長に切り詰め
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized

    def is_empty_csv(self, file_path: str) -> bool:
        """
        CSVファイルが空または改行のみかをチェック

        Args:
            file_path: CSVファイルパス

        Returns:
            空または改行のみの場合True
        """
        try:
            # ファイルサイズをチェック
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                return True
            
            # ファイル内容をチェック（複数エンコーディング対応）
            for encoding in ['utf-8', 'shift_jis', 'cp932', 'utf-8-sig']:
                try:
                    with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                        content = f.read().strip()
                        if len(content) == 0:
                            return True
                        # カンマのみや改行のみもチェック
                        if content.replace(',', '').replace('\n', '').replace('\r', '') == '':
                            return True
                    break
                except Exception:
                    continue
            
            return False
        except Exception:
            return False

    def read_csv(self, file_path: str, has_header: bool) -> Optional[pd.DataFrame]:
        """
        CSVファイルを読み込み

        Args:
            file_path: CSVファイルパス
            has_header: ヘッダー行の有無

        Returns:
            DataFrameオブジェクト、空ファイルの場合はNone
        """
        # 空ファイルまたは改行のみのファイルをチェック
        if self.is_empty_csv(file_path):
            return None

        encoding = self.detect_encoding(file_path)
        header = 0 if has_header else None

        try:
            # ダブルクォーテーションで囲まれた項目を文字列として扱う
            df = pd.read_csv(
                file_path,
                encoding=encoding,
                header=header,
                quoting=1,  # QUOTE_ALL: ダブルクォーテーションで囲まれた項目を処理
                dtype=str,  # 全ての列を文字列として読み込み、データ型の自動推測を防ぐ
                keep_default_na=False,  # 空文字列をNaNに変換しない
            )
            
            # データフレームが空の場合もNoneを返す
            if df.empty:
                return None
            
            return df
        except pd.errors.EmptyDataError:
            # 空のCSVファイル（データなし）
            return None
        except ValueError as e:
            if "No columns to parse" in str(e):
                # カラムが解析できない（空ファイル）
                return None
            raise Exception(f"CSVファイルの読み込みに失敗: {file_path}\n{str(e)}")
        except Exception as e:
            raise Exception(f"CSVファイルの読み込みに失敗: {file_path}\n{str(e)}")

    def convert_mode_a(self, output_dir: str, has_header: bool) -> None:
        """
        モードA: 1CSV → 1Excelファイル（並列処理で高速化）

        Args:
            output_dir: 出力ディレクトリ
            has_header: ヘッダー行の有無
        """
        def process_single_file(csv_file: str) -> bool:
            """単一CSVファイルを処理"""
            try:
                df = self.read_csv(csv_file, has_header)
                
                # 空ファイルの場合はスキップ
                if df is None:
                    return False
                
                base_name = Path(csv_file).stem
                excel_path = os.path.join(output_dir, f"{base_name}.xlsx")

                # 高速書き込み設定
                with pd.ExcelWriter(excel_path, engine="openpyxl", mode='w') as writer:
                    df.to_excel(writer, index=False, header=has_header, sheet_name="Sheet1")
                    # スタイルを最小限に抑えて高速化
                    writer.book.write_only = False
                
                return True
            except Exception:
                return False

        # 並列処理で変換（最大4ワーカー）
        total = len(self.csv_files)
        completed = 0
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(process_single_file, csv_file): csv_file 
                      for csv_file in self.csv_files}
            
            for future in as_completed(futures):
                completed += 1
                self.progress_bar.setValue(int((completed / total) * 100))
                QApplication.processEvents()

        self.progress_bar.setValue(100)

    def convert_mode_b(self, output_dir: str, has_header: bool) -> None:
        """
        モードB: 複数CSV → 1Excel (各シート)（最適化版）

        Args:
            output_dir: 出力ディレクトリ
            has_header: ヘッダー行の有無
        """
        excel_path = os.path.join(output_dir, "merged_sheets.xlsx")
        
        # 先にすべてのCSVを読み込み（並列処理）
        dataframes = {}
        total = len(self.csv_files)
        sheet_name_counts = {}  # シート名の重複をカウント
        
        def load_csv(csv_file: str) -> tuple:
            df = self.read_csv(csv_file, has_header)
            base_name = Path(csv_file).stem
            return (csv_file, base_name, df)
        
        # 並列でCSV読み込み
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(load_csv, csv_file): csv_file 
                      for csv_file in self.csv_files}
            
            completed = 0
            results = []
            for future in as_completed(futures):
                csv_file, base_name, df = future.result()
                if df is not None:
                    results.append((csv_file, base_name, df))
                completed += 1
                self.progress_bar.setValue(int((completed / total) * 50))  # 50%まで読み込み
                QApplication.processEvents()
        
        # 元のファイル順序を保持してシート名の重複を処理
        for csv_file in self.csv_files:
            for saved_csv, base_name, df in results:
                if saved_csv == csv_file:
                    # シート名を正規化（無効文字を除外）
                    sheet_name = self.sanitize_sheet_name(base_name, 31)
                    
                    # 重複チェック
                    if sheet_name in sheet_name_counts:
                        # 重複している場合、番号を付与
                        sheet_name_counts[sheet_name] += 1
                        counter = sheet_name_counts[sheet_name]
                        # 番号を付けても31文字以内に収める
                        suffix = f"_{counter}"
                        max_base_len = 31 - len(suffix)
                        sheet_name = f"{self.sanitize_sheet_name(base_name, max_base_len)}{suffix}"
                    else:
                        sheet_name_counts[sheet_name] = 0
                    
                    dataframes[sheet_name] = df
                    break
        
        # 一括書き込み（残り50%）
        if dataframes:
            with pd.ExcelWriter(excel_path, engine="openpyxl", mode='w') as writer:
                for i, (sheet_name, df) in enumerate(dataframes.items()):
                    df.to_excel(writer, index=False, header=has_header, sheet_name=sheet_name)
                    progress = 50 + int((i + 1) / len(dataframes) * 50)
                    self.progress_bar.setValue(progress)
                    QApplication.processEvents()

        self.progress_bar.setValue(100)

    def convert_mode_c(self, output_dir: str, has_header: bool) -> None:
        """
        モードC: 複数CSV → 1Excel (1シートにマージ)（最適化版）

        Args:
            output_dir: 出力ディレクトリ
            has_header: ヘッダー行の有無
        """
        excel_path = os.path.join(output_dir, "merged_single_sheet.xlsx")
        all_data = []
        
        def load_and_add_filename(csv_file: str) -> Optional[pd.DataFrame]:
            """CSVを読み込んでファイル名列を追加"""
            df = self.read_csv(csv_file, has_header)
            if df is None:
                return None
            file_name = Path(csv_file).stem
            df.insert(0, "ファイル名", file_name)
            return df
        
        # 並列でCSV読み込み
        total = len(self.csv_files)
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(load_and_add_filename, csv_file): csv_file 
                      for csv_file in self.csv_files}
            
            completed = 0
            for future in as_completed(futures):
                df = future.result()
                if df is not None:
                    all_data.append(df)
                completed += 1
                self.progress_bar.setValue(int((completed / total) * 80))  # 80%まで読み込み
                QApplication.processEvents()

        # 全データを結合（空データの場合は空のExcelを作成しない）
        if not all_data:
            self.progress_bar.setValue(100)
            return
        
        self.progress_bar.setValue(85)
        QApplication.processEvents()
        
        # 高速結合
        merged_df = pd.concat(all_data, ignore_index=True, copy=False)
        
        self.progress_bar.setValue(90)
        QApplication.processEvents()

        # 高速書き込み
        with pd.ExcelWriter(excel_path, engine="openpyxl", mode='w') as writer:
            merged_df.to_excel(writer, index=False, header=has_header, sheet_name="Merged")

        self.progress_bar.setValue(100)

    def convert_to_excel(self) -> None:
        """Excel変換を実行"""
        if not self.csv_files:
            QMessageBox.warning(self, "警告", "CSVファイルが選択されていません。")
            return

        # 出力先が設定されていない場合はデフォルトを使用
        if not self.output_dir:
            self.output_dir = os.path.dirname(self.csv_files[0])
        
        output_dir = self.output_dir

        # プログレスバーを表示
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_convert.setEnabled(False)

        try:
            has_header = self.header_button_group.checkedId() == 0
            mode_id = self.mode_group.checkedId()

            if mode_id == 0:  # モードA
                self.convert_mode_a(output_dir, has_header)
            elif mode_id == 1:  # モードB
                self.convert_mode_b(output_dir, has_header)
            elif mode_id == 2:  # モードC
                self.convert_mode_c(output_dir, has_header)

            QMessageBox.information(
                self,
                "完了",
                f"Excel変換が完了しました。\n出力先: {output_dir}",
            )

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"変換中にエラーが発生しました:\n{str(e)}")

        finally:
            self.progress_bar.setVisible(False)
            self.btn_convert.setEnabled(True)


def main():
    """メイン関数"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # モダンな見た目に設定

    window = CsvToExcelConverter()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
