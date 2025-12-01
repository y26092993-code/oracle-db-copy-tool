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
        """検索クエリにマッチするかチェック"""
        if not query:
            return True
        query_lower = query.lower()
        return (
            query_lower in self.addressee_number.lower() or
            query_lower in self.name.lower() or
            query_lower in self.name_kana.lower() or
            query_lower in self.address_prefecture.lower() or
            query_lower in self.address_city.lower() or
            query_lower in self.address_town.lower() or
            query_lower in self.address_number.lower() or
            query_lower in self.address_other.lower() or
            query_lower in self.postal_code.lower()
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

    def resizeEvent(self, event) -> None:
        # when resized, recompute scaled pixmap if fit_to_window
        super().resizeEvent(event)
        self._rescale()
        self._center_or_clamp()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
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
        if event.button() == Qt.LeftButton and self._dragging:
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
        self.resize(1000, 600)

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
        
        # 納税義務者情報検索関連
        self.taxpayer_records: List[TaxpayerRecord] = []
        self.taxpayer_csv_path = Path("納税義務者情報.csv")

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
        # Settings UI: show/reset buttons (追加)
        self.show_settings_btn = QPushButton("設定表示")
        self.reset_settings_btn = QPushButton("設定をリセット")

        select_btn = QPushButton("フォルダ選択")
        load_btn = QPushButton("フォルダ再読込")
        output_btn = QPushButton("出力先選択")
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
        # OCR button near zoom controls for quick access
        self.ocr_btn = QPushButton("OCR 実行")
        self.ocr_btn.setFocusPolicy(Qt.NoFocus)
        zoom_row.addWidget(self.ocr_btn)
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
                idx = 0
                for i in range(self.ocr_backend_combo.count()):
                    d = self.ocr_backend_combo.itemData(i)
                    if isinstance(d, (list, tuple)) and d[1]:
                        idx = i
                        break
                self.ocr_backend_combo.setCurrentIndex(idx)
                self.ocr_backend = self.ocr_backend_combo.itemData(idx)[0]
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
        # Top meta row: 業務 / 年度 / 帳票No / 管理No / 資料連番 横並び
        meta_row = QHBoxLayout()
        meta_row.addWidget(QLabel("業務"))
        meta_row.addWidget(self.business_input)
        meta_row.addSpacing(6)
        meta_row.addWidget(QLabel("年度"))
        meta_row.addWidget(self.year_input)
        meta_row.addSpacing(6)
        meta_row.addWidget(QLabel("帳票No"))
        meta_row.addWidget(self.form_combo)
        meta_row.addSpacing(6)
        meta_row.addWidget(QLabel("管理No"))
        meta_row.addWidget(self.book_input)
        meta_row.addSpacing(6)
        meta_row.addWidget(QLabel("資料連番"))
        meta_row.addWidget(self.index_input)
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
        # Mod11 check option
        self.mod11_checkbox = QCheckBox("モジュラス11チェック")
        try:
            self.mod11_checkbox.setChecked(False)
        except Exception:
            pass
        addr_row.addWidget(self.mod11_checkbox)
        
        # Check digit option (checkdeji2 style)
        self.checkdeji_checkbox = QCheckBox("チェックデジット検証")
        try:
            self.checkdeji_checkbox.setChecked(False)
        except Exception:
            pass
        addr_row.addWidget(self.checkdeji_checkbox)
        form_layout.addLayout(addr_row)

        # remaining buttons: place navigation on single row
        nav_row = QHBoxLayout()
        nav_row.addWidget(prev_btn)
        nav_row.addWidget(next_btn)
        form_layout.addLayout(nav_row)

        # output/save below navigation
        form_layout.addWidget(output_btn)
        form_layout.addWidget(save_btn)
        # settings buttons row
        settings_row = QHBoxLayout()
        settings_row.addWidget(self.show_settings_btn)
        settings_row.addWidget(self.reset_settings_btn)
        form_layout.addLayout(settings_row)

        right_layout = QVBoxLayout()
        # preview (stretch), zoom controls under preview, then form
        right_layout.addLayout(right_top_layout, 1)
        right_layout.addLayout(zoom_row)
        right_layout.addLayout(form_layout, 0)

        splitter = QSplitter()
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        try:
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 1)
        except Exception:
            pass

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(splitter)

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
            self.year_input.editingFinished.connect(lambda: self.save_settings())
        except Exception:
            pass
        # settings buttons
        try:
            self.show_settings_btn.clicked.connect(self.show_settings_dialog)
            self.reset_settings_btn.clicked.connect(self.reset_settings)
        except Exception:
            pass
        # connect OCR button
        try:
            # connect to async runner to avoid UI freeze
            self.ocr_btn.clicked.connect(self.perform_ocr_for_current_async)
        except Exception:
            # fallback to sync if connecting fails
            try:
                self.ocr_btn.clicked.connect(self.perform_ocr_for_current)
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
        save_btn.clicked.connect(self.save_csv)
        prev_btn.clicked.connect(self.select_previous)
        next_btn.clicked.connect(self.select_next)
        output_btn.clicked.connect(self.select_output)
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
            try:
                self.recursive_checkbox.setChecked(True)
                self.mod11_checkbox.setChecked(False)
            finally:
                self.recursive_checkbox.blockSignals(False)
                self.mod11_checkbox.blockSignals(False)
            # reset output/input to initial values
            self.input_dir = Path(self._initial_input_dir)
            self.output_csv = Path(self._initial_output_csv)
            # reset form and year
            try:
                self._set_form_combo_by_code("050")
            except Exception:
                pass
            self.year_input.setText(self._current_wareki_code())
            # apply geometry reset (center on screen with default size)
            try:
                self.resize(1000, 600)
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
                                texts.append(o)
                            elif isinstance(o, dict):
                                for v in o.values():
                                    _collect_strings(v)
                            elif isinstance(o, (list, tuple)):
                                for e in o:
                                    _collect_strings(e)
                        _collect_strings(doc)
                        return '\n'.join(t for t in texts if t)
                    else:
                        # md/csv/html: return raw file content
                        try:
                            with open(out_file, 'r', encoding='utf-8', errors='replace') as fh:
                                return fh.read()
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
            if "ocr_backend" in data:
                try:
                    val = str(data.get("ocr_backend", ""))
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
                                            if str(d[0]) == val:
                                                idx = i
                                                break
                                        except Exception:
                                            pass
                                if idx is not None:
                                    self.ocr_backend_combo.setCurrentIndex(idx)
                                else:
                                    # fallback for legacy values: try to set by visible text
                                    try:
                                        self.ocr_backend_combo.setCurrentText(val)
                                    except Exception:
                                        pass
                            finally:
                                self.ocr_backend_combo.blockSignals(False)
                        except Exception:
                            pass
                    self.ocr_backend = val
                except Exception:
                    pass
        except Exception:
            pass

    def save_settings(self) -> None:
        """Save current settings to JSON file.

        We persist only a minimal set: recursive, mod11, checkdeji, output_csv, input_dir.
        """
        data = {
            "recursive": bool(self.recursive_checkbox.isChecked()),
            "mod11": bool(self.mod11_checkbox.isChecked()),
            "checkdeji": bool(self.checkdeji_checkbox.isChecked()),
            "output_csv": str(self.output_csv) if self.output_csv is not None else "",
            "input_dir": str(self.input_dir) if self.input_dir is not None else "",
            "form": self._form_code_from_label(self.form_combo.currentText()),
            "year": str(self.year_input.text()).strip(),
            # OCR backend selection (pytesseract | easyocr | none)
            "ocr_backend": (str(self.ocr_backend_combo.currentText()) if hasattr(self, 'ocr_backend_combo') and self.ocr_backend_combo is not None else getattr(self, 'ocr_backend', '')),
            "geom": {
                "x": int(self.geometry().x()),
                "y": int(self.geometry().y()),
                "w": int(self.geometry().width()),
                "h": int(self.geometry().height()),
            },
        }
        success = False
        original_config_path = self.config_path
        
        # Try current config path first
        try:
            with self.config_path.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            # mark hidden where applicable (best-effort)
            try:
                _set_hidden(self.config_path)
            except Exception:
                pass
            success = True
        except PermissionError:
            # Permission denied - try alternative paths
            logger.warning(f"設定ファイルの保存権限がありません: {self.config_path}")
        except Exception as e:
            logger.warning(f"設定ファイルの保存でエラー: {e}")
            
        # If initial save failed, try fallback locations
        if not success:
            fallback_paths = [
                Path.home() / ".image_entry_gui_config.json",
                Path.cwd() / ".image_entry_gui_config.json", 
                Path(tempfile.gettempdir()) / ".image_entry_gui_config.json"
            ]
            
            for fallback_path in fallback_paths:
                try:
                    # Skip if it's the same path we already tried
                    if fallback_path.resolve() == original_config_path.resolve():
                        continue
                        
                    with fallback_path.open("w", encoding="utf-8") as fh:
                        json.dump(data, fh, ensure_ascii=False, indent=2)
                    
                    # Update config path for future use
                    self.config_path = fallback_path
                    
                    # mark hidden where applicable (best-effort)
                    try:
                        _set_hidden(self.config_path)
                    except Exception:
                        pass
                        
                    logger.info(f"設定を代替場所に保存しました: {self.config_path}")
                    success = True
                    break
                except Exception:
                    continue
                    
        if not success:
            # All attempts failed - log but don't interrupt UI
            logger.error("すべての設定保存場所でエラーが発生しました。設定は保存されません。")

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
        """Try to load a form list from a few candidate files, else return fallback list."""
        # For this project the allowed 帳票No values are fixed per spec
        return ["住申：040", "給報：050", "年報：060"]

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

                    # Second row: 業務列に '1' のみを出力（帳票No・年度は出力しない）
                    _write_idx_row(["1"])

                    # Per-record rows: イメージ番号, イメージファイル名 の2カラムのみ出力
                    for rec in self.records:
                        ent = self.entries.get(rec.key_for_linkage, {})
                        form_raw = ent.get("form") or (rec.form or "")
                        manage_raw = ent.get("book") or (rec.manage or self.book_input.text())
                        idx_raw = ent.get("index") or (rec.seq or "")
                        # zero-pad values per record
                        year_p = year_p_global
                        form_p = self._pad_num(form_raw, 3)
                        manage_p = self._pad_num(manage_raw, 4)
                        idx_p = self._pad_num(idx_raw, 7)
                        image_number_field = f"{year_p}-{form_p}-{manage_p}-{idx_p}"
                        ext = rec.path.suffix or ""
                        image_filename_field = f"{year_p}-{form_p}-{manage_p}-{idx_p}{ext}"
                        # コピー先フォルダを作成して、入力画像を出力ファイル名へリネームしてコピー
                        # record the arcname we will use inside the zip (preserve hierarchy)
                        arcname = str(Path(business_value) / year_p_global / form_p / manage_p / image_filename_field).replace('\\', '/')
                        zip_entries.append((rec.path, arcname))
                        _write_idx_row([image_number_field, image_filename_field])
            except Exception:
                # don't fail the whole save if index write fails
                pass

            # Create ZIP of all output images preserving the hierarchy
            try:
                zip_name = f"{out_path.stem}_images.zip"
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

            QMessageBox.information(self, "保存完了", f"CSV を保存しました: {out_path}")
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
            
            print(f"納税義務者情報を {len(self.taxpayer_records)} 件読み込みました。")
        except Exception as e:
            print(f"納税義務者情報の読み込みに失敗しました: {e}")
            QMessageBox.warning(self, "読み込みエラー", f"納税義務者情報の読み込みに失敗しました:\n{e}")

    def perform_search(self) -> None:
        """検索を実行して結果を表示する。"""
        try:
            query = self.search_input.text().strip()
            if not query:
                self.search_results.clear()
                self.search_results.setVisible(False)
                return
            
            # 画面の年度から西暦を取得してフィルタリング用
            current_wareki = self.year_input.text().strip()
            target_year = self._wareki_to_seireki(current_wareki) if current_wareki else None
            
            # 検索実行
            matching_records = []
            for record in self.taxpayer_records:
                # 年度フィルタリング（税年度が一致する場合のみ）
                if target_year and record.tax_year:
                    try:
                        record_year = int(record.tax_year)
                        if record_year != target_year:
                            continue  # 年度が一致しない場合はスキップ
                    except ValueError:
                        continue  # 年度が数値でない場合はスキップ
                
                if record.matches_search(query):
                    matching_records.append(record)
            
            # 結果表示
            self.search_results.clear()
            if matching_records:
                for record in matching_records[:20]:  # 最大20件まで表示
                    # 生年月日を和暦表示で含む表示文字列
                    wareki_birth = record.get_wareki_birth_date()
                    birth_info = f" [{wareki_birth}]" if wareki_birth else ""
                    display_text = f"{record.addressee_number} - {record.name}{birth_info} ({record.full_address})"
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
