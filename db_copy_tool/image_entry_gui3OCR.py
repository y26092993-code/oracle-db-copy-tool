"""PySide6 GUI: イメージを見ながら宛名番号を一覧で入力するアプリ

機能:
- 指定フォルダ内のイメージファイル名を仕様に従って解析して一覧表示
- 選択した画像をプレビュー表示
- 各画像に対して「宛名番号」「資料冊号」「資料連番」を入力して保存
- 保存は Shift-JIS (cp932) の CSV 形式（イメージ紐づけ仕様）で出力

使い方:
python image_entry_gui.py --input-dir "C:/path/to/images" --output "C:/path/to/out/image_linkage.csv"

注: PySide6 が必要です。インストール:
    python -m pip install PySide6

設計上の注意:
- ファイル名のパターンは仕様に従う (例: 508-050-0001-0010001_01.tif)
- 形式に合わないファイルはリストに表示されるが灰色化され、編集を促す
"""

from __future__ import annotations

import argparse
import csv
import io
import shutil
import zipfile
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import json
import subprocess
import tempfile
import os
import glob
import subprocess

from PySide6.QtCore import Qt, QSize, QEvent, QPoint, Signal, QThread, QTimer, QStringListModel
from PySide6.QtGui import QPixmap, QKeySequence, QBrush, QColor, QFont, QPainter, QTransform
from PySide6.QtWidgets import QStyle
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
        QAbstractItemView,
        QStyledItemDelegate,
        QStyleOptionViewItem,
    QSizePolicy,
    QComboBox,
    QPushButton,
    QCheckBox,
    QDialog,
    QTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QProgressDialog,
    QCompleter,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

"""
Detect OCR backend availability lazily without importing heavy libraries at module
import time. We use importlib.util.find_spec to check availability so the GUI can
start even if OCR packages are not installed.
"""
import importlib.util

def _spec_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False

# Flags indicating whether backends are installable (not necessarily usable at runtime).
PYTESSERACT_AVAILABLE = _spec_exists('pytesseract')
PIL_AVAILABLE = _spec_exists('PIL')
EASYOCR_AVAILABLE = _spec_exists('easyocr')
PADDLE_AVAILABLE = _spec_exists('paddleocr')
YOMITOKU_AVAILABLE = _spec_exists('yomitoku')

# overall OCR availability if any backend+PIL is present
OCR_AVAILABLE = ((PYTESSERACT_AVAILABLE and PIL_AVAILABLE) or EASYOCR_AVAILABLE or PADDLE_AVAILABLE or YOMITOKU_AVAILABLE)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# Helpers to mark the settings file as hidden on Windows or dot-prefixed on POSIX.
def _set_hidden(path: Path) -> None:
    try:
        if not path.exists():
            return
        if os.name == 'nt':
            try:
                import ctypes
                FILE_ATTRIBUTE_HIDDEN = 0x02
                GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
                SetFileAttributesW = ctypes.windll.kernel32.SetFileAttributesW
                GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
                GetFileAttributesW.restype = ctypes.c_uint32
                attrs = GetFileAttributesW(str(path))
                if attrs != 0xFFFFFFFF:
                    SetFileAttributesW(str(path), attrs | FILE_ATTRIBUTE_HIDDEN)
            except Exception:
                # best-effort only
                pass
        else:
            # POSIX: rename to dotfile if not already hidden
            if not path.name.startswith('.'):
                newp = path.with_name('.' + path.name)
                try:
                    path.replace(newp)
                except Exception:
                    pass
    except Exception:
        pass


def _clear_hidden(path: Path) -> None:
    try:
        if not path.exists():
            return
        if os.name == 'nt':
            try:
                import ctypes
                FILE_ATTRIBUTE_HIDDEN = 0x02
                GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
                SetFileAttributesW = ctypes.windll.kernel32.SetFileAttributesW
                GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
                GetFileAttributesW.restype = ctypes.c_uint32
                attrs = GetFileAttributesW(str(path))
                if attrs != 0xFFFFFFFF:
                    SetFileAttributesW(str(path), int(attrs & ~FILE_ATTRIBUTE_HIDDEN))
            except Exception:
                pass
        else:
            # POSIX: if dot-prefixed, rename back to non-dot name (best-effort)
            if path.name.startswith('.'):
                new_name = path.name.lstrip('.')
                newp = path.with_name(new_name)
                try:
                    path.replace(newp)
                except Exception:
                    pass
    except Exception:
        pass


IMG_REGEX = re.compile(
    r"^(?P<era>\d{3})-(?P<form>\d{3})-(?P<manage>\d{4})-(?P<seq>\d{7})(?:_(?P<page>\d+))?\.(?P<ext>tif|tiff|jpg|jpeg|png)$",
    re.IGNORECASE,
)


@dataclass
class ImageRecord:
    path: Path
    era: Optional[str]
    form: Optional[str]
    manage: Optional[str]
    seq: Optional[str]
    page: Optional[str]

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def image_number(self) -> str:
        if self.era and self.form and self.manage and self.seq:
            return f"{self.era}-{self.form}-{self.manage}-{self.seq}"
        return ""

    @property
    def key_for_linkage(self) -> str:
        # ファイル名からハイフンと拡張子を除いたもの
        return self.path.stem.replace("-", "")


@dataclass
class TaxpayerRecord:
    """納税義務者情報のレコード"""
    municipality_code: str  # 市区町村コード
    tax_year: str  # 課税年度
    addressee_number: str  # 宛名番号
    postal_code: str  # 郵便番号
    address_prefecture: str  # 住所_都道府県
    address_city: str  # 住所_市区郡町村名
    address_town: str  # 住所_町字
    address_number: str  # 住所_番地号表記
    address_other: str  # 住所_方書
    name_kana: str  # 氏名（振り仮名）
    name: str  # 氏名
    birth_date: str  # 生年月日
    
    def matches_search(self, query: str) -> bool:
        """検索クエリにマッチするかチェック（日本語対応）"""
        if not query:
            return True
        # 日本語の場合はそのまま、英数字の場合は小文字化
        query_normalized = query if any(ord(c) > 127 for c in query) else query.lower()
        
        def normalize_and_check(text: str) -> bool:
            if not text:
                return False
            # 日本語を含む場合はそのまま、英数字のみの場合は小文字化
            text_normalized = text if any(ord(c) > 127 for c in text) else text.lower()
            return query_normalized in text_normalized
        
        return (
            normalize_and_check(self.addressee_number) or
            normalize_and_check(self.name) or
            normalize_and_check(self.name_kana) or
            normalize_and_check(self.address_prefecture) or
            normalize_and_check(self.address_city) or
            normalize_and_check(self.address_town) or
            normalize_and_check(self.address_number) or
            normalize_and_check(self.address_other) or
            normalize_and_check(self.postal_code) or
            normalize_and_check(self.full_address)
        )
    
    @property
    def full_address(self) -> str:
        """完全な住所を返す（表示用）"""
        parts = [self.address_prefecture, self.address_city, self.address_town, self.address_number]
        if self.address_other:
            parts.append(self.address_other)
        return "".join(part for part in parts if part)
    
    def get_wareki_birth_date(self) -> str:
        """生年月日を和暦表示に変換して返す"""
        if not self.birth_date:
            return ""
        
        try:
            # 日付を解析 (yyyy/mm/dd または yyyy-mm-dd 形式をサポート)
            date_str = self.birth_date.strip().strip("'")
            if '/' in date_str:
                year, month, day = date_str.split('/')
            elif '-' in date_str:
                year, month, day = date_str.split('-')
            else:
                return self.birth_date  # フォーマットが不明な場合はそのまま返す
            
            year = int(year)
            month = int(month)
            day = int(day)
            
            # 和暦変換
            if year >= 2019:
                era_name = "令和"
                era_year = year - 2018
            elif year >= 1989:
                era_name = "平成"
                era_year = year - 1988
            elif year >= 1926:
                era_name = "昭和"
                era_year = year - 1925
            elif year >= 1912:
                era_name = "大正"
                era_year = year - 1911
            elif year >= 1868:
                era_name = "明治"
                era_year = year - 1867
            else:
                return f"{year}年{month}月{day}日"
            
            return f"{era_name}{era_year}年{month}月{day}日"
            
        except (ValueError, IndexError) as e:
            # エラーの場合は元の値を返す
            return self.birth_date


class ListItemDelegate(QStyledItemDelegate):
    """Custom delegate to draw list items consistently across platforms.

    - Selected row: use system highlight/background and highlighted text color
    - Disabled (parse-failed) row: draw in grey
    - Fallback: selected row is italic
    """

    def paint(self, painter, option, index):
        # Use the platform default painting as much as possible to avoid
        # inconsistencies. Only tweak the palette/font for disabled/selected.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        try:
            from PySide6.QtGui import QPalette

            # If item is not enabled (parse failed), show it in grey text
            if not (index.flags() & Qt.ItemIsEnabled):
                opt.palette.setColor(QPalette.Text, QColor(130, 130, 130))
            # Make selected item italic as a fallback visual cue
            if opt.state & QStyle.State_Selected:
                opt.font.setItalic(True)
        except Exception:
            pass

        # Delegate to base painter which respects platform styles (selection, focus, etc.)
        super().paint(painter, opt, index)

    def sizeHint(self, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        from PySide6.QtGui import QFontMetrics

        fm = QFontMetrics(opt.font)
        h = max(20, fm.height() + 8)
        return QSize(fm.horizontalAdvance(opt.text) + 12, h)


class PreviewLabel(QLabel):
    """QLabel subclass that supports panning (drag) and controlled scaling.

    Usage:
        preview = PreviewLabel()
        preview.set_image(pixmap, fit_to_window=True, zoom=1.0)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._full_pixmap: Optional[QPixmap] = None
        self._scaled_pixmap: Optional[QPixmap] = None
        self._offset = QPoint(0, 0)
        self._dragging = False
        self._last_pos = QPoint(0, 0)
        self.fit_to_window = True
        self.zoom = 1.0
        self.setMouseTracking(True)
        
        # 範囲選択機能用
        self._selection_mode = False
        self._selection_start = None
        self._selection_rect = None
        self._selection_active = False

    def set_image(self, pix: QPixmap, fit_to_window: bool = True, zoom: float = 1.0, preserve_view: bool = False) -> None:
        """Set the image to display.

        preserve_view: if True, try to preserve previous offset (pixel coordinates) and zoom position.
        """
        old_offset = QPoint(self._offset) if preserve_view else None
        self._full_pixmap = pix
        self.fit_to_window = fit_to_window
        self.zoom = zoom
        self._rescale()
        # preserve previous view (offset) when requested; otherwise center
        if preserve_view and old_offset is not None:
            self._offset = old_offset
            self._clamp_offset()
        else:
            self._center_or_clamp()
        self.update()
    
    def enable_selection_mode(self) -> None:
        """範囲選択モードを有効にする。"""
        self._selection_mode = True
        self._selection_rect = None
        self._selection_active = False
        self.setCursor(Qt.CrossCursor)
        self.update()
    
    def disable_selection_mode(self) -> None:
        """範囲選択モードを無効にする。"""
        self._selection_mode = False
        self._selection_rect = None
        self._selection_active = False
        self.setCursor(Qt.ArrowCursor)
        self.update()
    
    def get_selected_region(self):
        """選択された領域をフルサイズ画像の座標で返す。
        
        Returns:
            tuple: (x, y, width, height) または None
        """
        if not self._selection_rect or self._full_pixmap is None or self._scaled_pixmap is None:
            return None
        
        # 表示座標からフルサイズ画像の座標に変換
        scale_x = self._full_pixmap.width() / self._scaled_pixmap.width()
        scale_y = self._full_pixmap.height() / self._scaled_pixmap.height()
        
        # オフセットを考慮した選択矩形の画像内座標
        img_x = (self._selection_rect.x() - self._offset.x()) * scale_x
        img_y = (self._selection_rect.y() - self._offset.y()) * scale_y
        img_w = self._selection_rect.width() * scale_x
        img_h = self._selection_rect.height() * scale_y
        
        # 画像範囲内にクリップ
        img_x = max(0, min(img_x, self._full_pixmap.width()))
        img_y = max(0, min(img_y, self._full_pixmap.height()))
        img_w = max(0, min(img_w, self._full_pixmap.width() - img_x))
        img_h = max(0, min(img_h, self._full_pixmap.height() - img_y))
        
        return (int(img_x), int(img_y), int(img_w), int(img_h))

    def _clamp_offset(self) -> None:
        """Clamp self._offset so the image stays within view bounds."""
        if self._scaled_pixmap is None:
            self._offset = QPoint(0, 0)
            return
        w_img = self._scaled_pixmap.width()
        h_img = self._scaled_pixmap.height()
        w_lbl = self.width()
        h_lbl = self.height()
        if w_img > w_lbl:
            min_x = w_lbl - w_img
            max_x = 0
            x = max(min_x, min(max_x, self._offset.x()))
        else:
            x = (w_lbl - w_img) // 2
        if h_img > h_lbl:
            min_y = h_lbl - h_img
            max_y = 0
            y = max(min_y, min(max_y, self._offset.y()))
        else:
            y = (h_lbl - h_img) // 2
        self._offset = QPoint(x, y)

    def _rescale(self) -> None:
        if self._full_pixmap is None:
            self._scaled_pixmap = None
            return
        if self.fit_to_window:
            target = self.size()
            if target.width() <= 0 or target.height() <= 0:
                self._scaled_pixmap = self._full_pixmap
                return
            self._scaled_pixmap = self._full_pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            w = max(1, int(self._full_pixmap.width() * self.zoom))
            h = max(1, int(self._full_pixmap.height() * self.zoom))
            self._scaled_pixmap = self._full_pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _center_or_clamp(self) -> None:
        if self._scaled_pixmap is None:
            self._offset = QPoint(0, 0)
            return
        w_img = self._scaled_pixmap.width()
        h_img = self._scaled_pixmap.height()
        w_lbl = self.width()
        h_lbl = self.height()
        # center if image smaller than label
        if w_img <= w_lbl:
            x = (w_lbl - w_img) // 2
        else:
            x = 0
        if h_img <= h_lbl:
            y = (h_lbl - h_img) // 2
        else:
            y = 0
        self._offset = QPoint(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().window())
        if self._scaled_pixmap is None:
            super().paintEvent(event)
            return
        # draw pixmap at offset; if image larger than label, offset may be negative to pan
        painter.drawPixmap(self._offset, self._scaled_pixmap)
        
        # 範囲選択の描画
        if self._selection_mode and self._selection_rect:
            from PySide6.QtGui import QPen
            pen = QPen(QColor(0, 120, 215), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(0, 120, 215, 50)))
            painter.drawRect(self._selection_rect)

    def resizeEvent(self, event) -> None:
        # when resized, recompute scaled pixmap if fit_to_window
        super().resizeEvent(event)
        self._rescale()
        self._center_or_clamp()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            # 範囲選択モードの場合
            if self._selection_mode:
                try:
                    pos = event.position().toPoint()
                except Exception:
                    pos = event.pos()
                self._selection_start = pos
                self._selection_rect = None
                self._selection_active = True
                event.accept()
                return
            
            # start dragging only if image is larger than label
            if self._scaled_pixmap and (self._scaled_pixmap.width() > self.width() or self._scaled_pixmap.height() > self.height()):
                self._dragging = True
                # use position() -> QPointF, convert to QPoint to avoid deprecated pos()
                try:
                    self._last_pos = event.position().toPoint()
                except Exception:
                    self._last_pos = event.pos()
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        # 範囲選択中の場合
        if self._selection_mode and self._selection_active and self._selection_start:
            try:
                cur_pos = event.position().toPoint()
            except Exception:
                cur_pos = event.pos()
            
            # 選択矩形を更新
            from PySide6.QtCore import QRect
            x = min(self._selection_start.x(), cur_pos.x())
            y = min(self._selection_start.y(), cur_pos.y())
            w = abs(cur_pos.x() - self._selection_start.x())
            h = abs(cur_pos.y() - self._selection_start.y())
            self._selection_rect = QRect(x, y, w, h)
            self.update()
            event.accept()
            return
        
        if self._dragging and self._scaled_pixmap:
            try:
                cur_pos = event.position().toPoint()
            except Exception:
                cur_pos = event.pos()
            delta = cur_pos - self._last_pos
            self._last_pos = cur_pos
            # adjust offset
            new_x = self._offset.x() + delta.x()
            new_y = self._offset.y() + delta.y()
            # clamp so edges are not leaving blank beyond the image
            w_img = self._scaled_pixmap.width()
            h_img = self._scaled_pixmap.height()
            w_lbl = self.width()
            h_lbl = self.height()
            if w_img > w_lbl:
                min_x = w_lbl - w_img
                max_x = 0
                new_x = max(min_x, min(max_x, new_x))
            else:
                new_x = (w_lbl - w_img) // 2
            if h_img > h_lbl:
                min_y = h_lbl - h_img
                max_y = 0
                new_y = max(min_y, min(max_y, new_y))
            else:
                new_y = (h_lbl - h_img) // 2
            self._offset = QPoint(new_x, new_y)
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            # 範囲選択モードの場合
            if self._selection_mode and self._selection_active:
                self._selection_active = False
                # 範囲が選択されている場合、親ウィジェットにシグナルを送る
                if self._selection_rect and self._selection_rect.width() > 5 and self._selection_rect.height() > 5:
                    # 親ウィジェット(ImageEntryApp)のメソッドを直接呼び出す
                    # window()を使ってトップレベルウィンドウを取得
                    parent = self.window()
                    if parent and hasattr(parent, 'on_region_selected'):
                        region = self.get_selected_region()
                        if region:
                            try:
                                parent.on_region_selected(region)
                            except Exception as e:
                                print(f"on_region_selected error: {e}")
                                import traceback
                                traceback.print_exc()
                event.accept()
                return
            
            # ドラッグモードの場合
            if self._dragging:
                self._dragging = False
                self.setCursor(Qt.ArrowCursor)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        # forward wheel zoom to parent if available
        try:
            delta = event.angleDelta().y()
        except Exception:
            delta = event.delta() if hasattr(event, "delta") else 0
        # prefer the top-level window (safer than parent() because layouts/containers may reparent)
        p = self.window()
        if p is not None and hasattr(p, 'zoom_in') and hasattr(p, 'zoom_out'):
            try:
                if delta > 0:
                    p.zoom_in()
                elif delta < 0:
                    p.zoom_out()
            except Exception:
                pass
            event.accept()
            return
        super().wheelEvent(event)


class OCRThread(QThread):
    """Run OCR in a background thread and emit results back to the main thread."""

    finished = Signal(str)
    error = Signal(str)

    def __init__(self, app: 'ImageEntryApp', rec: ImageRecord):
        super().__init__()
        self.app = app
        self.rec = rec

    def run(self) -> None:
        try:
            # call the app's perform_ocr (heavy work)
            text = self.app.perform_ocr(self.rec)
            self.finished.emit(text if text is not None else "")
        except Exception as exc:
            self.error.emit(str(exc))


class FormListDialog(QDialog):
    """帳票No一覧を編集するダイアログ（多枚数対応フラグ付き）"""

    # デフォルトの帳票No（削除不可）
    DEFAULT_FORMS = ["住申：040", "給報：050", "年報：060"]

    # テーブル列定数
    COL_NAME = 0
    COL_CODE = 1
    COL_MULTI = 2

    def __init__(self, parent=None, current_list: List[str] = None,
                 multi_page_set: set = None):
        super().__init__(parent)
        self.setWindowTitle("帳票No 管理")
        self.resize(520, 420)

        self.form_list = current_list.copy() if current_list else []
        self._multi_page_set: set = set(multi_page_set) if multi_page_set else set()

        # テーブルウィジェット（名称 / コード / 多枚数対応）
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["名称", "コード", "多枚数対応"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._populate_table()

        # 編集用の入力フィールド
        input_layout = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("名称（例: 住申）")
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("コード（例: 040）")
        self.code_input.setMaxLength(3)
        self.multi_check = QCheckBox("多枚数対応")
        self.multi_check.setToolTip(
            "チェックすると、このインデックスファイル出力時に\n"
            "宛名番号グループの前後に -1,, の区切り行を挿入します"
        )
        input_layout.addWidget(QLabel("名称:"))
        input_layout.addWidget(self.name_input, 1)
        input_layout.addWidget(QLabel("コード:"))
        input_layout.addWidget(self.code_input)
        input_layout.addSpacing(8)
        input_layout.addWidget(self.multi_check)

        # ボタン
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("追加")
        edit_btn = QPushButton("修正")
        delete_btn = QPushButton("削除")
        up_btn = QPushButton("↑")
        down_btn = QPushButton("↓")

        add_btn.clicked.connect(self.add_item)
        edit_btn.clicked.connect(self.edit_item)
        delete_btn.clicked.connect(self.delete_item)
        up_btn.clicked.connect(self.move_up)
        down_btn.clicked.connect(self.move_down)

        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(up_btn)
        btn_layout.addWidget(down_btn)

        # OK/Cancelボタン
        dialog_btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("キャンセル")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        dialog_btn_layout.addStretch()
        dialog_btn_layout.addWidget(ok_btn)
        dialog_btn_layout.addWidget(cancel_btn)

        # レイアウト
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("帳票No 一覧（☑ 多枚数対応: 宛名番号グループ前後に -1,, を出力）"))
        layout.addWidget(self.table, 1)
        layout.addLayout(input_layout)
        layout.addLayout(btn_layout)
        layout.addLayout(dialog_btn_layout)

        # 行選択時に入力欄に反映
        self.table.currentCellChanged.connect(self.on_selection_changed)

    def _populate_table(self):
        """form_list と multi_page_set からテーブルを構築する"""
        self.table.setRowCount(0)
        for item_text in self.form_list:
            self._append_table_row(item_text)

    def _append_table_row(self, item_text: str, checked: bool = None):
        """テーブル末尾に1行追加する。checked=None の場合は _multi_page_set を参照。"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        if "：" in item_text:
            parts = item_text.split("：")
            name_cell = QTableWidgetItem(parts[0].strip())
            code_val = parts[1].strip()
            code_cell = QTableWidgetItem(code_val)
        else:
            name_cell = QTableWidgetItem(item_text)
            code_val = ""
            code_cell = QTableWidgetItem("")
        self.table.setItem(row, self.COL_NAME, name_cell)
        self.table.setItem(row, self.COL_CODE, code_cell)
        # 多枚数チェック列
        chk_item = QTableWidgetItem()
        chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        if checked is None:
            checked = code_val in self._multi_page_set
        chk_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        chk_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, self.COL_MULTI, chk_item)

    def on_selection_changed(self, current_row, *_):
        """行選択時に入力欄に値を設定"""
        if current_row < 0:
            return
        name_item = self.table.item(current_row, self.COL_NAME)
        code_item = self.table.item(current_row, self.COL_CODE)
        multi_item = self.table.item(current_row, self.COL_MULTI)
        if name_item:
            self.name_input.setText(name_item.text())
        if code_item:
            self.code_input.setText(code_item.text())
        if multi_item:
            self.multi_check.setChecked(multi_item.checkState() == Qt.Checked)

    def add_item(self):
        """アイテムを追加"""
        name = self.name_input.text().strip()
        code = self.code_input.text().strip()

        if not name or not code:
            QMessageBox.warning(self, "入力エラー", "名称とコードの両方を入力してください。")
            return
        if not code.isdigit() or len(code) != 3:
            QMessageBox.warning(self, "入力エラー", "コードは3桁の数字である必要があります。")
            return

        item_text = f"{name}：{code}"
        self.form_list.append(item_text)
        self._append_table_row(item_text, checked=self.multi_check.isChecked())
        self.name_input.clear()
        self.code_input.clear()
        self.multi_check.setChecked(False)

    def edit_item(self):
        """選択されたアイテムを修正"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "選択なし", "修正する項目を選択してください。")
            return

        name = self.name_input.text().strip()
        code = self.code_input.text().strip()

        if not name or not code:
            QMessageBox.warning(self, "入力エラー", "名称とコードの両方を入力してください。")
            return
        if not code.isdigit() or len(code) != 3:
            QMessageBox.warning(self, "入力エラー", "コードは3桁の数字である必要があります。")
            return

        item_text = f"{name}：{code}"
        self.table.item(row, self.COL_NAME).setText(name)
        self.table.item(row, self.COL_CODE).setText(code)
        chk = self.table.item(row, self.COL_MULTI)
        chk.setCheckState(Qt.Checked if self.multi_check.isChecked() else Qt.Unchecked)
        self.form_list[row] = item_text

    def delete_item(self):
        """選択されたアイテムを削除"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "選択なし", "削除する項目を選択してください。")
            return

        item_text = self.form_list[row]
        if item_text in self.DEFAULT_FORMS:
            QMessageBox.warning(self, "削除不可", f"デフォルトの帳票No（{item_text}）は削除できません。")
            return

        self.table.removeRow(row)
        self.form_list.pop(row)

    def move_up(self):
        """選択されたアイテムを上に移動"""
        row = self.table.currentRow()
        if row <= 0:
            return
        self._swap_rows(row, row - 1)
        self.table.setCurrentCell(row - 1, self.COL_NAME)

    def move_down(self):
        """選択されたアイテムを下に移動"""
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount() - 1:
            return
        self._swap_rows(row, row + 1)
        self.table.setCurrentCell(row + 1, self.COL_NAME)

    def _swap_rows(self, a: int, b: int):
        """テーブルの a 行と b 行を入れ替える"""
        for col in range(self.table.columnCount()):
            item_a = self.table.takeItem(a, col)
            item_b = self.table.takeItem(b, col)
            self.table.setItem(a, col, item_b)
            self.table.setItem(b, col, item_a)
        self.form_list[a], self.form_list[b] = self.form_list[b], self.form_list[a]

    def get_form_list(self) -> List[str]:
        """編集後の帳票No一覧を取得"""
        return self.form_list

    def get_multi_page_set(self) -> set:
        """多枚数対応としてチェックされた帳票コードのセットを返す"""
        result = set()
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, self.COL_MULTI)
            if chk and chk.checkState() == Qt.Checked:
                code_item = self.table.item(row, self.COL_CODE)
                if code_item:
                    result.add(code_item.text().strip())
        return result


class OptionsDialog(QDialog):
    """オプション設定ダイアログ"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("オプション設定")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.parent_app = parent

        layout = QVBoxLayout(self)
        
        # 納税義務者CSV選択
        taxpayer_row = QHBoxLayout()
        taxpayer_label = QLabel("納税義務者:")
        taxpayer_row.addWidget(taxpayer_label)
        self.taxpayer_path_label = QLabel("")
        if parent and hasattr(parent, 'taxpayer_csv_path'):
            self.taxpayer_path_label.setText(str(parent.taxpayer_csv_path))
        taxpayer_row.addWidget(self.taxpayer_path_label, 1)
        self.taxpayer_select_btn = QPushButton("選択...")
        self.taxpayer_select_btn.clicked.connect(self._select_taxpayer_csv)
        taxpayer_row.addWidget(self.taxpayer_select_btn)
        layout.addLayout(taxpayer_row)

        layout.addSpacing(10)

        # 出力先選択
        output_row = QHBoxLayout()
        output_label = QLabel("出力先:")
        output_row.addWidget(output_label)
        self.output_path_label = QLabel("")
        if parent and hasattr(parent, 'output_csv'):
            self.output_path_label.setText(str(parent.output_csv))
        output_row.addWidget(self.output_path_label, 1)
        self.output_select_btn = QPushButton("選択...")
        self.output_select_btn.clicked.connect(self._select_output)
        output_row.addWidget(self.output_select_btn)
        layout.addLayout(output_row)

        layout.addSpacing(20)

        # 管理ボタン群
        self.show_settings_btn = QPushButton("設定表示")
        self.show_settings_btn.clicked.connect(self._show_settings)
        layout.addWidget(self.show_settings_btn)

        self.reset_settings_btn = QPushButton("設定をリセット")
        self.reset_settings_btn.clicked.connect(self._reset_settings)
        layout.addWidget(self.reset_settings_btn)

        self.manage_form_btn = QPushButton("帳票No管理")
        self.manage_form_btn.clicked.connect(self._manage_form_list)
        layout.addWidget(self.manage_form_btn)

        layout.addStretch(1)

        # 閉じるボタン
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _select_taxpayer_csv(self):
        """納税義務者CSV選択"""
        if self.parent_app:
            self.parent_app.select_taxpayer_csv()
            # パス表示を更新
            if hasattr(self.parent_app, 'taxpayer_csv_path'):
                self.taxpayer_path_label.setText(str(self.parent_app.taxpayer_csv_path))

    def _select_output(self):
        """出力先選択"""
        if self.parent_app:
            self.parent_app.select_output()
            # パス表示を更新
            if hasattr(self.parent_app, 'output_csv'):
                self.output_path_label.setText(str(self.parent_app.output_csv))

    def _show_settings(self):
        """設定表示"""
        if self.parent_app:
            self.parent_app.show_settings_dialog()

    def _reset_settings(self):
        """設定リセット"""
        if self.parent_app:
            self.parent_app.reset_settings()

    def _manage_form_list(self):
        """帳票No管理"""
        if self.parent_app:
            self.parent_app.manage_form_list()


class OCRProgressDialog(QDialog):
    """Small centered dialog with a message and Cancel button.

    This replaces QProgressDialog to give deterministic centered layout
    and avoid unexpected 'canceled' emission on close.
    """

    canceled = Signal()

    def __init__(self, parent=None, message: str = "処理中..."):
        super().__init__(parent)
        self.setWindowTitle("")
        self.setModal(True)
        self._was_canceled = False
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        # layout: centered label and cancel button
        v = QVBoxLayout(self)
        # spinner label (centered) + message
        self._spinner_label = QLabel(self)
        self._spinner_label.setFixedSize(64, 64)
        self._spinner_label.setAlignment(Qt.AlignCenter)
        # text label below spinner
        lbl = QLabel(message, self)
        lbl.setAlignment(Qt.AlignCenter)

        v.addStretch(1)
        v.addWidget(self._spinner_label, 0, Qt.AlignHCenter)
        v.addSpacing(6)
        v.addWidget(lbl)
        v.addSpacing(12)
        btn = QPushButton("キャンセル", self)
        btn.clicked.connect(self._on_cancel)
        # center button horizontally
        hb = QHBoxLayout()
        hb.addStretch(1)
        hb.addWidget(btn)
        hb.addStretch(1)
        v.addLayout(hb)
        v.addStretch(1)

        # prepare a simple programmatic spinner pixmap (no external assets)
        size = 64
        base = QPixmap(size, size)
        base.fill(Qt.transparent)
        p = QPainter(base)
        p.setRenderHint(QPainter.Antialiasing)
        pen_color = self.palette().text().color()
        p.setPen(Qt.NoPen)
        # draw 12 spokes with alpha gradient
        for i in range(12):
            a = 255 - int((i / 12.0) * 200)
            col = QColor(pen_color)
            col.setAlpha(a)
            p.setBrush(col)
            # draw rounded rectangle spoke
            w = size * 0.08
            h = size * 0.28
            p.save()
            p.translate(size / 2, size / 2)
            p.rotate(i * (360 / 12))
            p.drawRoundedRect(int(-w / 2), int(-size / 2 + 6), int(w), int(h), int(w / 2), int(w / 2))
            p.restore()
        p.end()
        self._spinner_base = base
        self._angle = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(80)
        self._spinner_timer.timeout.connect(self._update_spinner)

    def _update_spinner(self) -> None:
        # rotate the base pixmap and show
        if self._spinner_base is None:
            return
        transform = QTransform().rotate(self._angle)
        rotated = self._spinner_base.transformed(transform, Qt.SmoothTransformation)
        # center by scaling if needed
        self._spinner_label.setPixmap(rotated)
        self._angle = (self._angle + 30) % 360

    def show(self) -> None:
        try:
            self._spinner_timer.start()
        except Exception:
            pass
        super().show()

    def close(self) -> None:
        try:
            self._spinner_timer.stop()
        except Exception:
            pass
        super().close()

    def _on_cancel(self) -> None:
        if not self._was_canceled:
            self._was_canceled = True
            self.canceled.emit()

    def was_canceled(self) -> bool:
        return self._was_canceled


class ImageEntryApp(QWidget):
    def __init__(self, input_dir: Path, output_csv: Path) -> None:
        super().__init__()
        self.setWindowTitle("Image Entry")
        self.resize(1200, 700)

        self.input_dir = input_dir
        self.output_csv = output_csv
        # keep initial values for reset
        self._initial_input_dir = Path(input_dir)
        self._initial_output_csv = Path(output_csv)

        # configuration file path. Use multiple fallback locations for robustness.
        self.config_path = self._get_config_path()

        self.records: List[ImageRecord] = []
        self.entries: Dict[str, Dict[str, str]] = {}  # key -> {address, book, index}
        self.zoom = 1.0
        self.fit_to_window = True
        # run OCR in subprocess worker by default so it can be killed on cancel
        self._use_subprocess_ocr = True
        self._ocr_subproc = None
        # currently shown record index in self.records (None when nothing selected)
        self._current_index = None
        # path of the currently displayed image (keeps track even if list selection changes)
        self._current_path = None
        # last item we explicitly styled (for fallback); used to reset styling when selection moves
        self._last_styled_item = None
        
        # 納税義務者情報検索関連(デフォルトパス、設定で変更可能)
        self.taxpayer_records: List[TaxpayerRecord] = []
        self.taxpayer_csv_path = Path("CSV/納税義務者情報.csv")
        # 検索高速化用インデックス
        self._taxpayer_by_year: Dict[str, List[TaxpayerRecord]] = {}
        self._taxpayer_by_number: Dict[str, TaxpayerRecord] = {}
        self._taxpayer_name_index: Dict[str, List[TaxpayerRecord]] = {}

        # UI
        self.list_widget = QListWidget()
        # show filenames only (no thumbnails)
        self.list_widget.setViewMode(QListWidget.ListMode)
        # ensure single-selection so highlight is predictable
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        # rely on the platform default selection appearance; do not force global stylesheet
        # install custom delegate to control drawing consistently
        self.list_widget.setItemDelegate(ListItemDelegate(self.list_widget))

        self.preview_label = PreviewLabel("No Image", parent=self)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(QSize(400, 300))
        # allow the preview to expand when the window grows
        try:
            self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass

        # Fields
        # New fields per user request
        # 業務: fixed to "JA", non-editable
        self.business_input = QLineEdit("JA")
        self.business_input.setReadOnly(True)

        # 年度: show 和暦コード (e.g. 508 for 令和8年). initial value is current year code
        self.year_input = QLineEdit(self._current_wareki_code())

        # 帳票No: combobox populated from a file (if exists) or fallback list
        self.form_combo = QComboBox()
        for v in self._load_form_list():
            self.form_combo.addItem(v)
        # default per user's spec: 給報:050 -> code '050'
        try:
            self._set_form_combo_by_code("050")
        except Exception:
            # best-effort, ignore if helper not present for any reason
            pass

        # 管理No (資料冊号 と同義): fixed to "1", non-editable per request
        self.book_input = QLineEdit("1")
        self.book_input.setReadOnly(True)

        # 資料連番: filled automatically after loading images (1..N)
        self.index_input = QLineEdit()
        self.addr_input = QLineEdit()

        # 多枚数対応帳票コードセット（帳票No管理ダイアログから読み込む。直接入力欄は廃止）
        self._multi_page_set: set = {"040"}

        select_btn = QPushButton("フォルダ選択")
        load_btn = QPushButton("フォルダ再読込")
        save_btn = QPushButton("CSV 出力")
        prev_btn = QPushButton("前へ")
        next_btn = QPushButton("次へ")
        zoom_in_btn = QPushButton("拡大 +")
        zoom_out_btn = QPushButton("縮小 -")
        fit_btn = QPushButton("フィット")
        # avoid buttons stealing focus which can change list selection on some platforms
        zoom_in_btn.setFocusPolicy(Qt.NoFocus)
        zoom_out_btn.setFocusPolicy(Qt.NoFocus)
        fit_btn.setFocusPolicy(Qt.NoFocus)

        # Layouts
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("ファイル一覧"))
        left_layout.addWidget(self.list_widget)
        # current folder label and buttons
        self.dir_label = QLabel(str(self.input_dir))
        left_layout.addWidget(self.dir_label)
        left_layout.addWidget(select_btn)
        left_layout.addWidget(load_btn)
        # Option: include subfolders when loading images
        self.recursive_checkbox = QCheckBox("サブフォルダを含める")
        try:
            self.recursive_checkbox.setChecked(True)
        except Exception:
            pass
        left_layout.addWidget(self.recursive_checkbox)

        right_top_layout = QVBoxLayout()
        right_top_layout.addWidget(self.preview_label, 1)

        # Zoom controls: place directly under the preview. Order: 拡大+, フィット, 縮小-
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(zoom_in_btn)
        try:
            # 固定ピクセル幅にしてレイアウトポリシーで潰されにくくする
            fit_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            fit_btn.setFixedWidth(100)  # 必要に応じて調整してください
        except Exception:
            pass
        zoom_row.addWidget(fit_btn)
        zoom_row.addWidget(zoom_out_btn)
        
        # 範囲選択OCRボタンを追加
        self.ocr_region_btn = QPushButton("範囲選択OCR")
        self.ocr_region_btn.setFocusPolicy(Qt.NoFocus)
        self.ocr_region_btn.setCheckable(False)
        zoom_row.addWidget(self.ocr_region_btn)
        # OCR backend selector (optional). Populate with available backends.
        try:
            self.ocr_backend_combo = QComboBox()
            # Always show known backends in the dropdown. Mark unavailable ones so user can install them.
            known_backends = ["pytesseract", "easyocr", "paddleocr", "yomitoku"]
            # store availability map
            self._ocr_backend_available = {}
            for key in known_backends:
                if key == 'pytesseract':
                    available = (PYTESSERACT_AVAILABLE and PIL_AVAILABLE)
                elif key == 'easyocr':
                    available = EASYOCR_AVAILABLE
                elif key == 'paddleocr':
                    available = PADDLE_AVAILABLE
                elif key == 'yomitoku':
                    available = YOMITOKU_AVAILABLE
                else:
                    available = False
                self._ocr_backend_available[key] = available
                label = key if available else f"{key} (未インストール)"
                # store tuple (backend_key, available) as userData for robust selection
                self.ocr_backend_combo.addItem(label, (key, available))
            # include a 'none' option
            self.ocr_backend_combo.addItem("none", ("none", True))
            # store a reader cache for EasyOCR (lazy init)
            self._easyocr_reader = None
            # default selection (will be overridden by load_settings if present)
            try:
                # select first available backend if any, else 'none'
                # easyocrを優先（Tesseract本体が不要で即座に使える）
                idx = None
                for i in range(self.ocr_backend_combo.count()):
                    d = self.ocr_backend_combo.itemData(i)
                    if isinstance(d, (list, tuple)) and len(d) >= 2:
                        backend_key, available = d[0], d[1]
                        # easyocrが利用可能ならそれを選択
                        if backend_key == 'easyocr' and available:
                            idx = i
                            break
                        # それ以外で最初に利用可能なものを記憶
                        if idx is None and available:
                            idx = i
                
                # 何も見つからなければnoneを選択
                if idx is None:
                    for i in range(self.ocr_backend_combo.count()):
                        d = self.ocr_backend_combo.itemData(i)
                        if isinstance(d, (list, tuple)) and d[0] == 'none':
                            idx = i
                            break
                
                if idx is not None:
                    self.ocr_backend_combo.setCurrentIndex(idx)
                    self.ocr_backend = self.ocr_backend_combo.itemData(idx)[0]
                else:
                    self.ocr_backend = "none"
            except Exception:
                self.ocr_backend = "none"
            # persist selection on change
            try:
                self.ocr_backend_combo.currentIndexChanged.connect(lambda _: self.save_settings())
            except Exception:
                pass
            zoom_row.addWidget(self.ocr_backend_combo)
        except Exception:
            # ignore UI addition failures
            self.ocr_backend_combo = None

        form_layout = QVBoxLayout()
        # Top meta row: 業務 / 年度 / 帳票No 横並び（管理No/資料連番は非表示）
        meta_row = QHBoxLayout()
        meta_row.addWidget(QLabel("業務"))
        meta_row.addWidget(self.business_input)
        meta_row.addSpacing(6)
        meta_row.addWidget(QLabel("年度"))
        meta_row.addWidget(self.year_input)
        meta_row.addSpacing(6)
        meta_row.addWidget(QLabel("帳票No"))
        meta_row.addWidget(self.form_combo)
        # 管理No/資料連番は内部的に保持するが非表示
        self.book_input.setVisible(False)
        self.index_input.setVisible(False)
        form_layout.addLayout(meta_row)

        # 検索機能の追加 - 宛名番号の上に配置
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("宛名番号検索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("宛名番号、氏名、住所で検索...")
        search_row.addWidget(self.search_input, 1)
        self.search_btn = QPushButton("検索")
        self.search_btn.setFixedWidth(60)
        search_row.addWidget(self.search_btn)
        form_layout.addLayout(search_row)
        
        # 検索結果表示用リスト（非表示で初期化）
        self.search_results = QListWidget()
        self.search_results.setMaximumHeight(120)
        self.search_results.setVisible(False)
        form_layout.addWidget(self.search_results)

        # 宛名番号 はメタ行の下に配置（ラベルと入力を横並びにして追随させる）
        addr_row = QHBoxLayout()
        addr_row.addWidget(QLabel("宛名番号 (必須)"))
        try:
            self.addr_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass
        addr_row.addWidget(self.addr_input, 1)
        # 前と同じ宛名番号を設定するボタン（多枚数対応帳票のみ有効）
        self.same_as_prev_btn = QPushButton("前と同じ")
        self.same_as_prev_btn.setToolTip(
            "前のイメージと同じ宛名番号を設定する\n"
            "（多枚数対応帳票のときの続きイメージ指定用）"
        )
        self.same_as_prev_btn.setFixedWidth(75)
        self.same_as_prev_btn.setEnabled(False)
        addr_row.addWidget(self.same_as_prev_btn)
        # Check digit options group
        addr_row.addWidget(QLabel("チェックデジット("))
        self.mod11_checkbox = QCheckBox("mod11")
        try:
            self.mod11_checkbox.setChecked(False)
        except Exception:
            pass
        addr_row.addWidget(self.mod11_checkbox)
        addr_row.addWidget(QLabel(","))
        # Check digit option (checkdeji2 style)
        self.checkdeji_checkbox = QCheckBox("old")
        try:
            self.checkdeji_checkbox.setChecked(False)
        except Exception:
            pass
        addr_row.addWidget(self.checkdeji_checkbox)
        addr_row.addWidget(QLabel(")"))
        form_layout.addLayout(addr_row)

        # remaining buttons: place navigation on single row
        nav_row = QHBoxLayout()
        nav_row.addWidget(prev_btn)
        nav_row.addWidget(next_btn)
        form_layout.addLayout(nav_row)

        # データ出力とオプションボタンを横並び
        save_btn.setText("データ出力")
        options_btn = QPushButton("オプション")
        
        # オプションボタンの幅をOCR選択コンボボックスに合わせる
        if hasattr(self, 'ocr_backend_combo') and self.ocr_backend_combo is not None:
            try:
                options_btn.setFixedWidth(self.ocr_backend_combo.sizeHint().width())
            except Exception:
                pass
        
        button_row = QHBoxLayout()
        button_row.addWidget(save_btn)  # データ出力ボタンは伸縮
        button_row.addWidget(options_btn)  # オプションボタンは固定幅
        form_layout.addLayout(button_row)

        right_layout = QVBoxLayout()
        # preview (stretch), zoom controls under preview, then form
        right_layout.addLayout(right_top_layout, 1)
        right_layout.addLayout(zoom_row)
        right_layout.addLayout(form_layout, 0)

        # 左右のウィジェットを直接配置（スプリッターなしで間隔を完全に詰める）
        left_widget = QWidget()
        left_layout.setContentsMargins(4, 4, 0, 4)  # 右マージン0
        left_layout.setSpacing(2)
        left_widget.setLayout(left_layout)
        # ファイル一覧の幅を最小限に制限（27文字 + 最小マージン）
        try:
            # フォントメトリクスを使用して正確な幅を計算
            fm = self.list_widget.fontMetrics()
            char_width = fm.averageCharWidth()
            list_width = int(char_width * 27) + 8  # 27文字 + 最小マージン
            left_widget.setMaximumWidth(list_width)
            left_widget.setMinimumWidth(list_width)
        except Exception as e:
            # フォールバック: 固定幅
            left_widget.setMaximumWidth(235)
            left_widget.setMinimumWidth(235)
        
        right_widget = QWidget()
        right_layout.setContentsMargins(0, 4, 4, 4)  # 左マージン0
        right_layout.setSpacing(2)
        right_widget.setLayout(right_layout)

        main_layout = QHBoxLayout(self)
        # メインレイアウトのマージンは0、スペーシングで1mm程度の間隔を作る
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)  # 約1mmの間隔
        # スプリッターを使わず直接配置
        main_layout.addWidget(left_widget)
        main_layout.addWidget(right_widget, 1)  # 右側に伸縮性を持たせる

        # Signals
        select_btn.clicked.connect(self.select_folder)
        load_btn.clicked.connect(self.load_images)
        # When the recursive checkbox is toggled, reload the image list immediately and save settings
        try:
            self.recursive_checkbox.stateChanged.connect(self._on_recursive_toggled)
        except Exception:
            pass
        self.list_widget.currentItemChanged.connect(self.on_selection_changed)
        # also handle direct clicks (ensure preview updates on click)
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        self.addr_input.editingFinished.connect(self.auto_save_current)
        # validation: mod11 checkbox and addr input
        try:
            self.mod11_checkbox.stateChanged.connect(lambda _: self.validate_addr_field())
            self.checkdeji_checkbox.stateChanged.connect(lambda _: self.validate_addr_field())
            self.addr_input.textChanged.connect(lambda _: self.validate_addr_field())
            # persist mod11 checkbox changes
            self.mod11_checkbox.stateChanged.connect(lambda _: self.save_settings())
            self.checkdeji_checkbox.stateChanged.connect(lambda _: self.save_settings())
            # persist form and year when changed
            self.form_combo.currentIndexChanged.connect(lambda _: self.save_settings())
            self.form_combo.currentIndexChanged.connect(lambda _: self._update_same_as_prev_btn())
            self.year_input.editingFinished.connect(lambda: self.save_settings())
        except Exception:
            pass
        # オプションボタン
        try:
            options_btn.clicked.connect(self.show_options_dialog)
        except Exception:
            pass
        
        # 範囲選択OCRボタンの接続
        try:
            self.ocr_region_btn.clicked.connect(self.start_region_selection_mode)
        except Exception:
            pass
        try:
            self.addr_input.returnPressed.connect(self.on_addr_return_pressed)
        except Exception:
            pass
        
        # 検索機能のシグナル接続
        try:
            self.search_btn.clicked.connect(self.perform_search)
            self.search_input.textChanged.connect(self.on_search_text_changed)
            self.search_input.returnPressed.connect(self.perform_search)
            self.search_results.itemClicked.connect(self.on_search_result_selected)
        except Exception:
            pass
        self.book_input.editingFinished.connect(self.auto_save_current)
        self.index_input.editingFinished.connect(self.auto_save_current)
        # 前と同じボタン
        self.same_as_prev_btn.clicked.connect(self.set_same_address_as_prev)
        save_btn.clicked.connect(self.save_csv)
        prev_btn.clicked.connect(self.select_previous)
        next_btn.clicked.connect(self.select_next)
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_out_btn.clicked.connect(self.zoom_out)
        fit_btn.clicked.connect(self.fit_image)

        # restore saved settings (may set input_dir/output_csv/checkboxes)
        try:
            self.load_settings()
        except Exception:
            pass
        # then load images
        self.load_images()
        
        # 納税義務者情報CSVを読み込み
        self.load_taxpayer_data()

    def show_options_dialog(self) -> None:
        """オプションダイアログを表示"""
        dlg = OptionsDialog(self)
        dlg.exec()

    def manage_form_list(self) -> None:
        """帳票No一覧を管理するダイアログを表示"""
        current_list = []
        for i in range(self.form_combo.count()):
            current_list.append(self.form_combo.itemText(i))

        dlg = FormListDialog(self, current_list, multi_page_set=self._multi_page_set)
        if dlg.exec() == QDialog.Accepted:
            new_list = dlg.get_form_list()
            new_multi = dlg.get_multi_page_set()

            # 多枚数セットを更新
            self._multi_page_set = new_multi

            # 現在選択されているコードを保存
            current_code = self._form_code_from_label(self.form_combo.currentText())

            # コンボボックスを更新
            self.form_combo.blockSignals(True)
            try:
                self.form_combo.clear()
                for item in new_list:
                    self.form_combo.addItem(item)
                if current_code:
                    for i in range(self.form_combo.count()):
                        if self._form_code_from_label(self.form_combo.itemText(i)) == current_code:
                            self.form_combo.setCurrentIndex(i)
                            break
            finally:
                self.form_combo.blockSignals(False)

            # 設定を保存
            self._save_form_list(new_list)
            self.save_settings()

    def show_settings_dialog(self) -> None:
        """Show current config file contents in a read-only dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle("現在の設定")
        te = QTextEdit(dlg)
        te.setReadOnly(True)
        te.setMinimumSize(600, 400)
        content = {}
        try:
            if self.config_path.exists():
                with self.config_path.open("r", encoding="utf-8") as fh:
                    content = json.load(fh)
            else:
                content = {"note": "設定ファイルは存在しません"}
        except Exception:
            content = {"error": "設定の読み込みに失敗しました"}
        try:
            te.setText(json.dumps(content, ensure_ascii=False, indent=2))
        except Exception:
            te.setText(str(content))
        layout = QVBoxLayout(dlg)
        layout.addWidget(te)
        dlg.setLayout(layout)
        dlg.exec()

    def reset_settings(self) -> None:
        """Reset settings to defaults and remove config file after user confirmation."""
        ret = QMessageBox.question(self, "設定リセット", "設定を初期化してデフォルトに戻しますか？\n（保存済みの設定ファイルは削除されます）", QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        # remove config file if exists
        try:
            if self.config_path.exists():
                # clear hidden attribute first (best-effort) so deletion is visible/allowed
                try:
                    _clear_hidden(self.config_path)
                except Exception:
                    pass
                self.config_path.unlink()
        except Exception:
            logger.exception("設定ファイルの削除に失敗しました")
        # reset UI to defaults (block signals to avoid intermediate saves)
        try:
            self.recursive_checkbox.blockSignals(True)
            self.mod11_checkbox.blockSignals(True)
            self.checkdeji_checkbox.blockSignals(True)
            try:
                self.recursive_checkbox.setChecked(True)
                self.mod11_checkbox.setChecked(False)
                self.checkdeji_checkbox.setChecked(False)
            finally:
                self.recursive_checkbox.blockSignals(False)
                self.mod11_checkbox.blockSignals(False)
                self.checkdeji_checkbox.blockSignals(False)
            # reset output/input to initial values
            self.input_dir = Path(self._initial_input_dir)
            self.output_csv = Path(self._initial_output_csv)
            
            # reset form list to defaults
            try:
                default_forms = FormListDialog.DEFAULT_FORMS.copy()
                self._save_form_list(default_forms)
                self.form_combo.blockSignals(True)
                try:
                    self.form_combo.clear()
                    for item in default_forms:
                        self.form_combo.addItem(item)
                finally:
                    self.form_combo.blockSignals(False)
            except Exception:
                pass
            
            # reset form and year
            try:
                self._set_form_combo_by_code("050")
            except Exception:
                pass
            self.year_input.setText(self._current_wareki_code())
            # apply geometry reset (center on screen with default size)
            try:
                self.resize(1200, 700)
                # optional: center
                screen = QApplication.primaryScreen()
                if screen is not None:
                    geo = screen.availableGeometry()
                    x = geo.x() + (geo.width() - self.width()) // 2
                    y = geo.y() + (geo.height() - self.height()) // 2
                    self.move(x, y)
            except Exception:
                pass
        except Exception:
            pass
        # reload images and save (will recreate config on next save)
        try:
            self.load_images()
            self.save_settings()
        except Exception:
            pass

    def start_region_selection_mode(self) -> None:
        """範囲選択モードを開始する。"""
        try:
            # 範囲選択モードを有効化
            self.preview_label.enable_selection_mode()
            self.ocr_region_btn.setText("選択中...")
            self.ocr_region_btn.setEnabled(False)
        except Exception as e:
            logger.exception("範囲選択モード開始エラー")
    
    def on_region_selected(self, region: tuple) -> None:
        """範囲が選択された時に呼ばれる。"""
        try:
            # 範囲選択モードを無効化
            self.preview_label.disable_selection_mode()
            self.ocr_region_btn.setText("範囲選択OCR")
            self.ocr_region_btn.setEnabled(True)
            
            # OCRを実行
            if region:
                self.perform_region_ocr_async(region)
        except Exception as e:
            logger.exception("範囲選択完了エラー")
            self.preview_label.disable_selection_mode()
            self.ocr_region_btn.setText("範囲選択OCR")
            self.ocr_region_btn.setEnabled(True)
    
    def perform_region_ocr_async(self, region: tuple) -> None:
        """選択された範囲でOCRを非同期実行する。
        
        Args:
            region: (x, y, width, height) のタプル
        """
        # 現在のレコードを取得
        rec = None
        if self._current_path is not None:
            rec = next((r for r in self.records if r.path == self._current_path), None)
        if rec is None:
            cur = self.list_widget.currentItem()
            if cur:
                filename = cur.text()
                rec = next((r for r in self.records if r.filename == filename), None)
        if rec is None:
            QMessageBox.information(self, "OCR", "対象の画像が選択されていません")
            return
        
        # 一時的に切り出した画像を保存
        try:
            from PIL import Image
            img = Image.open(str(rec.path))
            x, y, w, h = region
            
            # 画像サイズの検証（yomitokuなどは最小サイズ要件がある）
            if w < 10 or h < 10:
                QMessageBox.warning(self, "範囲が小さすぎます", 
                    f"選択範囲が小さすぎます ({w}x{h}px)。\nより大きな範囲を選択してください。")
                return
            
            cropped = img.crop((x, y, x + w, y + h))
            
            # 一時ファイルに保存
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name
                cropped.save(tmp_path)
            
            # 一時的なImageRecordを作成してOCR実行
            from dataclasses import replace
            temp_rec = replace(rec, path=Path(tmp_path))
            
            # 進捗ダイアログを表示
            try:
                self.ocr_region_btn.setEnabled(False)
            except Exception:
                pass
            
            try:
                self._ocr_progress = OCRProgressDialog(self, message="範囲OCR実行中...")
                self._ocr_progress.canceled.connect(self._cancel_ocr)
                self._ocr_progress.show()
            except Exception:
                self._ocr_progress = None
            
            # ワーカースレッドを開始
            try:
                self._ocr_user_cancelled = False
                self._ocr_thread = OCRThread(self, temp_rec)
                self._ocr_thread.finished.connect(lambda text: self._on_region_ocr_finished(text, tmp_path))
                self._ocr_thread.error.connect(lambda err: self._on_region_ocr_error(err, tmp_path))
                try:
                    self._ocr_thread.finished.connect(self._ocr_thread.deleteLater)
                    self._ocr_thread.error.connect(self._ocr_thread.deleteLater)
                except Exception:
                    pass
                self._ocr_thread.start()
            except Exception as exc:
                # クリーンアップ
                try:
                    if self._ocr_progress:
                        self._ocr_progress.close()
                except Exception:
                    pass
                try:
                    self.ocr_region_btn.setEnabled(True)
                except Exception:
                    pass
                try:
                    Path(tmp_path).unlink()
                except Exception:
                    pass
                logger.exception("範囲OCR スレッド開始に失敗しました")
                QMessageBox.critical(self, "OCR エラー", f"範囲OCR スレッドの開始に失敗しました: {exc}")
        
        except Exception as e:
            logger.exception("範囲OCR実行エラー")
            QMessageBox.critical(self, "OCR エラー", f"範囲OCRの実行に失敗しました: {e}")
    
    def _on_region_ocr_finished(self, text: str, tmp_path: str) -> None:
        """範囲OCR完了時の処理。"""
        # 進捗ダイアログを閉じる
        try:
            if getattr(self, '_ocr_progress', None):
                self._ocr_progress.close()
        except Exception:
            pass
        try:
            self.ocr_region_btn.setEnabled(True)
        except Exception:
            pass
        
        # 一時ファイルを削除
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass
        
        # 結果ダイアログを表示
        try:
            self.show_ocr_result_dialog(text)
        except Exception:
            QMessageBox.information(self, "OCR", "処理は完了しましたが結果表示に失敗しました。")
    
    def _on_region_ocr_error(self, err: str, tmp_path: str) -> None:
        """範囲OCRエラー時の処理。"""
        try:
            if getattr(self, '_ocr_progress', None):
                self._ocr_progress.close()
        except Exception:
            pass
        try:
            self.ocr_region_btn.setEnabled(True)
        except Exception:
            pass
        
        # 一時ファイルを削除
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass
        
        logger.error("範囲OCR 実行エラー: %s", err)
        
        # エラーメッセージを簡潔に
        error_msg = err
        if "Image size is too small" in err:
            error_msg = "選択範囲が小さすぎます。より大きな範囲を選択してください。"
        elif "YomiToku" in err and len(err) > 500:
            # 長いスタックトレースを簡潔に
            if "Image size is too small" in err:
                error_msg = "YomiToku: 選択範囲が小さすぎます。より大きな範囲を選択してください。"
            else:
                error_msg = "YomiToku: OCR実行に失敗しました。別のOCRバックエンドを試してください。"
        
        try:
            QMessageBox.critical(self, "OCR エラー", f"範囲OCR 実行中にエラーが発生しました:\n{error_msg}")
        except Exception:
            pass
    
    def perform_ocr_for_current(self) -> None:
        """Run OCR for the currently shown image and show results in a dialog."""
        # determine current record
        rec = None
        if self._current_path is not None:
            rec = next((r for r in self.records if r.path == self._current_path), None)
        if rec is None:
            cur = self.list_widget.currentItem()
            if cur:
                filename = cur.text()
                rec = next((r for r in self.records if r.filename == filename), None)
        if rec is None:
            QMessageBox.information(self, "OCR", "対象の画像が選択されていません")
            return
        # perform OCR
        try:
            text = self.perform_ocr(rec)
        except Exception as exc:
            logger.exception("OCR 実行中にエラー")
            QMessageBox.critical(self, "OCR エラー", f"OCR 実行中にエラーが発生しました: {exc}")
            return
        # show results and allow user to apply
        self.show_ocr_result_dialog(text)

    def perform_ocr_for_current_async(self) -> None:
        """Start OCR in a background thread and show a progress dialog."""
        # determine current record (same logic as sync version)
        rec = None
        if self._current_path is not None:
            rec = next((r for r in self.records if r.path == self._current_path), None)
        if rec is None:
            cur = self.list_widget.currentItem()
            if cur:
                filename = cur.text()
                rec = next((r for r in self.records if r.filename == filename), None)
        if rec is None:
            QMessageBox.information(self, "OCR", "対象の画像が選択されていません")
            return

        # disable OCR button to prevent re-entry
        try:
            self.ocr_btn.setEnabled(False)
        except Exception:
            pass

        # create centered progress dialog (custom) to avoid accidental canceled() emission
        try:
            self._ocr_progress = OCRProgressDialog(self, message="OCR 実行中...")
            self._ocr_progress.canceled.connect(self._cancel_ocr)
            self._ocr_progress.show()
        except Exception:
            self._ocr_progress = None

        # start worker thread
        try:
            # reset cancel flag
            self._ocr_user_cancelled = False
            self._ocr_thread = OCRThread(self, rec)
            self._ocr_thread.finished.connect(self._on_ocr_finished)
            self._ocr_thread.error.connect(self._on_ocr_error)
            # ensure thread object is cleaned up when done
            try:
                self._ocr_thread.finished.connect(self._ocr_thread.deleteLater)
                self._ocr_thread.error.connect(self._ocr_thread.deleteLater)
            except Exception:
                pass
            self._ocr_thread.start()
        except Exception as exc:
            # re-enable and close progress
            try:
                if self._ocr_progress:
                    self._ocr_progress.close()
            except Exception:
                pass
            try:
                self.ocr_btn.setEnabled(True)
            except Exception:
                pass
            logger.exception("OCR スレッド開始に失敗しました")
            QMessageBox.critical(self, "OCR エラー", f"OCR スレッドの開始に失敗しました: {exc}")

    def _cancel_ocr(self) -> None:
        """User requested cancel. Mark a flag; do not show an immediate message to avoid false positives.

        The heavy OCR routine may not be interruptible; this flag is available for later handling.
        """
        try:
            # mark user cancel flag; main thread handlers can check this
            self._ocr_user_cancelled = True
            # kill subprocess if running so cancellation is immediate
            proc = getattr(self, '_ocr_subproc', None)
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.kill()
                except Exception:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
            # disable cancel control visually if custom dialog is used
            if getattr(self, '_ocr_progress', None) and hasattr(self._ocr_progress, 'was_canceled'):
                # dialog may keep internal state; nothing else needed here
                pass
        except Exception:
            pass

    def _on_ocr_finished(self, text: str) -> None:
        # close progress and re-enable
        try:
            if getattr(self, '_ocr_progress', None):
                self._ocr_progress.close()
        except Exception:
            pass
        try:
            self.ocr_btn.setEnabled(True)
        except Exception:
            pass
        # show results dialog
        try:
            self.show_ocr_result_dialog(text)
        except Exception:
            QMessageBox.information(self, "OCR", "処理は完了しましたが結果表示に失敗しました。")

    def _on_ocr_error(self, err: str) -> None:
        try:
            if getattr(self, '_ocr_progress', None):
                self._ocr_progress.close()
        except Exception:
            pass
        try:
            self.ocr_btn.setEnabled(True)
        except Exception:
            pass
        logger.error("OCR 実行エラー: %s", err)
        try:
            QMessageBox.critical(self, "OCR エラー", f"OCR 実行中にエラーが発生しました:\n{err}")
        except Exception:
            pass

    def perform_ocr(self, rec: ImageRecord) -> str:
        """Perform OCR on the given ImageRecord and return extracted text.

        Supports multiple backends: 'pytesseract' (requires pytesseract + Pillow) and 'easyocr'.
        The active backend is chosen from the UI combo (if present) or from
        self.ocr_backend. Raises RuntimeError when no suitable backend is available.
        """
        # determine backend selection
        backend = None
        if hasattr(self, 'ocr_backend_combo') and self.ocr_backend_combo is not None:
            try:
                idx = self.ocr_backend_combo.currentIndex()
                data = self.ocr_backend_combo.itemData(idx)
                if isinstance(data, (list, tuple)):
                    backend = data[0]
                else:
                    backend = str(self.ocr_backend_combo.currentText())
            except Exception:
                backend = getattr(self, 'ocr_backend', None)
        else:
            backend = getattr(self, 'ocr_backend', None)

        # If configured, run OCR in a separate worker process so it can be killed on cancel.
        if getattr(self, '_use_subprocess_ocr', False):
            try:
                worker = Path(__file__).resolve().parent.parent / 'ocr_worker.py'
            except Exception:
                worker = Path('ocr_worker.py')
            if worker.exists():
                cmd = [sys.executable, str(worker), '--backend', backend or '', '--image', str(rec.path)]
                env = os.environ.copy()
                env.setdefault('PYTHONUTF8', '1')
                env.setdefault('PYTHONIOENCODING', 'utf-8')
                try:
                    # run in binary mode to avoid parent-side decoding using cp932 on Windows
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False, env=env)
                    # keep handle so main thread can kill it on cancel
                    self._ocr_subproc = proc
                    out_bytes, err_bytes = proc.communicate()
                    ret = proc.returncode
                    self._ocr_subproc = None
                    # decode using UTF-8; replace invalid sequences to avoid UnicodeDecodeError
                    try:
                        out = out_bytes.decode('utf-8', errors='replace') if out_bytes is not None else ''
                    except Exception:
                        out = str(out_bytes)
                    try:
                        err = err_bytes.decode('utf-8', errors='replace') if err_bytes is not None else ''
                    except Exception:
                        err = str(err_bytes)
                    if ret != 0:
                        msg = (err or out or '').strip()
                        raise RuntimeError(f'OCR worker failed (code={ret}): {msg}')
                    return out
                except Exception as e:
                    # ensure subprocess is cleaned up
                    try:
                        if getattr(self, '_ocr_subproc', None) and self._ocr_subproc.poll() is None:
                            self._ocr_subproc.kill()
                    except Exception:
                        pass
                    raise

        if backend == 'easyocr':
            if not EASYOCR_AVAILABLE:
                raise RuntimeError('EasyOCR がインストールされていません。easyocr をインストールしてください。')
            # lazy-init reader (may download models on first run)
            if getattr(self, '_easyocr_reader', None) is None:
                try:
                    easyocr = __import__('easyocr')
                except Exception as e:
                    raise RuntimeError(f'EasyOCR import failed: {e}')
                # prefer Japanese+English if available
                try:
                    self._easyocr_reader = easyocr.Reader(['ja', 'en'], gpu=False)
                except Exception:
                    # fallback to English-only
                    self._easyocr_reader = easyocr.Reader(['en'], gpu=False)
            try:
                # detail=0 returns only text lines; paragraph=True attempts to join
                res = self._easyocr_reader.readtext(str(rec.path), detail=0, paragraph=True)
                if isinstance(res, (list, tuple)):
                    text = "\n".join([str(x) for x in res])
                else:
                    text = str(res)
            except Exception as exc:
                raise RuntimeError(f"EasyOCR 実行中にエラーが発生しました: {exc}")
            return text

        if backend == 'pytesseract':
            if not (PYTESSERACT_AVAILABLE and PIL_AVAILABLE):
                raise RuntimeError('pytesseract または Pillow が利用できません。pytesseract, Pillow と Tesseract 本体をインストールしてください。')
            try:
                pytesseract = __import__('pytesseract')
                PIL_mod = __import__('PIL')
                PILImage = getattr(PIL_mod, 'Image')
            except Exception as e:
                raise RuntimeError(f'pytesseract/Pillow import failed: {e}')
            # load with PIL (handle multi-frame by selecting first frame)
            img = PILImage.open(str(rec.path))
            try:
                if getattr(img, 'n_frames', 1) > 1:
                    img.seek(0)
            except Exception:
                pass
            try:
                text = pytesseract.image_to_string(img, lang='jpn+eng')
            except Exception:
                # fallback to default language
                text = pytesseract.image_to_string(img)
            return text

        if backend == 'paddleocr':
            if not PADDLE_AVAILABLE:
                raise RuntimeError('PaddleOCR がインストールされていません。paddleocr と paddlepaddle をインストールしてください。')
            # lazy-init PaddleOCR instance (CPU)
            if getattr(self, '_paddleocr_reader', None) is None:
                # initialize PaddleOCR with best-effort args across versions
                try:
                    paddleocr_mod = __import__('paddleocr')
                    PaddleOCR = getattr(paddleocr_mod, 'PaddleOCR')
                except Exception as e:
                    raise RuntimeError(f'PaddleOCR import failed: {e}')
                try:
                    # recent versions prefer use_textline_orientation
                    self._paddleocr_reader = PaddleOCR(use_textline_orientation=True)
                except Exception:
                    try:
                        # older versions used use_angle_cls
                        self._paddleocr_reader = PaddleOCR(use_angle_cls=True)
                    except Exception:
                        try:
                            # fallback to no-arg constructor
                            self._paddleocr_reader = PaddleOCR()
                        except Exception as exc:
                            raise RuntimeError(f'PaddleOCR の初期化に失敗しました: {exc}')
            try:
                # Try the high-level .ocr() call first (older API)
                try:
                    res = self._paddleocr_reader.ocr(str(rec.path))
                except TypeError:
                    # some versions forward kwargs to predict() which may not accept them;
                    # fall back to predict() without extra kwargs
                    res = self._paddleocr_reader.predict(str(rec.path))

                # Normalize result to a list of text strings.
                texts = []
                # Common format: list of [box, (text, score)] or nested lists
                if isinstance(res, (list, tuple)):
                    for item in res:
                        try:
                            # item may be [box, (text, score)]
                            if isinstance(item, (list, tuple)) and len(item) >= 2:
                                cand = item[1]
                                if isinstance(cand, (list, tuple)) and len(cand) >= 1:
                                    texts.append(str(cand[0]))
                                elif isinstance(cand, str):
                                    texts.append(cand)
                                else:
                                    # fallback: stringify item
                                    texts.append(str(item))
                            elif isinstance(item, str):
                                texts.append(item)
                            else:
                                texts.append(str(item))
                        except Exception:
                            # best-effort flatten
                            def _collect(o):
                                if isinstance(o, str):
                                    texts.append(o)
                                elif isinstance(o, (list, tuple)):
                                    for e in o:
                                        _collect(e)
                            _collect(item)
                else:
                    # unexpected type — stringify
                    texts.append(str(res))

                text = "\n".join(t for t in texts if t)
            except Exception as exc:
                raise RuntimeError(f'PaddleOCR 実行中にエラーが発生しました: {exc}')
            return text

        if backend == 'yomitoku':
            # Prefer CLI invocation which supports -f json for structured output.
            exe = shutil.which('yomitoku') or shutil.which('yomitoku.exe')
            tmp_out = None
            try:
                if exe:
                    tmp_out = tempfile.mkdtemp(prefix='yomitoku_out_')
                    # build command: request JSON output and write to tmp_out
                    cmd = [exe, str(rec.path), '-f', 'json', '-o', tmp_out, '--ignore_line_break']
                    # run CLI
                    # Force UTF-8 for the subprocess to avoid cp932 decode errors on Windows
                    env = os.environ.copy()
                    # PYTHONUTF8 ensures internal Python IO uses UTF-8; PYTHONIOENCODING sets streams
                    env.setdefault("PYTHONUTF8", "1")
                    env.setdefault("PYTHONIOENCODING", "utf-8")
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
                    if proc.returncode != 0:
                        # CLI failed; capture stderr for diagnostics and try python package as fallback
                        cli_err = proc.stderr.strip() or proc.stdout.strip()
                        raise RuntimeError(f'YomiToku CLI が非ゼロ終了: {proc.returncode}, stderr: {cli_err}')
                    # find a JSON file under the output dir
                    matches = glob.glob(os.path.join(tmp_out, '**', '*.json'), recursive=True)
                    if not matches:
                        # if no json, try markdown/csv/html
                        matches = glob.glob(os.path.join(tmp_out, '**', '*.md'), recursive=True)
                    if not matches:
                        matches = glob.glob(os.path.join(tmp_out, '**', '*.csv'), recursive=True)
                    if not matches:
                        # nothing produced; fallback to returning stdout
                        if proc.stdout:
                            return proc.stdout.strip()
                        raise RuntimeError('YomiToku が出力を生成しませんでした')
                    out_file = matches[0]
                    ext = os.path.splitext(out_file)[1].lower()
                    
                    # 共通のクリーニング関数
                    def clean_yomitoku_output(text: str) -> str:
                        """yomitokuの出力をクリーニング"""
                        import re
                        
                        # まず行ごとに処理
                        lines = text.split('\n')
                        cleaned_lines = []
                        seen_lines = set()
                        
                        for line in lines:
                            stripped = line.strip()
                            
                            # "horizontal" のみの行を完全に削除
                            if stripped.lower() == 'horizontal':
                                continue
                            
                            # horizontalを含むマーカーを削除
                            stripped = re.sub(r'<horizontal[^>]*>.*?</horizontal>', '', stripped, flags=re.DOTALL | re.IGNORECASE)
                            stripped = re.sub(r'\[horizontal\].*?\[/horizontal\]', '', stripped, flags=re.DOTALL | re.IGNORECASE)
                            stripped = re.sub(r'^\s*horizontal:\s*', '', stripped, flags=re.IGNORECASE)
                            stripped = re.sub(r'\bhorizontal\b', '', stripped, flags=re.IGNORECASE)
                            stripped = stripped.strip()
                            
                            # 空行はスキップ
                            if not stripped:
                                continue
                            
                            # 重複行を削除（連続していなくても）
                            if stripped not in seen_lines:
                                cleaned_lines.append(stripped)
                                seen_lines.add(stripped)
                        
                        return '\n'.join(cleaned_lines).strip()
                    
                    if ext == '.json':
                        try:
                            with open(out_file, 'r', encoding='utf-8') as fh:
                                doc = json.load(fh)
                        except Exception as exc:
                            raise RuntimeError(f'出力 JSON の読み込みに失敗しました: {exc}')
                        # Flatten any string values found in the JSON into lines
                        texts = []
                        def _collect_strings(o):
                            if isinstance(o, str):
                                # 各文字列からhorizontalを除去
                                cleaned = o.strip()
                                if cleaned.lower() != 'horizontal' and cleaned:
                                    texts.append(cleaned)
                            elif isinstance(o, dict):
                                for v in o.values():
                                    _collect_strings(v)
                            elif isinstance(o, (list, tuple)):
                                for e in o:
                                    _collect_strings(e)
                        _collect_strings(doc)
                        raw_text = '\n'.join(texts)
                        return clean_yomitoku_output(raw_text)
                    else:
                        # md/csv/html: return raw file content
                        try:
                            with open(out_file, 'r', encoding='utf-8', errors='replace') as fh:
                                content = fh.read()
                                return clean_yomitoku_output(content)
                        except Exception as exc:
                            raise RuntimeError(f'出力ファイルの読み取りに失敗しました: {exc}')
                # if CLI not found or CLI failed above, try Python package API if available
            except Exception as cli_exc:
                # Try Python package API if available (lazy import)
                try:
                    yomitoku_mod = __import__('yomitoku')
                except Exception:
                    # no python package available; re-raise CLI error
                    raise RuntimeError(f'YomiToku 実行エラー: {cli_exc}')
                try:
                    # Try a few common API entry points
                    if hasattr(yomitoku_mod, 'run') and callable(yomitoku_mod.run):
                        res = yomitoku_mod.run(str(rec.path))
                    elif hasattr(yomitoku_mod, 'recognize') and callable(yomitoku_mod.recognize):
                        res = yomitoku_mod.recognize(str(rec.path))
                    elif hasattr(yomitoku_mod, 'ocr') and callable(yomitoku_mod.ocr):
                        res = yomitoku_mod.ocr(str(rec.path))
                    elif hasattr(yomitoku_mod, 'read_text') and callable(yomitoku_mod.read_text):
                        res = yomitoku_mod.read_text(str(rec.path))
                    else:
                        # try class-based client
                        Cls = getattr(yomitoku_mod, 'YomiToku', None) or getattr(yomitoku_mod, 'Client', None)
                        if Cls:
                            try:
                                inst = Cls()
                            except Exception:
                                inst = Cls
                            if hasattr(inst, 'run'):
                                res = inst.run(str(rec.path))
                            elif hasattr(inst, 'recognize'):
                                res = inst.recognize(str(rec.path))
                            elif hasattr(inst, 'ocr'):
                                res = inst.ocr(str(rec.path))
                            else:
                                raise RuntimeError('YomiToku Python API の適切なエントリポイントが見つかりませんでした')
                        else:
                            raise RuntimeError('YomiToku Python API の適切なエントリポイントが見つかりませんでした')
                    # normalize result
                    if isinstance(res, (list, tuple)):
                        return '\n'.join(map(str, res))
                    if isinstance(res, dict):
                        texts = []
                        def _collect(o):
                            if isinstance(o, str):
                                texts.append(o)
                            elif isinstance(o, dict):
                                for v in o.values():
                                    _collect(v)
                            elif isinstance(o, (list, tuple)):
                                for e in o:
                                    _collect(e)
                        _collect(res)
                        return '\n'.join(t for t in texts if t)
                    return str(res)
                except Exception as py_exc:
                    raise RuntimeError(f'YomiToku 実行エラー (cli: {cli_exc} / python-api: {py_exc})')
                # neither CLI nor Python API succeeded
                raise RuntimeError(f'YomiToku 実行エラー: {cli_exc}')
            finally:
                if tmp_out and os.path.isdir(tmp_out):
                        try:
                            shutil.rmtree(tmp_out)
                        except Exception:
                            pass

        # no backend
        raise RuntimeError('利用可能な OCR バックエンドが選択されていません。設定で pytesseract か easyocr を選択してください。')

    def show_ocr_result_dialog(self, text: str) -> None:
        """Dialog to display OCR text and allow applying to addr_input."""
        dlg = QDialog(self)
        dlg.setWindowTitle("OCR 結果")
        te = QTextEdit(dlg)
        te.setPlainText(text)
        te.setMinimumSize(600, 400)
        # buttons
        apply_btn = QPushButton("宛名番号欄に適用")
        close_btn = QPushButton("閉じる")

        def on_apply():
            val = te.toPlainText().strip()
            if val:
                # apply full text to search input; user can edit later
                self.search_input.setText(val)
            dlg.accept()

        apply_btn.clicked.connect(on_apply)
        close_btn.clicked.connect(dlg.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(close_btn)

        layout = QVBoxLayout(dlg)
        layout.addWidget(te)
        layout.addLayout(btn_row)
        dlg.setLayout(layout)
        dlg.exec()

    def _on_recursive_toggled(self, _state) -> None:
        """Reload images and save settings when recursive checkbox is toggled."""
        try:
            self.load_images()
        except Exception:
            pass
        try:
            self.save_settings()
        except Exception:
            pass

    def load_settings(self) -> None:
        """Load persistent settings from JSON if available.

        Supported keys:
        - recursive (bool)
        - mod11 (bool)
        - output_csv (str)
        - input_dir (str)
        """
        if not self.config_path.exists():
            return
        try:
            with self.config_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return
        # apply values with signal blocking to avoid side-effects during load
        try:
            if "recursive" in data:
                self.recursive_checkbox.blockSignals(True)
                try:
                    self.recursive_checkbox.setChecked(bool(data.get("recursive", True)))
                finally:
                    self.recursive_checkbox.blockSignals(False)
            if "mod11" in data:
                self.mod11_checkbox.blockSignals(True)
                try:
                    self.mod11_checkbox.setChecked(bool(data.get("mod11", False)))
                finally:
                    self.mod11_checkbox.blockSignals(False)
            if "checkdeji" in data:
                self.checkdeji_checkbox.blockSignals(True)
                try:
                    self.checkdeji_checkbox.setChecked(bool(data.get("checkdeji", False)))
                finally:
                    self.checkdeji_checkbox.blockSignals(False)
            if "output_csv" in data:
                try:
                    p = Path(data.get("output_csv"))
                    if p.parent.exists():
                        self.output_csv = p
                except Exception:
                    pass
            # 帳票No一覧を読み込んでコンボボックスを更新
            if "form_list" in data:
                try:
                    form_list = data.get("form_list", [])
                    if isinstance(form_list, list) and form_list:
                        self.form_combo.blockSignals(True)
                        try:
                            self.form_combo.clear()
                            for item in form_list:
                                self.form_combo.addItem(item)
                        finally:
                            self.form_combo.blockSignals(False)
                except Exception:
                    pass
            
            if "form" in data:
                try:
                    # block signals to avoid saving while applying
                    self.form_combo.blockSignals(True)
                    try:
                        self._set_form_combo_by_code(str(data.get("form")))
                    finally:
                        self.form_combo.blockSignals(False)
                except Exception:
                    pass
            if "year" in data:
                try:
                    self.year_input.blockSignals(True)
                    try:
                        self.year_input.setText(str(data.get("year", self._current_wareki_code())))
                    finally:
                        self.year_input.blockSignals(False)
                except Exception:
                    pass
            if "multi_page_forms" in data:
                try:
                    raw = str(data.get("multi_page_forms", "040"))
                    self._multi_page_set = {
                        s.strip() for s in raw.split(",") if s.strip()
                    }
                except Exception:
                    pass
            if "geom" in data:
                try:
                    g = data.get("geom", {})
                    x = int(g.get("x", 0))
                    y = int(g.get("y", 0))
                    w = int(g.get("w", self.width()))
                    h = int(g.get("h", self.height()))
                    # apply geometry
                    try:
                        self.setGeometry(x, y, w, h)
                    except Exception:
                        self.resize(w, h)
                except Exception:
                    pass
            if "input_dir" in data:
                try:
                    d = Path(data.get("input_dir"))
                    if d.exists():
                        self.input_dir = d
                except Exception:
                    pass
            if "taxpayer_csv_path" in data:
                try:
                    csv_path = Path(data.get("taxpayer_csv_path"))
                    if csv_path.exists():
                        self.taxpayer_csv_path = csv_path
                        self.load_taxpayer_data()
                except Exception:
                    pass
            if "ocr_backend" in data:
                try:
                    val = str(data.get("ocr_backend", ""))
                    # ラベル表示から実際のバックエンド名を抽出（例: "easyocr" または "pytesseract (未インストール)"）
                    backend_key = val
                    if " " in val:
                        # ラベルに "(未インストール)" などが含まれる場合は最初の単語を取得
                        backend_key = val.split()[0]
                    
                    # apply to combo if present
                    if hasattr(self, 'ocr_backend_combo') and self.ocr_backend_combo is not None:
                        try:
                            self.ocr_backend_combo.blockSignals(True)
                            try:
                                # Try to match stored backend key against itemData tuples added when the
                                # combo was populated (itemData = (backend_key, available)). This handles
                                # labels that include "(未インストール)" and legacy saved text values.
                                idx = None
                                for i in range(self.ocr_backend_combo.count()):
                                    d = self.ocr_backend_combo.itemData(i)
                                    if isinstance(d, (list, tuple)) and len(d) > 0:
                                        try:
                                            if str(d[0]) == backend_key:
                                                # 利用可能なバックエンドのみ選択
                                                if len(d) >= 2 and d[1]:
                                                    idx = i
                                                    break
                                        except Exception:
                                            pass
                                
                                # 見つからない、または利用不可の場合は利用可能なものを自動選択
                                if idx is None:
                                    # easyocrを優先的に探す
                                    for i in range(self.ocr_backend_combo.count()):
                                        d = self.ocr_backend_combo.itemData(i)
                                        if isinstance(d, (list, tuple)) and len(d) >= 2:
                                            if d[0] == 'easyocr' and d[1]:
                                                idx = i
                                                break
                                    
                                    # easyocrがなければ他の利用可能なものを探す
                                    if idx is None:
                                        for i in range(self.ocr_backend_combo.count()):
                                            d = self.ocr_backend_combo.itemData(i)
                                            if isinstance(d, (list, tuple)) and len(d) >= 2:
                                                if d[1]:  # 利用可能
                                                    idx = i
                                                    break
                                
                                if idx is not None:
                                    self.ocr_backend_combo.setCurrentIndex(idx)
                                    self.ocr_backend = self.ocr_backend_combo.itemData(idx)[0]
                                else:
                                    # noneを選択
                                    for i in range(self.ocr_backend_combo.count()):
                                        d = self.ocr_backend_combo.itemData(i)
                                        if isinstance(d, (list, tuple)) and d[0] == 'none':
                                            self.ocr_backend_combo.setCurrentIndex(i)
                                            self.ocr_backend = 'none'
                                            break
                            finally:
                                self.ocr_backend_combo.blockSignals(False)
                        except Exception:
                            pass
                    else:
                        self.ocr_backend = backend_key
                except Exception:
                    pass
        except Exception:
            pass

    def save_settings(self) -> None:
        """Save current settings to JSON file.

        We persist only a minimal set: recursive, mod11, checkdeji, output_csv, input_dir.
        """
        # OCRバックエンドキーを取得（ラベルではなくキーを保存）
        ocr_backend_key = getattr(self, 'ocr_backend', 'none')
        if hasattr(self, 'ocr_backend_combo') and self.ocr_backend_combo is not None:
            try:
                idx = self.ocr_backend_combo.currentIndex()
                data = self.ocr_backend_combo.itemData(idx)
                if isinstance(data, (list, tuple)) and len(data) > 0:
                    ocr_backend_key = str(data[0])
            except Exception:
                pass
        
        data = {
            "recursive": bool(self.recursive_checkbox.isChecked()),
            "mod11": bool(self.mod11_checkbox.isChecked()),
            "checkdeji": bool(self.checkdeji_checkbox.isChecked()),
            "output_csv": str(self.output_csv) if self.output_csv is not None else "",
            "input_dir": str(self.input_dir) if self.input_dir is not None else "",
            "taxpayer_csv_path": str(self.taxpayer_csv_path) if self.taxpayer_csv_path is not None else "",
            "form": self._form_code_from_label(self.form_combo.currentText()),
            "year": str(self.year_input.text()).strip(),
            "multi_page_forms": ",".join(sorted(self._multi_page_set)),
            # OCR backend selection (pytesseract | easyocr | none) - キーのみ保存
            "ocr_backend": ocr_backend_key,
            "geom": {
                "x": int(self.geometry().x()),
                "y": int(self.geometry().y()),
                "w": int(self.geometry().width()),
                "h": int(self.geometry().height()),
            },
        }
        success = False
        original_config_path = self.config_path
        
        # 保存を試みるパスのリスト（優先順位順）
        try_paths = [self.config_path]
        # フォールバック先を追加
        try_paths.extend([
            Path.cwd() / ".image_entry_gui_config.json",
            Path(tempfile.gettempdir()) / "image_entry_gui_config.json",
            Path(__file__).resolve().parent / ".image_entry_gui_config.json"
        ])
        
        # 各パスを順番に試す
        for try_path in try_paths:
            try:
                # 親ディレクトリが存在することを確認
                try_path.parent.mkdir(parents=True, exist_ok=True)
                
                with try_path.open("w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
                
                # 保存成功
                if try_path != self.config_path:
                    self.config_path = try_path
                    # 初回のみログ出力（毎回出力すると煩雑）
                    if not success:
                        logger.info(f"設定を保存しました: {self.config_path}")
                
                # mark hidden where applicable (best-effort)
                try:
                    if try_path.name.startswith('.'):
                        _set_hidden(try_path)
                except Exception:
                    pass
                
                success = True
                break
                
            except PermissionError:
                # 権限エラーは次のパスを試す
                continue
            except Exception as e:
                # その他のエラーも次のパスを試す
                continue
                    
        if not success:
            # すべて失敗した場合のみエラーログ（1回だけ）
            if not hasattr(self, '_save_error_shown'):
                logger.error("設定ファイルを保存できませんでした。アプリケーションは動作しますが、設定は保存されません。")
                self._save_error_shown = True

    def _get_config_path(self) -> Path:
        """Get configuration file path with multiple fallback locations.
        
        Try paths in order of preference:
        1. User's home directory
        2. Current working directory  
        3. Temp directory
        4. Script directory (last resort)
        """
        config_filename = ".image_entry_gui_config.json"
        
        # Try user home directory first (most reliable)
        try:
            home_path = Path.home() / config_filename
            # Test write permission
            test_file = home_path.with_suffix('.test')
            test_file.write_text('test')
            test_file.unlink()
            return home_path
        except Exception:
            pass
            
        # Try current working directory
        try:
            cwd_path = Path.cwd() / config_filename
            # Test write permission
            test_file = cwd_path.with_suffix('.test')
            test_file.write_text('test')
            test_file.unlink()
            return cwd_path
        except Exception:
            pass
            
        # Try temp directory
        try:
            temp_path = Path(tempfile.gettempdir()) / config_filename
            # Test write permission
            test_file = temp_path.with_suffix('.test')
            test_file.write_text('test')
            test_file.unlink()
            return temp_path
        except Exception:
            pass
            
        # Last resort: script directory
        try:
            script_path = Path(__file__).resolve().parent / config_filename
            return script_path
        except Exception:
            # Final fallback
            return Path(config_filename).resolve()

    def _current_wareki_code(self) -> str:
        """Return wareki code like 508 for Reiwa 8."""
        from datetime import date

        y = date.today().year
        # Era mapping: Meiji=1, Taisho=2, Showa=3, Heisei=4, Reiwa=5
        if y >= 2019:
            era_code = 5
            era_year = y - 2018
        elif y >= 1989:
            era_code = 4
            era_year = y - 1988
        elif y >= 1926:
            era_code = 3
            era_year = y - 1925
        else:
            era_code = 0
            era_year = y
        return f"{era_code}{era_year:02d}"
    
    def _wareki_to_seireki(self, wareki_code: str) -> int:
        """和暦コードから西暦年に変換する (e.g. '508' -> 2026)."""
        try:
            if len(wareki_code) != 3:
                raise ValueError("和暦コードは3桁である必要があります")
            
            era_code = wareki_code[0]
            year_in_era = int(wareki_code[1:3])
            
            if era_code == '5':  # 令和
                return 2018 + year_in_era
            elif era_code == '4':  # 平成
                return 1988 + year_in_era
            elif era_code == '3':  # 昭和
                return 1925 + year_in_era
            else:
                raise ValueError(f"未対応の元号コード: {era_code}")
        except (ValueError, IndexError) as e:
            print(f"和暦変換エラー: {e}")
            return 2024  # デフォルト値

    def _load_form_list(self) -> List[str]:
        """Try to load a form list from settings or return fallback list."""
        # Try to load from settings
        try:
            if self.config_path.exists():
                with self.config_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if "form_list" in data and isinstance(data["form_list"], list):
                        return data["form_list"]
        except Exception:
            pass
        # Fallback to default list
        return FormListDialog.DEFAULT_FORMS.copy()
    
    def _save_form_list(self, form_list: List[str]) -> None:
        """Save form list to settings."""
        try:
            # Load existing settings
            data = {}
            if self.config_path.exists():
                try:
                    with self.config_path.open("r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except Exception:
                    pass
            
            # Update form_list
            data["form_list"] = form_list
            
            # Save
            try:
                with self.config_path.open("w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
            except Exception:
                pass
        except Exception:
            logger.exception("帳票No一覧の保存に失敗しました")

    def _form_code_from_label(self, label: str) -> str:
        """Extract the numeric form code (3 digits) from a label like '住申：040' -> '040'."""
        if not label:
            return ""
        m = re.search(r"(\d{3})$", label)
        if m:
            return m.group(1)
        # if label itself is numeric
        if label.isdigit():
            return label
        return ""

    def _set_form_combo_by_code(self, code: str) -> None:
        """Set the form_combo selection to the first item whose code matches `code`.

        If none matches, leave selection unchanged.
        """
        if not code:
            return
        for i in range(self.form_combo.count()):
            txt = self.form_combo.itemText(i)
            if self._form_code_from_label(txt) == code:
                self.form_combo.setCurrentIndex(i)
                return

    def _pad_num(self, value: object, width: int) -> str:
        """Convert value to int-like string and zero-pad to width.

        Non-numeric values are treated as 0.
        """
        try:
            n = int(str(value))
        except Exception:
            n = 0
        return str(n).zfill(width)

    def _pad_numeric(self, value: Optional[str], width: int) -> str:
        """Keep only digits from value and left-pad with zeros to width.

        If no digits found, return zeros of requested width.
        """
        s = "" if value is None else str(value)
        digits = "".join(ch for ch in s if ch.isdigit())
        if not digits:
            return "0" * width
        if len(digits) >= width:
            return digits
        return digits.zfill(width)

    def on_item_clicked(self, item: Optional[QListWidgetItem]) -> None:
        """Called when an item is clicked: forward to selection handler to update preview."""
        if item is None:
            return
        # call selection handler with current=item and previous=None
        try:
            # update preview without forcing selection save logic
            filename = item.text()
            # find index and update current index
            for i, r in enumerate(self.records):
                if r.filename == filename:
                    self._current_index = i
                    self.update_preview_for_record(r)
                    break
        except Exception:
            self.preview_label.setText("プレビューエラー")

    def load_images(self) -> None:
        try:
            self.records.clear()
            self.list_widget.clear()
            # reset last styled item when reloading
            self._last_styled_item = None
            # choose recursive or top-level search based on checkbox
            try:
                recursive = bool(self.recursive_checkbox.isChecked())
            except Exception:
                recursive = True
            if recursive:
                files = [p for p in self.input_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".tif", ".tiff", ".jpg", ".jpeg", ".png"}]
            else:
                files = [p for p in self.input_dir.glob("*") if p.is_file() and p.suffix.lower() in {".tif", ".tiff", ".jpg", ".jpeg", ".png"}]
            for p in sorted(files):
                rec = self.parse_image(p)
                self.records.append(rec)
                # create list item (no thumbnail)
                item = QListWidgetItem(rec.filename)
                if not rec.era:
                    # parse failed -> mark with tooltip but keep enabled so coloring is consistent
                    item.setToolTip("ファイル名が仕様に一致しません")
                self.list_widget.addItem(item)
                
            # normalize item styles so all non-disabled items use the default foreground
            for i in range(self.list_widget.count()):
                it = self.list_widget.item(i)
                try:
                    # Reset font to default to avoid inherited italic/weight from platform styles
                    from PySide6.QtGui import QFont

                    it.setFont(QFont())
                except Exception:
                    pass
                try:
                    # keep disabled items greyed; otherwise leave default foreground so platform selection works
                    if not (it.flags() & Qt.ItemIsEnabled):
                        it.setForeground(QBrush(QColor(130, 130, 130)))
                    it.setBackground(QBrush(Qt.transparent))
                except Exception:
                    pass

            # (debug logging removed)
            # set default 資料連番 for each record (1..N) unless already present
            for i, rec in enumerate(self.records):
                key = rec.key_for_linkage
                if key not in self.entries:
                    # store default form code (numeric) per current selection
                    form_code = self._form_code_from_label(self.form_combo.currentText())
                    self.entries[key] = {"address": "", "book": self.book_input.text(), "index": str(i + 1), "form": form_code}

            if self.list_widget.count() > 0:
                self.list_widget.setCurrentRow(0)
                # フォーカスは常に宛名番号欄に移す
                try:
                    self.addr_input.setFocus()
                except Exception:
                    pass
            # update dir label
            self.dir_label.setText(str(self.input_dir))
        except Exception as exc:
            QMessageBox.critical(self, "エラー", f"画像読み込み中にエラーが発生しました: {exc}")

    def parse_image(self, path: Path) -> ImageRecord:
        m = IMG_REGEX.match(path.name)
        if not m:
            return ImageRecord(path=path, era=None, form=None, manage=None, seq=None, page=None)
        return ImageRecord(
            path=path,
            era=m.group("era"),
            form=m.group("form"),
            manage=m.group("manage"),
            seq=m.group("seq"),
            page=m.group("page"),
        )

    def on_selection_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        # save previous
        if previous is not None:
            self.save_current_from_fields(previous.text())

        if current is None:
            return
        filename = current.text()
        rec = next((r for r in self.records if r.filename == filename), None)
        # update current index
        if rec is not None:
            try:
                self._current_index = self.records.index(rec)
            except ValueError:
                self._current_index = None
        if rec is None:
            return

        # load preview (use helper to avoid duplicated logic)
        try:
            self.update_preview_for_record(rec)
        except Exception:
            self.preview_label.setText("プレビューエラー")

        # load existing entries
        key = rec.key_for_linkage
        e = self.entries.get(key, {})
        self.addr_input.setText(e.get("address", ""))
        self.book_input.setText(e.get("book", ""))
        self.index_input.setText(e.get("index", ""))
        # validate field on load
        try:
            self.validate_addr_field()
        except Exception:
            pass
        # set form_combo to the stored per-record form code if present
        stored_form = e.get("form")
        if stored_form:
            self._set_form_combo_by_code(stored_form)

        # Fallback: ensure exactly one item is explicitly styled regardless of theme
        try:
            # Reset styling for all items first (clear any lingering styles)
            for i in range(self.list_widget.count()):
                it = self.list_widget.item(i)
                try:
                    # reset to default font object to avoid leftover italic state
                    from PySide6.QtGui import QFont

                    it.setFont(QFont())
                except Exception:
                    pass
                try:
                    # keep disabled items greyed; otherwise leave default foreground
                    if not (it.flags() & Qt.ItemIsEnabled):
                        it.setForeground(QBrush(QColor(130, 130, 130)))
                    it.setBackground(QBrush(Qt.transparent))
                except Exception:
                    pass

            # apply explicit style to current item
            if current is not None:
                try:
                    from PySide6.QtGui import QFont

                    cf = QFont()
                    cf.setItalic(True)
                    current.setFont(cf)
                except Exception:
                    pass
                # do not set explicit background/foreground here; delegate handles colors
                pass

            # remember which item we styled (not strictly needed now)
            self._last_styled_item = current
        except Exception:
            # best-effort only; do not interrupt normal flow
            pass
        # 選択が変わったら宛名番号欄にフォーカスを戻す
        try:
            self.addr_input.setFocus()
        except Exception:
            pass
        # 前と同じボタンの状態を更新
        self._update_same_as_prev_btn()

    def update_preview_for_record(self, rec: ImageRecord) -> None:
        """Load and display preview for the given record respecting zoom/fit settings."""
        pix = QPixmap(str(rec.path))
        if pix.isNull():
            self.preview_label.setText("プレビュー不可")
            return
        # Let PreviewLabel handle scaling and panning
        try:
            # preserve current view (zoom and pan) when not in fit-to-window mode
            preserve = not getattr(self, "fit_to_window", True)
            self.preview_label.set_image(pix, getattr(self, "fit_to_window", True), getattr(self, "zoom", 1.0), preserve_view=preserve)
        except Exception:
            # fallback to simple setPixmap
            try:
                scaled = pix.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview_label.setPixmap(scaled)
            except Exception:
                self.preview_label.setText("プレビューエラー")
        # remember which record is currently shown
        try:
            self._current_path = rec.path
        except Exception:
            self._current_path = None
        
        # ensure the corresponding list row is selected and visible
        try:
            idx = self.records.index(rec)
        except ValueError:
            idx = None
        if idx is not None:
            self._current_index = idx
            item = self.list_widget.item(idx)
            if item is not None:
                # set current row to highlight it and ensure visibility
                self.list_widget.setCurrentRow(idx)
                try:
                    self.list_widget.scrollToItem(item)
                except Exception:
                    pass

    def eventFilter(self, obj, event) -> bool:
        # capture wheel events on preview_label to handle zoom
        if obj is self.preview_label and event.type() == QEvent.Wheel:
            try:
                delta = event.angleDelta().y()
            except Exception:
                delta = event.delta() if hasattr(event, "delta") else 0
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            return True
        return super().eventFilter(obj, event)

    def save_current_from_fields(self, filename: str) -> None:
        rec = next((r for r in self.records if r.filename == filename), None)
        if rec is None:
            return
        key = rec.key_for_linkage
        addr = self.addr_input.text().strip()
        book = self.book_input.text().strip()
        idx = self.index_input.text().strip()
        # validate address field visually before saving
        self.validate_addr_field()
        # capture currently selected 帳票No as numeric code
        form_code = self._form_code_from_label(self.form_combo.currentText())
        if addr == "":
            # do not remove entries if empty; keep empty to allow later fill
            self.entries[key] = {"address": "", "book": book, "index": idx, "form": form_code}
        else:
            self.entries[key] = {"address": addr, "book": book, "index": idx, "form": form_code}

    def auto_save_current(self) -> None:
        item = self.list_widget.currentItem()
        if item is not None:
            self.save_current_from_fields(item.text())

    def _update_same_as_prev_btn(self) -> None:
        """「前と同じ」ボタンの有効/無効を更新する。
        
        条件: 多枚数対応帳票かつ現在のレコードが先頭以外のとき有効。
        """
        try:
            current_form_code = self._form_code_from_label(self.form_combo.currentText())
            is_multi = current_form_code in self._multi_page_set
            idx = self._current_index
            can_use = is_multi and idx is not None and idx > 0
            self.same_as_prev_btn.setEnabled(bool(can_use))
        except Exception:
            self.same_as_prev_btn.setEnabled(False)

    def set_same_address_as_prev(self) -> None:
        """前のレコードの宛名番号を現在のレコードにコピーする。"""
        try:
            idx = self._current_index
            if idx is None or idx <= 0:
                return
            prev_rec = self.records[idx - 1]
            prev_entry = self.entries.get(prev_rec.key_for_linkage, {})
            prev_addr = prev_entry.get("address", "")
            if not prev_addr:
                QMessageBox.information(self, "情報", "前のイメージに宛名番号が入力されていません。")
                return
            self.addr_input.setText(prev_addr)
            self.auto_save_current()
            # 入力後は次のレコードに移動しやすいようフォーカスを宛名番号欄に戻す
            self.addr_input.setFocus()
            self.addr_input.selectAll()
        except Exception as exc:
            logger.exception("前と同じ宛名番号のコピーに失敗しました")

    def _mod11_check(self, s: str) -> bool:
        """Perform a Modulus-11 check where the last digit is the check digit.

        Algorithm used:
        - Expect numeric string; last digit is check digit.
        - Starting from the rightmost digit before the check digit, multiply digits by weights 2,3,4,5,6,7 repeating.
        - Sum the products, compute remainder = sum % 11.
        - check = (11 - remainder) % 11. If check == 10, validation fails (no 'X' handling).
        - Return True if check equals the numeric check digit.
        """
        if not s or not s.isdigit() or len(s) < 2:
            return False
        digits = [int(ch) for ch in s]
        check_digit = digits[-1]
        body = digits[:-1]
        weights = [2, 3, 4, 5, 6, 7]
        total = 0
        w_index = 0
        # iterate from rightmost of body
        for d in reversed(body):
            total += d * weights[w_index % len(weights)]
            w_index += 1
        remainder = total % 11
        check = (11 - remainder) % 11
        if check == 10:
            return False
        return check == check_digit

    def _checkdeji_check(self, number: str) -> bool:
        """Perform check digit validation using checkdeji2 algorithm.
        
        Algorithm from checkdeji2.py:
        - Extract all digits except the last as base digits
        - Weights applied cyclically from left to right: [7, 6, 5, 4, 3, 2]
        - Calculate weighted sum
        - remainder = weighted_sum % 11
        - check_digit = 11 - remainder
        - if remainder == 0 or check_digit == 11: check_digit = 1
        - Return True if calculated check digit matches the provided one
        """
        if not number or not number.isdigit() or len(number) < 2:
            return False
            
        try:
            # Extract all digits except the last as base digits
            base_digits = [int(d) for d in number[:-1]]
            provided_cd = int(number[-1])

            # Weights applied cyclically from left to right
            weights = [7, 6, 5, 4, 3, 2]
            applied_weights = [weights[i % len(weights)] for i in range(len(base_digits))]

            # Calculate weighted sum
            weighted_sum = sum(d * w for d, w in zip(base_digits, applied_weights))
            remainder = weighted_sum % 11

            # Calculate check digit
            check_digit = 11 - remainder
            if remainder == 0 or check_digit == 11:
                check_digit = 1

            return check_digit == provided_cd
        except Exception:
            return False

    def validate_addr_field(self) -> None:
        """Validate the addr_input according to mod11 and checkdeji checkboxes. Update background color on error."""
        try:
            mod11_enabled = bool(self.mod11_checkbox.isChecked())
            checkdeji_enabled = bool(self.checkdeji_checkbox.isChecked())
        except Exception:
            mod11_enabled = False
            checkdeji_enabled = False
            
        val = self.addr_input.text().strip()
        ok = True
        
        # Check both validation methods if enabled
        if mod11_enabled:
            ok = ok and self._mod11_check(val)
        if checkdeji_enabled:
            ok = ok and self._checkdeji_check(val)
            
        try:
            if not ok and (mod11_enabled or checkdeji_enabled):
                # light red background for invalid
                self.addr_input.setStyleSheet("background-color: #ffcccc;")
            else:
                # reset to default
                self.addr_input.setStyleSheet("")
        except Exception:
            pass

    def on_addr_return_pressed(self) -> None:
        """Handle Enter in the addr_input: save and move to next record."""
        try:
            cur = self.list_widget.currentItem()
            if cur is not None:
                # save current field
                self.save_current_from_fields(cur.text())
            # move to next record
            self.select_next()
            # ensure focus and text selected for quick overwrite
            try:
                self.addr_input.setFocus()
                self.addr_input.selectAll()
            except Exception:
                pass
        except Exception:
            pass

    def save_csv(self) -> None:
        try:
            # ensure current is saved
            cur = self.list_widget.currentItem()
            if cur:
                self.save_current_from_fields(cur.text())

            rows = []
            # collect entries to include in the output ZIP (src_path, arcname)
            zip_entries = []
            # global year code from UI (pad to 3 digits)
            year_raw = self.year_input.text().strip()
            for rec in self.records:
                key = rec.key_for_linkage
                ent = self.entries.get(key, {"address": "", "book": "", "index": "", "form": ""})
                # per-spec raw values
                form_raw = ent.get("form") or (rec.form or "")
                manage_raw = ent.get("book") or (rec.manage or self.book_input.text())
                idx_raw = ent.get("index") or (rec.seq or "")
                # zero-pad per specification
                year_p = self._pad_num(year_raw, 3)
                form_p = self._pad_num(form_raw, 3)
                manage_p = self._pad_num(manage_raw, 4)
                idx_p = self._pad_num(idx_raw, 7)
                # linkage CSV: イメージファイル名 = [年度][帳票No][管理No][資料連番] (no hyphens, no ext)
                linkage_image_name = f"{year_p}{form_p}{manage_p}{idx_p}"
                # produce linkage row: イメージファイル名, 宛名番号, 資料冊号(ゼロ埋め), 資料連番(ゼロ埋め)
                rows.append([linkage_image_name, ent.get("address", ""), manage_p, idx_p])

            out_path = self.output_csv
            out_path.parent.mkdir(parents=True, exist_ok=True)
            # Write linkage CSV but ensure each line ends with a trailing comma.
            def _write_row_trailing_comma(fh, row):
                buf = io.StringIO()
                csv.writer(buf).writerow(row)
                s = buf.getvalue().rstrip("\r\n")
                fh.write(s + ",\n")

            with out_path.open("w", newline="", encoding="cp932", errors="replace") as fh:
                for r in rows:
                    _write_row_trailing_comma(fh, r)

            # Also write an index CSV that lists all images and parsed metadata
            try:
                # use fixed index filename per user request
                index_path = out_path.parent / "image_index.csv"
                with index_path.open("w", newline="", encoding="cp932", errors="replace") as idxfh:
                    # helper to write CSV rows with trailing comma
                    def _write_idx_row(row):
                        buf = io.StringIO()
                        csv.writer(buf).writerow(row)
                        s = buf.getvalue().rstrip("\r\n")
                        idxfh.write(s + ",\n")

                    # First row: output the current screen values (業務, 帳票NO, 年度)
                    business_value = self.business_input.text().strip()
                    current_form_code = self._form_code_from_label(self.form_combo.currentText())
                    year_raw = self.year_input.text().strip()
                    year_p_global = self._pad_num(year_raw, 3)
                    _write_idx_row([business_value, current_form_code, year_p_global])

                    # 多枚数対応帳票NOの判定（帳票No管理ダイアログで設定）
                    is_multi_page = current_form_code in self._multi_page_set

                    if not is_multi_page:
                        # 通常形式: 2行目に帳票枚数識別値 '1' を出力
                        _write_idx_row(["1"])

                    # Per-record rows
                    current_group_key = None
                    for rec in self.records:
                        ent = self.entries.get(rec.key_for_linkage, {})
                        form_raw = ent.get("form") or (rec.form or "")
                        manage_raw = ent.get("book") or (rec.manage or self.book_input.text())
                        idx_raw = ent.get("index") or (rec.seq or "")
                        addr_raw = ent.get("address", "")
                        # zero-pad values per record
                        year_p = year_p_global
                        form_p = self._pad_num(form_raw, 3)
                        manage_p = self._pad_num(manage_raw, 4)
                        idx_p = self._pad_num(idx_raw, 7)
                        ext = rec.path.suffix or ""
                        image_filename_field = f"{year_p}-{form_p}-{manage_p}-{idx_p}{ext}"
                        # record the arcname we will use inside the zip (preserve hierarchy)
                        arcname = str(Path(business_value) / year_p_global / form_p / manage_p / image_filename_field).replace('\\', '/')
                        zip_entries.append((rec.path, arcname))

                        if is_multi_page:
                            # 多枚数形式: 1列目は宛名番号ベース（グループ化キー）
                            addr_p = self._pad_num(addr_raw, 7)
                            image_number_field = f"{year_p}-{form_p}-{manage_p}-{addr_p}"
                            # グループ切替時（最初のレコード前を含む）に -1,, を挿入
                            if current_group_key != image_number_field:
                                _write_idx_row(["-1", ""])
                            current_group_key = image_number_field
                        else:
                            # 通常形式: 1列目は資料連番ベース
                            image_number_field = f"{year_p}-{form_p}-{manage_p}-{idx_p}"

                        _write_idx_row([image_number_field, image_filename_field])

                    # 多枚数形式: 最終レコードの後にもバーコード区切りを出力（仕様必須）
                    if is_multi_page and current_group_key is not None:
                        _write_idx_row(["-1", ""])
            except Exception:
                # don't fail the whole save if index write fails
                pass

            # Create ZIP of all output images preserving the hierarchy
            try:
                zip_name = "JA.zip"
                zip_path = out_path.parent / zip_name
                # write files into the zip with stored arcname
                with zipfile.ZipFile(str(zip_path), 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                    for src_path, arcname in zip_entries:
                        try:
                            # use arcname to preserve folder hierarchy in the zip
                            zf.write(str(src_path), arcname)
                        except Exception:
                            logger.exception(f"画像をZIPへ追加できませんでした: {src_path} -> {arcname}")
            except Exception:
                logger.exception("ZIP 作成中にエラーが発生しました")

            QMessageBox.information(self, "保存完了", f"保存完了\n\n保存先: {out_path.parent}")
        except Exception as exc:
            logger.exception("CSV 保存中にエラー")
            QMessageBox.critical(self, "エラー", f"CSV 保存に失敗しました: {exc}")

    def select_previous(self) -> None:
        # determine new index preferring the currently shown image
        if self._current_index is not None:
            new = max(0, self._current_index - 1)
        else:
            cur = self.list_widget.currentRow()
            new = max(0, cur - 1)
        if 0 <= new < len(self.records):
            # set current row; this will trigger on_selection_changed -> update_preview
            self.list_widget.setCurrentRow(new)

    def select_next(self) -> None:
        # determine new index preferring the currently shown image
        total = len(self.records)
        if total == 0:
            return
        if self._current_index is not None:
            new = min(total - 1, self._current_index + 1)
        else:
            cur = self.list_widget.currentRow()
            new = min(total - 1, cur + 1)
        if 0 <= new < total:
            self.list_widget.setCurrentRow(new)

    def zoom_in(self) -> None:
        self.fit_to_window = False
        self.zoom = min(getattr(self, "zoom", 1.0) * 1.2, 10.0)
        # refresh preview
        # prefer the currently shown record; fall back to tracked index or selection
        rec = None
        if self._current_path is not None:
            rec = next((r for r in self.records if r.path == self._current_path), None)
        if rec is None and self._current_index is not None and 0 <= self._current_index < len(self.records):
            rec = self.records[self._current_index]
        if rec is None:
            cur = self.list_widget.currentItem()
            if cur:
                filename = cur.text()
                rec = next((r for r in self.records if r.filename == filename), None)
        if rec:
            # update current index/path
            try:
                self._current_index = self.records.index(rec)
            except ValueError:
                self._current_index = None
            self._current_path = rec.path
            self.update_preview_for_record(rec)

    def zoom_out(self) -> None:
        self.fit_to_window = False
        self.zoom = max(getattr(self, "zoom", 1.0) / 1.2, 0.1)
        # same logic as zoom_in to keep preview consistent
        rec = None
        if self._current_path is not None:
            rec = next((r for r in self.records if r.path == self._current_path), None)
        if rec is None and self._current_index is not None and 0 <= self._current_index < len(self.records):
            rec = self.records[self._current_index]
        if rec is None:
            cur = self.list_widget.currentItem()
            if cur:
                filename = cur.text()
                rec = next((r for r in self.records if r.filename == filename), None)
        if rec:
            try:
                self._current_index = self.records.index(rec)
            except ValueError:
                self._current_index = None
            self._current_path = rec.path
            self.update_preview_for_record(rec)

    def fit_image(self) -> None:
        self.fit_to_window = True
        self.zoom = 1.0
        cur = self.list_widget.currentItem()
        if cur:
            self.on_selection_changed(cur, None)

    def keyPressEvent(self, event) -> None:
        """Handle basic keyboard navigation and zoom without QShortcut.

        Left/Right: navigate images
        Ctrl + + / Ctrl + - : zoom in/out
        """
        try:
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key_Left:
                self.select_previous()
                return
            if key == Qt.Key_Right:
                self.select_next()
                return
            # Ctrl + Plus (platform dependent key) or Ctrl + = often used for +
            if mods & Qt.ControlModifier and key in (Qt.Key_Plus, Qt.Key_Equal):
                self.zoom_in()
                return
            if mods & Qt.ControlModifier and key in (Qt.Key_Minus, Qt.Key_Underscore):
                self.zoom_out()
                return
        except Exception:
            pass
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        """Use mouse wheel to zoom when cursor is over the preview area.

        Scrolling up -> zoom in, scrolling down -> zoom out.
        """
        try:
            # event.pos() is relative to self; find the child widget under the cursor
            child = self.childAt(event.pos())
            w = child
            while w is not None:
                if w is self.preview_label:
                    delta = 0
                    # PySide6: use angleDelta().y() for vertical scroll
                    try:
                        delta = event.angleDelta().y()
                    except Exception:
                        # fallback for older events
                        delta = event.delta() if hasattr(event, "delta") else 0
                    if delta > 0:
                        self.zoom_in()
                    elif delta < 0:
                        self.zoom_out()
                    return
                w = w.parentWidget()
        except Exception:
            # ignore and propagate to default
            pass
        super().wheelEvent(event)

    def select_folder(self) -> None:
        """フォルダ選択ダイアログを表示して入力フォルダを設定する。"""
        folder = QFileDialog.getExistingDirectory(self, "フォルダ選択", str(self.input_dir))
        if folder:
            self.input_dir = Path(folder)
            self.load_images()
            try:
                self.save_settings()
            except Exception:
                pass

    def select_output(self) -> None:
        """出力先 CSV を選択するダイアログを表示する。"""
        path, _ = QFileDialog.getSaveFileName(self, "出力先を選択", str(self.output_csv), "CSV Files (*.csv);;All Files (*)")
        if path:
            self.output_csv = Path(path)
            QMessageBox.information(self, "出力先設定", f"出力先を {self.output_csv} に設定しました")
            try:
                self.save_settings()
            except Exception:
                pass

    def select_taxpayer_csv(self) -> None:
        """納税義務者情報CSVを選択するダイアログを表示する。"""
        initial_dir = str(self.taxpayer_csv_path.parent) if self.taxpayer_csv_path.exists() else "CSV"
        path, _ = QFileDialog.getOpenFileName(
            self, 
            "納税義務者情報CSVを選択", 
            initial_dir, 
            "CSV Files (*.csv);;All Files (*)"
        )
        if path:
            csv_path = Path(path)
            if not csv_path.exists():
                QMessageBox.warning(self, "エラー", f"ファイルが見つかりません: {csv_path}")
                return
            
            # CSVパスを更新
            self.taxpayer_csv_path = csv_path
            
            # CSVを読み込み
            try:
                self.load_taxpayer_data()
                record_count = len(self.taxpayer_records)
                QMessageBox.information(
                    self, 
                    "納税義務者情報CSV設定", 
                    f"納税義務者情報CSVを設定しました:\n{self.taxpayer_csv_path}\n\n読み込み件数: {record_count:,}件"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, 
                    "読み込みエラー", 
                    f"CSVの読み込みに失敗しました:\n{e}"
                )
                return
            
            # 設定を保存
            try:
                self.save_settings()
            except Exception:
                pass

    def _build_search_indexes(self) -> None:
        """検索高速化用のインデックスを構築する。"""
        try:
            self._taxpayer_by_year.clear()
            self._taxpayer_by_number.clear()
            self._taxpayer_name_index.clear()
            
            for record in self.taxpayer_records:
                # 年度別インデックス
                if record.tax_year:
                    try:
                        year_key = str(int(record.tax_year))
                        if year_key not in self._taxpayer_by_year:
                            self._taxpayer_by_year[year_key] = []
                        self._taxpayer_by_year[year_key].append(record)
                    except ValueError:
                        pass
                
                # 宛名番号インデックス（完全一致用）
                if record.addressee_number:
                    self._taxpayer_by_number[record.addressee_number] = record
                
                # 氏名インデックス（部分一致用）
                if record.name:
                    name_lower = record.name.lower()
                    if name_lower not in self._taxpayer_name_index:
                        self._taxpayer_name_index[name_lower] = []
                    self._taxpayer_name_index[name_lower].append(record)
                    
        except Exception as e:
            print(f"インデックス構築エラー: {e}")
    
    def load_taxpayer_data(self) -> None:
        """納税義務者情報CSVを読み込む。"""
        try:
            if not self.taxpayer_csv_path.exists():
                print(f"納税義務者情報ファイル ({self.taxpayer_csv_path}) が見つかりません。")
                return
            
            import csv
            self.taxpayer_records = []
            
            with open(self.taxpayer_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        record = TaxpayerRecord(
                            municipality_code=row.get('市区町村コード', '').strip(),
                            tax_year=row.get('課税年度', '').strip(),
                            addressee_number=row.get('宛名番号', '').strip(),
                            postal_code=row.get('郵便番号', '').strip(),
                            address_prefecture=row.get('住所_都道府県', '').strip(),
                            address_city=row.get('住所_市区郡町村名', '').strip(),
                            address_town=row.get('住所_町字', '').strip(),
                            address_number=row.get('住所_番地号表記', '').strip(),
                            address_other=row.get('住所_方書', '').strip(),
                            name_kana=row.get('氏名（振り仮名）', '').strip(),
                            name=row.get('氏名', '').strip(),
                            birth_date=row.get('生年月日', '').strip()
                        )
                        if record.addressee_number:  # 宛名番号が空でない場合のみ追加
                            self.taxpayer_records.append(record)
                    except Exception as e:
                        print(f"レコード解析エラー: {e}")
                        continue
            
            # 検索高速化用のインデックスを構築
            self._build_search_indexes()
            
            print(f"納税義務者情報を {len(self.taxpayer_records)} 件読み込みました。")
        except Exception as e:
            print(f"納税義務者情報の読み込みに失敗しました: {e}")
            QMessageBox.warning(self, "読み込みエラー", f"納税義務者情報の読み込みに失敗しました:\n{e}")

    def perform_search(self) -> None:
        """検索を実行して結果を表示する（高速化版）。"""
        try:
            query = self.search_input.text().strip()
            if not query:
                self.search_results.clear()
                self.search_results.setVisible(False)
                return
            
            # 画面の年度から西暦を取得してフィルタリング用
            current_wareki = self.year_input.text().strip()
            target_year = self._wareki_to_seireki(current_wareki) if current_wareki else None
            
            # 年度でフィルタリングしたレコードリストを取得
            if target_year:
                year_key = str(target_year)
                search_pool = self._taxpayer_by_year.get(year_key, [])
            else:
                search_pool = self.taxpayer_records
            
            matching_records = []
            max_results = 50  # 最大検索件数（パフォーマンス向上のため）
            
            # 段階1: 宛名番号での完全一致検索（最速）
            if query.isdigit() and query in self._taxpayer_by_number:
                record = self._taxpayer_by_number[query]
                if not target_year or (record.tax_year and int(record.tax_year) == target_year):
                    matching_records.append(record)
            
            # 段階2: 十分な結果が見つからない場合は部分一致検索
            if len(matching_records) < max_results:
                for record in search_pool:
                    if len(matching_records) >= max_results:
                        break  # 早期終了
                    
                    # 既に追加済みのレコードはスキップ
                    if record in matching_records:
                        continue
                    
                    if record.matches_search(query):
                        matching_records.append(record)
            
            # 結果表示
            self.search_results.clear()
            if matching_records:
                for record in matching_records[:20]:  # 最大20件まで表示
                    # 生年月日を和暦表示で含む表示文字列
                    wareki_birth = record.get_wareki_birth_date()
                    birth_info = f" [{wareki_birth}]" if wareki_birth else ""
                    # 氏名（振り仮名）を追加
                    kana_info = f"（{record.name_kana}）" if record.name_kana else ""
                    display_text = f"{record.addressee_number} - {record.name}{kana_info}{birth_info} ({record.full_address})"
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.UserRole, record)  # レコードデータを保存
                    self.search_results.addItem(item)
                
                self.search_results.setVisible(True)
                if len(matching_records) > 20:
                    status_item = QListWidgetItem(f"... 他 {len(matching_records) - 20} 件")
                    status_item.setFlags(Qt.NoItemFlags)  # 選択不可
                    self.search_results.addItem(status_item)
            else:
                # 検索結果なし
                year_info = f" (年度: {target_year})" if target_year else ""
                no_result_item = QListWidgetItem(f"検索結果が見つかりません{year_info}")
                no_result_item.setFlags(Qt.NoItemFlags)  # 選択不可
                self.search_results.addItem(no_result_item)
                self.search_results.setVisible(True)
                
        except Exception as e:
            print(f"検索実行エラー: {e}")
            QMessageBox.warning(self, "検索エラー", f"検索の実行に失敗しました:\n{e}")

    def on_search_text_changed(self, text: str) -> None:
        """検索テキスト変更時の処理。"""
        try:
            # テキストが空の場合は結果をクリア
            if not text.strip():
                self.search_results.clear()
                self.search_results.setVisible(False)
        except Exception as e:
            print(f"検索テキスト変更エラー: {e}")

    def on_search_result_selected(self, item: QListWidgetItem) -> None:
        """検索結果選択時の処理。"""
        try:
            record = item.data(Qt.UserRole)
            if isinstance(record, TaxpayerRecord):
                # 宛名番号を自動入力
                self.addr_input.setText(record.addressee_number)
                # 検索結果を非表示
                self.search_results.setVisible(False)
                self.search_input.clear()
                # フォーカスを宛名番号入力欄に移動
                self.addr_input.setFocus()
        except Exception as e:
            print(f"検索結果選択エラー: {e}")

    def closeEvent(self, event) -> None:
        # Save settings on exit
        try:
            self.save_settings()
        except Exception:
            pass
        super().closeEvent(event)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    import argparse as _argparse

    p = _argparse.ArgumentParser(description="Image Entry GUI (PySide6)")
    p.add_argument("--input-dir", required=False, default=".", help="画像が置かれたフォルダ")
    p.add_argument("--output", required=False, default="image_linkage.csv", help="出力 CSV ファイルパス")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    app = QApplication(sys.argv)
    win = ImageEntryApp(input_dir=Path(args.input_dir), output_csv=Path(args.output))
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
