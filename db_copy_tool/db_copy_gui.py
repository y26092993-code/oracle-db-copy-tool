"""Oracle DB オブジェクトコピーツール GUI版.

開発環境のないLAN環境で使用できるスタンドアロンアプリケーション。
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
from typing import Dict, List, Optional
import logging
from datetime import datetime
import yaml
import os
import csv

from db_manager import (
    DatabaseManager,
    DatabaseObject,
    ObjectType,
    CopyResult,
    ConnectionConfig,
    init_thick_mode,
)
from tnsnames_parser import TnsNamesParser, TnsEntry


class DBCopyToolGUI:
    """Oracle DBオブジェクトコピーツールのGUIクラス。"""

    def __init__(self, root: tk.Tk):
        """初期化。
        
        Args:
            root: Tkinterのルートウィンドウ
        """
        self.root = root
        self.root.title("Oracle DB オブジェクトコピーツール")
        self._setup_window_size()
        
        # ロギング設定
        self._setup_logging()
        
        # データベースマネージャー
        self.db_manager: Optional[DatabaseManager] = None
        
        # エラー情報を保持（エラーサマリー用）
        self.error_logs: List[str] = []
        
        # tnsnames.ora パーサー
        self.tns_parser: Optional[TnsNamesParser] = None
        try:
            self.tns_parser = TnsNamesParser()
            if self.tns_parser.has_tnsnames():
                logging.info(f"tnsnames.ora を読み込みました: {self.tns_parser.get_tnsnames_path()}")
            else:
                logging.info("tnsnames.ora が見つかりませんでした（手動入力モード）")
        except Exception as e:
            logging.warning(f"tnsnames.ora の読み込みエラー: {e}")
            self.tns_parser = None
        
        # UI構築
        self._create_widgets()
        
        logging.info("アプリケーション起動")

    def _setup_window_size(self) -> None:
        """画面解像度に合わせてウィンドウサイズと位置を設定。"""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        # タスクバー等を考慮して画面の90%を上限とする
        max_w = int(screen_w * 0.90)
        max_h = int(screen_h * 0.90)

        win_w = min(1200, max_w)
        win_h = min(900, max_h)

        # 最小サイズを保証
        win_w = max(win_w, 900)
        win_h = max(win_h, 600)

        # 画面中央に配置
        pos_x = (screen_w - win_w) // 2
        pos_y = (screen_h - win_h) // 2

        self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.root.minsize(900, 600)

    def _setup_logging(self) -> None:
        """ロギングの設定。"""
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(
                    f'db_copy_tool_{datetime.now().strftime("%Y%m%d")}.log',
                    encoding='utf-8'
                ),
                logging.StreamHandler()
            ]
        )

    def _create_widgets(self) -> None:
        """ウィジェットを作成。"""
        # ノートブック（タブ）
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # タブ1: 接続設定
        self.connection_frame = ttk.Frame(notebook)
        notebook.add(self.connection_frame, text="接続設定")
        self._create_connection_tab()
        
        # タブ2: オブジェクト選択
        self.object_frame = ttk.Frame(notebook)
        notebook.add(self.object_frame, text="オブジェクト選択")
        self._create_object_tab()
        
        # タブ3: 実行とログ
        self.execution_frame = ttk.Frame(notebook)
        notebook.add(self.execution_frame, text="実行とログ")
        self._create_execution_tab()

    def _create_connection_tab(self) -> None:
        """接続設定タブを作成。"""
        parent = self.connection_frame
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        # スクロール対応キャンバス
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.grid(row=0, column=0, sticky="nsew")

        inner = ttk.Frame(canvas)
        inner_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(inner_window, width=event.width)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=1)

        # tnsnames.ora ツールバー（2列にまたがる）
        tns_toolbar = ttk.Frame(inner)
        tns_toolbar.grid(row=0, column=0, columnspan=2, padx=10, pady=(8, 4), sticky="ew")

        if self.tns_parser and self.tns_parser.has_tnsnames():
            info_text = f"tnsnames.ora: {self.tns_parser.get_tnsnames_path()}"
            ttk.Label(tns_toolbar, text=info_text, foreground="green").pack(side=tk.LEFT, padx=5)
        else:
            ttk.Label(tns_toolbar, text="tnsnames.ora が見つかりません",
                      foreground="orange").pack(side=tk.LEFT, padx=5)

        ttk.Button(tns_toolbar, text="tnsnames.ora を選択",
                   command=self._select_tnsnames_file, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(tns_toolbar, text="読み込み結果を表示",
                   command=self._show_tnsnames_entries, width=20).pack(side=tk.LEFT, padx=5)

        # ソース／ターゲット DB を横並びに配置
        source_frame = ttk.LabelFrame(inner, text="ソースデータベース（コピー元）", padding=8)
        source_frame.grid(row=1, column=0, padx=(10, 4), pady=4, sticky="nsew")
        self._create_db_fields(source_frame, "source")

        target_frame = ttk.LabelFrame(inner, text="ターゲットデータベース（コピー先）", padding=8)
        target_frame.grid(row=1, column=1, padx=(4, 10), pady=4, sticky="nsew")
        self._create_db_fields(target_frame, "target")

        # ボタン行
        button_frame = ttk.Frame(inner)
        button_frame.grid(row=2, column=0, columnspan=2, pady=6)

        ttk.Button(button_frame, text="接続テスト",
                   command=self._test_connections, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="設定を保存",
                   command=self._save_config, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="設定を読込",
                   command=self._load_config, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="認証情報をコピー元→コピー先へコピー",
                   command=self._copy_auth_to_target, width=30).pack(side=tk.LEFT, padx=5)

        # 接続モード選択（2列にまたがる）
        mode_frame = ttk.LabelFrame(
            inner,
            text="▶ 接続モード（認証エラー DPY-3015 が出る場合は Thick mode を試してください）",
            padding=6
        )
        mode_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=(4, 8), sticky="ew")

        self.thick_mode_var = tk.BooleanVar(value=False)

        ttk.Radiobutton(mode_frame,
                        text="Thin mode  （デフォルト・追加ソフトウェア不要）",
                        variable=self.thick_mode_var, value=False,
                        command=self._on_mode_changed
                        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=5, pady=2)

        ttk.Radiobutton(mode_frame,
                        text="Thick mode  （Oracle Instant Client 必要・全認証方式対応）",
                        variable=self.thick_mode_var, value=True,
                        command=self._on_mode_changed
                        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=5, pady=2)

        ttk.Label(mode_frame, text="Instant Client パス:").grid(
            row=2, column=0, sticky="e", padx=5, pady=3)
        self.client_lib_entry = ttk.Entry(mode_frame, width=45, state="disabled")
        self.client_lib_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=3)
        self.client_lib_browse_btn = ttk.Button(
            mode_frame, text="参照...", command=self._browse_client_lib,
            state="disabled", width=8)
        self.client_lib_browse_btn.grid(row=2, column=2, padx=5, pady=3)
        ttk.Label(mode_frame,
                  text="  例: C:\\oracle\\instantclient_21_3  (空の場合は PATH から自動検索)",
                  foreground="gray", font=("", 8)
                  ).grid(row=3, column=0, columnspan=3, sticky="w", padx=5)
        mode_frame.columnconfigure(1, weight=1)

    def _create_db_fields(self, parent: ttk.Frame, prefix: str) -> None:
        """DB接続フィールドを作成。
        
        Args:
            parent: 親ウィジェット
            prefix: フィールド名のプレフィックス（source/target）
        """
        # 入力フィールドを保存する辞書を作成
        if not hasattr(self, 'entries'):
            self.entries: Dict[str, tk.Entry] = {}
        if not hasattr(self, 'tns_combos'):
            self.tns_combos: Dict[str, ttk.Combobox] = {}
        
        # TNSエントリ選択（常に表示）
        row = 0
        
        # TNS エントリセクション
        tns_section = ttk.LabelFrame(parent, text="方法1: TNS エントリから選択", padding=5)
        tns_section.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
        
        help_text = "登録済みの接続設定を選択（自動入力されます）"
        ttk.Label(tns_section, text=help_text, foreground="gray", font=("", 8)).pack(anchor="w", padx=5, pady=(0, 2))
        
        # tnsnames.ora が読み込まれている場合はエントリを表示、そうでない場合は "未設定" を表示
        if self.tns_parser and self.tns_parser.has_tnsnames():
            tns_entries = list(self.tns_parser.get_entries().keys())
            combo_values = ["（手動入力）"] + sorted(tns_entries)
            combo_state = "readonly"
        else:
            combo_values = ["（手動入力）", "tnsnames.ora が見つかりません"]
            combo_state = "readonly"
        
        tns_combo = ttk.Combobox(
            tns_section,
            values=combo_values,
            state=combo_state,
            width=22
        )
        tns_combo.set("（手動入力）")
        tns_combo.pack(fill="x", padx=5, pady=3)
        
        if self.tns_parser and self.tns_parser.has_tnsnames():
            tns_combo.bind("<<ComboboxSelected>>", 
                          lambda e, p=prefix: self._on_tns_selected(p))
        
        self.tns_combos[prefix] = tns_combo
        row += 1
        
        # 手動入力セクション
        manual_section = ttk.LabelFrame(parent, text="方法2: 手動で接続情報を入力", padding=5)
        manual_section.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=(2, 3))
        
        connection_fields = [
            ("ホスト:", "host"),
            ("ポート:", "port"),
            ("サービス名/SID:", "service"),
        ]
        
        for i, (label, field) in enumerate(connection_fields):
            ttk.Label(manual_section, text=label).grid(
                row=i, column=0, sticky="e", padx=5, pady=2
            )

            entry = ttk.Entry(manual_section, width=22)
            entry.grid(row=i, column=1, sticky="ew", padx=5, pady=2)
            
            # デフォルト値
            if field == "port":
                entry.insert(0, "1521")
            
            self.entries[f"{prefix}_{field}"] = entry
        
        manual_section.columnconfigure(1, weight=1)
        row += 1
        
        # 認証情報セクション（必須）
        auth_section = ttk.LabelFrame(parent, text="★ 認証情報（必須）", padding=5)
        auth_section.grid(row=row, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
        
        auth_fields = [
            ("ユーザー名: *", "username"),
            ("パスワード: *", "password"),
        ]
        
        for i, (label, field) in enumerate(auth_fields):
            ttk.Label(auth_section, text=label, foreground="red" if "*" in label else "black").grid(
                row=i, column=0, sticky="e", padx=5, pady=2
            )

            entry = ttk.Entry(auth_section, width=22)
            entry.grid(row=i, column=1, sticky="ew", padx=5, pady=2)
            
            # パスワードフィールドは表示を隠す
            if field == "password":
                entry.config(show="*")
            
            self.entries[f"{prefix}_{field}"] = entry
        
        auth_section.columnconfigure(1, weight=1)
        
        parent.columnconfigure(1, weight=1)

    def _create_object_tab(self) -> None:
        """オブジェクト選択タブを作成。"""
        # 説明
        ttk.Label(
            self.object_frame,
            text="コピーするオブジェクトの種類を選択してください",
            font=("", 10, "bold")
        ).pack(pady=10)
        
        # オブジェクトタイプのチェックボックス
        self.object_vars: Dict[ObjectType, tk.BooleanVar] = {}
        
        checkbox_frame = ttk.Frame(self.object_frame)
        checkbox_frame.pack(pady=10)
        
        object_types = [
            (ObjectType.TABLE, "テーブル"),
            (ObjectType.VIEW, "ビュー"),
            (ObjectType.PROCEDURE, "プロシージャ"),
            (ObjectType.FUNCTION, "ファンクション"),
            (ObjectType.PACKAGE, "パッケージ"),
            (ObjectType.TRIGGER, "トリガー"),
            (ObjectType.SEQUENCE, "シーケンス"),
        ]
        
        for i, (obj_type, label) in enumerate(object_types):
            var = tk.BooleanVar(value=True)
            self.object_vars[obj_type] = var
            
            cb = ttk.Checkbutton(
                checkbox_frame,
                text=label,
                variable=var
            )
            cb.grid(row=i // 4, column=i % 4, sticky="w", padx=20, pady=5)
        
        # オプション
        option_frame = ttk.LabelFrame(
            self.object_frame,
            text="コピーオプション",
            padding=10
        )
        option_frame.pack(pady=10, padx=10, fill=tk.X)
        
        self.drop_before_create = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            option_frame,
            text="コピー前にターゲットのオブジェクトを削除 (DROP)",
            variable=self.drop_before_create
        ).pack(anchor="w")
        
        self.show_diff_confirmation = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            option_frame,
            text="コピー前に差分を確認する",
            variable=self.show_diff_confirmation
        ).pack(anchor="w")
        
        self.skip_errors = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            option_frame,
            text="エラーが発生しても続行",
            variable=self.skip_errors
        ).pack(anchor="w")
        
        # ワイルドカードフィルタ
        filter_frame = ttk.LabelFrame(
            self.object_frame,
            text="オブジェクト名フィルタ（ワイルドカード）",
            padding=10
        )
        filter_frame.pack(pady=10, padx=10, fill=tk.X)
        
        ttk.Label(
            filter_frame,
            text="パターン（カンマ区切り）:",
            font=("", 9)
        ).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        
        ttk.Label(
            filter_frame,
            text="例: USER_%, %_TMP, TEST% （% = 任意の文字列、_ = 任意の1文字、, = 複数指定（カンマ区切り））",
            foreground="gray",
            font=("", 8)
        ).grid(row=1, column=0, sticky="w", padx=5, pady=2)
        
        self.pattern_entry = ttk.Entry(filter_frame, width=60)
        self.pattern_entry.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        filter_frame.columnconfigure(0, weight=1)
        
        # オブジェクト一覧
        list_frame = ttk.LabelFrame(
            self.object_frame,
            text="ソースDBのオブジェクト一覧",
            padding=10
        )
        list_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        
        # ツールバー
        toolbar = ttk.Frame(list_frame)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(
            toolbar,
            text="フィルタして一覧を取得",
            command=self._refresh_object_list,
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            toolbar,
            text="すべて選択",
            command=self._select_all_objects,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            toolbar,
            text="すべて解除",
            command=self._deselect_all_objects,
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(
            toolbar,
            text="表示フィルタ:",
            font=("", 8)
        ).pack(side=tk.LEFT, padx=(10, 5))
        
        self.display_filter_entry = ttk.Entry(toolbar, width=25)
        self.display_filter_entry.pack(side=tk.LEFT, padx=5)
        self.display_filter_entry.bind('<KeyRelease>', lambda e: self._apply_display_filter())

        ttk.Button(
            toolbar,
            text="CSV出力",
            command=self._export_object_csv,
            width=12
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            toolbar,
            text="名前コピー",
            command=self._copy_object_names_to_clipboard,
            width=12
        ).pack(side=tk.LEFT, padx=5)

        # Treeviewとスクロールバー
        tree_container = ttk.Frame(list_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)
        
        # スクロールバー
        vsb = ttk.Scrollbar(tree_container, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(tree_container, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Treeview作成
        self.object_tree = ttk.Treeview(
            tree_container,
            columns=("name", "type", "created", "updated"),
            show="tree headings",
            height=20,
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            selectmode="extended"
        )
        self.object_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        vsb.config(command=self.object_tree.yview)
        hsb.config(command=self.object_tree.xview)
        
        # 列の設定
        self.object_tree.column("#0", width=25, minwidth=25, anchor="center")
        self.object_tree.column("name", width=250, minwidth=150, anchor="w")
        self.object_tree.column("type", width=120, minwidth=100, anchor="center")
        self.object_tree.column("created", width=150, minwidth=120, anchor="center")
        self.object_tree.column("updated", width=150, minwidth=120, anchor="center")
        
        # ヘッダーの設定（クリックでソート）
        self.object_tree.heading("#0", text="✓", anchor="center")
        self.object_tree.heading("name", text="オブジェクト名", anchor="w",
                                  command=lambda: self._sort_object_tree("name"))
        self.object_tree.heading("type", text="種類", anchor="center",
                                  command=lambda: self._sort_object_tree("type"))
        self.object_tree.heading("created", text="作成日", anchor="center",
                                  command=lambda: self._sort_object_tree("created"))
        self.object_tree.heading("updated", text="更新日", anchor="center",
                                  command=lambda: self._sort_object_tree("updated"))

        # チェックボックスのクリックイベント
        self.object_tree.bind("<Button-1>", self._on_tree_click)

        # ソート状態管理
        self.object_tree_sort_state: Dict[str, bool] = {}

        # オブジェクトデータを保持（フィルタ用）
        self.all_objects: List[DatabaseObject] = []
        self.object_check_states: Dict[str, bool] = {}  # オブジェクトIDごとのチェック状態

    def _create_execution_tab(self) -> None:
        """実行とログタブを作成。"""
        # 実行ボタン
        button_frame = ttk.Frame(self.execution_frame)
        button_frame.pack(pady=10)
        
        self.execute_button = ttk.Button(
            button_frame,
            text="コピー実行",
            command=self._execute_copy,
            width=20
        )
        self.execute_button.pack(side=tk.LEFT, padx=5)

        self.dry_run_button = ttk.Button(
            button_frame,
            text="ドライラン",
            command=self._execute_dry_run,
            width=20
        )
        self.dry_run_button.pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="差分確認",
            command=self._open_diff_view,
            width=20
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="ログをクリア",
            command=self._clear_log,
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="エラーのみ表示",
            command=self._show_error_summary,
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        # プログレスバー
        self.progress = ttk.Progressbar(
            self.execution_frame,
            mode='determinate'
        )
        self.progress.pack(fill=tk.X, padx=10, pady=5)
        
        # 進捗テキスト
        self.progress_text = ttk.Label(
            self.execution_frame,
            text="準備完了",
            foreground="blue"
        )
        self.progress_text.pack(pady=5)
        
        # ステータス
        self.status_label = ttk.Label(
            self.execution_frame,
            text="準備完了",
            foreground="green"
        )
        self.status_label.pack(pady=5)
        
        # ログ表示
        log_frame = ttk.LabelFrame(
            self.execution_frame,
            text="実行ログ",
            padding=10
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=20,
            font=("Courier", 9),
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _on_mode_changed(self) -> None:
        """Thin/Thick mode 切り替え時の処理。"""
        if self.thick_mode_var.get():
            self.client_lib_entry.config(state="normal")
            self.client_lib_browse_btn.config(state="normal")
        else:
            self.client_lib_entry.config(state="disabled")
            self.client_lib_browse_btn.config(state="disabled")

    def _browse_client_lib(self) -> None:
        """Oracle Instant Client ディレクトリを選択。"""
        from tkinter import filedialog
        directory = filedialog.askdirectory(
            title="Oracle Instant Client ディレクトリを選択"
        )
        if directory:
            self.client_lib_entry.delete(0, tk.END)
            self.client_lib_entry.insert(0, directory)

    def _copy_auth_to_target(self) -> None:
        """コピー元のユーザー名・パスワードをコピー先へ複写する"""
        username = self.entries["source_username"].get()
        password = self.entries["source_password"].get()
        self.entries["target_username"].delete(0, tk.END)
        self.entries["target_username"].insert(0, username)
        self.entries["target_password"].delete(0, tk.END)
        self.entries["target_password"].insert(0, password)

    def _test_connections(self) -> None:
        """接続テストを実行。"""
        self._log("接続テストを開始...")
        
        try:
            # ソース接続
            source_config = self._get_connection_config("source")
            self._log(f"ソースDB接続中: {source_config.host}:{source_config.port}/{source_config.service}")
            
            # ターゲット接続
            target_config = self._get_connection_config("target")
            self._log(f"ターゲットDB接続中: {target_config.host}:{target_config.port}/{target_config.service}")
            
            # DatabaseManagerの作成
            thick_mode = self.thick_mode_var.get()
            client_lib_dir = self.client_lib_entry.get().strip() if thick_mode else None
            self.db_manager = DatabaseManager(
                source_config, target_config,
                thick_mode=thick_mode,
                client_lib_dir=client_lib_dir or None
            )
            
            # 接続テスト
            if self.db_manager.test_connections():
                self._log("✓ 両方のデータベースに正常に接続できました", "success")
                messagebox.showinfo("成功", "接続テストに成功しました")
            else:
                self._log("✗ 接続テストに失敗しました", "error")
                detail = self.db_manager.last_connection_error
                if detail:
                    messagebox.showerror(
                        "エラー",
                        f"接続テストに失敗しました\n\n詳細:\n{detail}"
                    )
                else:
                    messagebox.showerror("エラー", "接続テストに失敗しました")
        
        except Exception as e:
            error_msg = f"接続エラー: {str(e)}"
            self._log(error_msg, "error")
            logging.error(error_msg, exc_info=True)
            messagebox.showerror("エラー", error_msg)

    def _get_connection_config(self, prefix: str) -> ConnectionConfig:
        """接続設定を取得。
        
        Args:
            prefix: source または target
            
        Returns:
            ConnectionConfig: 接続設定
        """
        return ConnectionConfig(
            host=self.entries[f"{prefix}_host"].get().strip(),
            port=int(self.entries[f"{prefix}_port"].get().strip()),
            service=self.entries[f"{prefix}_service"].get().strip(),
            username=self.entries[f"{prefix}_username"].get().strip(),
            password=self.entries[f"{prefix}_password"].get().strip()
        )
    
    def _get_name_patterns(self) -> Optional[List[str]]:
        """ワイルドカードパターンを取得。
        
        Returns:
            パターンのリスト、空の場合はNone
        """
        pattern_text = self.pattern_entry.get().strip()
        
        if not pattern_text:
            return None
        
        # カンマ区切りで分割、空白を除去
        patterns = [p.strip() for p in pattern_text.split(',') if p.strip()]
        
        return patterns if patterns else None

    def _refresh_object_list(self) -> None:
        """オブジェクト一覧を更新。"""
        if not self.db_manager:
            messagebox.showwarning("警告", "先に接続テストを実行してください")
            return
        
        self._log("オブジェクト一覧を取得中...")
        
        try:
            # 選択されたオブジェクトタイプ
            selected_types = [
                obj_type for obj_type, var in self.object_vars.items()
                if var.get()
            ]
            
            if not selected_types:
                messagebox.showwarning("警告", "少なくとも1つのオブジェクトタイプを選択してください")
                return
            
            # ワイルドカードパターンを取得
            name_patterns = self._get_name_patterns()
            if name_patterns:
                self._log(f"フィルタパターン: {', '.join(name_patterns)}")
            
            # オブジェクト一覧取得
            objects = self.db_manager.get_source_objects(selected_types, name_patterns)
            
            # オブジェクトデータを保存
            self.all_objects = objects
            
            # チェック状態を初期化（すべて選択状態）
            self.object_check_states.clear()
            for obj in objects:
                obj_id = f"{obj.object_type.value}:{obj.name}"
                self.object_check_states[obj_id] = True
            
            # Treeviewに表示
            self._display_objects(objects)
            
            self._log(f"✓ {len(objects)} 個のオブジェクトを取得しました", "success")
        
        except Exception as e:
            error_msg = f"オブジェクト一覧取得エラー: {str(e)}"
            self._log(error_msg, "error")
            logging.error(error_msg, exc_info=True)
            messagebox.showerror("エラー", error_msg)

    def _display_objects(self, objects: List[DatabaseObject]) -> None:
        """オブジェクトをTreeviewに表示。
        
        Args:
            objects: 表示するオブジェクトのリスト
        """
        # 既存項目をクリア
        for item in self.object_tree.get_children():
            self.object_tree.delete(item)
        
        # オブジェクトを表示
        for obj in objects:
            obj_id = f"{obj.object_type.value}:{obj.name}"
            is_checked = self.object_check_states.get(obj_id, True)
            check_mark = "☑" if is_checked else "☐"
            
            self.object_tree.insert(
                "",
                "end",
                iid=obj_id,
                text=check_mark,
                values=(
                    obj.name,
                    obj.object_type.value,
                    obj.created or "N/A",
                    obj.last_ddl_time or "N/A"
                )
            )

    def _on_tree_click(self, event) -> None:
        """Treeviewのクリックイベント処理（チェックボックストグル）。
        
        Args:
            event: クリックイベント
        """
        region = self.object_tree.identify("region", event.x, event.y)
        
        if region == "tree":
            # チェックボックス列がクリックされた
            item = self.object_tree.identify_row(event.y)
            if item:
                # チェック状態をトグル
                obj_id = item
                current_state = self.object_check_states.get(obj_id, True)
                new_state = not current_state
                self.object_check_states[obj_id] = new_state
                
                # 表示を更新
                check_mark = "☑" if new_state else "☐"
                self.object_tree.item(item, text=check_mark)

    def _select_all_objects(self) -> None:
        """すべてのオブジェクトを選択。"""
        for item in self.object_tree.get_children():
            self.object_check_states[item] = True
            self.object_tree.item(item, text="☑")
        
        self._log("すべてのオブジェクトを選択しました")

    def _deselect_all_objects(self) -> None:
        """すべてのオブジェクトの選択を解除。"""
        for item in self.object_tree.get_children():
            self.object_check_states[item] = False
            self.object_tree.item(item, text="☐")
        
        self._log("すべてのオブジェクトの選択を解除しました")

    def _apply_display_filter(self) -> None:
        """表示フィルタを適用（Treeviewの表示フィルタ）。"""
        filter_text = self.display_filter_entry.get().strip().upper()
        
        if not filter_text:
            # フィルタなし：すべてのオブジェクトを表示
            self._display_objects(self.all_objects)
        else:
            # フィルタあり：マッチするオブジェクトのみ表示
            filtered_objects = [
                obj for obj in self.all_objects
                if filter_text in obj.name.upper() or filter_text in obj.object_type.value.upper()
            ]
            self._display_objects(filtered_objects)

    def _apply_filter(self) -> None:
        """表示フィルタを適用（リストボックスの表示のみ）。"""
        # 注: これは表示フィルタのみ。実際のコピーには影響しない。
        # 実際のコピーフィルタはワイルドカードパターン欄で指定する。
        # 新しいTreeview実装では_apply_display_filterが使用される
        pass

    def _sort_object_tree(self, col: str) -> None:
        """オブジェクト一覧Treeviewを指定列でソート。"""
        asc = not self.object_tree_sort_state.get(col, False)
        self.object_tree_sort_state[col] = asc

        items = [(self.object_tree.set(iid, col).lower(), iid)
                 for iid in self.object_tree.get_children("")]
        items.sort(reverse=not asc)
        for idx, (_, iid) in enumerate(items):
            self.object_tree.move(iid, "", idx)

        _LABELS = {"name": "オブジェクト名", "type": "種類",
                   "created": "作成日", "updated": "更新日"}
        for c, label in _LABELS.items():
            ind = (" ▲" if asc else " ▼") if c == col else ""
            a = "w" if c == "name" else "center"
            self.object_tree.heading(c, text=label + ind, anchor=a,
                                     command=lambda _c=c: self._sort_object_tree(_c))

    def _export_object_csv(self) -> None:
        """オブジェクト一覧をCSVファイルに出力。"""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="objects.csv"
        )
        if not filepath:
            return
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["オブジェクト名", "種類", "作成日", "更新日", "選択"])
                for iid in self.object_tree.get_children(""):
                    vals = self.object_tree.item(iid, "values")
                    checked = "✓" if self.object_check_states.get(iid, False) else ""
                    writer.writerow(list(vals) + [checked])
            messagebox.showinfo("CSV出力", f"保存しました:\n{filepath}")
            self._log(f"CSV出力完了: {filepath}")
        except Exception as e:
            messagebox.showerror("エラー", f"CSV出力エラー: {e}")

    def _copy_object_names_to_clipboard(self) -> None:
        """選択中のオブジェクト名をクリップボードへコピー（未選択なら全件）。"""
        selected = self.object_tree.selection()
        items = selected if selected else self.object_tree.get_children("")
        names = [self.object_tree.set(iid, "name") for iid in items]
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(names))
        self._log(f"クリップボードにコピーしました ({len(names)} 件)")

    def _open_diff_view(self) -> None:
        """差分確認ウィンドウを「コピー実行」ボタンから独立して開く。"""
        if not self.db_manager:
            messagebox.showwarning("警告", "先に接続テストを実行してください")
            return
        selected_objects = self._get_selected_objects()
        if not selected_objects:
            messagebox.showwarning("警告", "オブジェクト一覧を取得してから確認してください")
            return
        self._show_diff_confirmation(selected_objects, view_only=True)

    def _execute_copy(self) -> None:
        """コピーを実行。"""
        if not self.db_manager:
            messagebox.showwarning("警告", "先に接続テストを実行してください")
            return
        
        # 選択されたオブジェクトを取得
        selected_objects = self._get_selected_objects()
        
        if not selected_objects:
            messagebox.showwarning("警告", "コピーするオブジェクトを選択してください")
            return
        
        # 差分確認オプションが有効な場合のみ表示
        if self.show_diff_confirmation.get():
            if not self._show_diff_confirmation(selected_objects, view_only=False):
                # ユーザーがキャンセルした場合
                return
        
        # 確認ダイアログ
        obj_count = len(selected_objects)
        type_counts = {}
        for obj in selected_objects:
            type_name = obj.object_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        type_summary = "\n".join([f"  {name}: {count}件" for name, count in sorted(type_counts.items())])
        message = f"以下のオブジェクトをコピーします:\n\n{type_summary}\n\n合計: {obj_count}件\n\n続行しますか？"
        
        if not messagebox.askyesno("確認", message):
            return
        
        # 別スレッドで実行
        thread = threading.Thread(target=self._execute_copy_thread, args=(selected_objects,))
        thread.daemon = True
        thread.start()

    def _get_selected_objects(self) -> List[DatabaseObject]:
        """選択されたオブジェクトを取得。
        
        Returns:
            選択されたDatabaseObjectのリスト
        """
        selected = []
        for obj in self.all_objects:
            obj_id = f"{obj.object_type.value}:{obj.name}"
            if self.object_check_states.get(obj_id, False):
                selected.append(obj)
        return selected

    def _show_diff_confirmation(self, selected_objects: List[DatabaseObject], view_only: bool = False) -> bool:
        """差分確認ウィンドウを表示。

        Args:
            selected_objects: コピー対象のオブジェクト
            view_only: True の場合は参照のみ（続行/キャンセルボタンなし）

        Returns:
            view_only=False時にユーザーが続行を選択した場合True。view_only=True時は常にTrue。
        """
        try:
            # ターゲットDB側のオブジェクト取得
            target_object_types = list(set(obj.object_type for obj in selected_objects))
            target_objects = self.db_manager.get_target_objects(target_object_types)
            
            # 差分比較
            diff_result = self.db_manager.compare_objects(selected_objects, target_objects)
            
            only_in_source = diff_result['only_in_source']
            only_in_target = diff_result['only_in_target']
            in_both = diff_result['in_both']

            # "両方に存在" タブで参照するターゲット側辞書
            target_dict = {(obj.name, obj.object_type): obj for obj in target_objects}

            # 「オブジェクト選択」タブのWCフィルタを「ターゲットのみ」にも適用
            name_patterns = self._get_name_patterns()
            if name_patterns:
                only_in_target = self.db_manager.filter_objects_by_pattern(only_in_target, name_patterns)

            # TNS / 接続情報ラベルを生成
            def _conn_label(prefix: str) -> str:
                combo = self.tns_combos.get(prefix)
                if combo:
                    val = combo.get()
                    if val and val not in ("（手動入力）", "tnsnames.ora が見つかりません"):
                        return val
                host = self.entries.get(f"{prefix}_host")
                service = self.entries.get(f"{prefix}_service")
                h = host.get().strip() if host else ""
                s = service.get().strip() if service else ""
                return f"{h}/{s}" if h else (s or "?")

            src_label = _conn_label("source")
            tgt_label = _conn_label("target")
            
            # 差分確認ウィンドウを作成
            diff_window = tk.Toplevel(self.root)
            diff_window.title("オブジェクト差分確認")
            diff_window.geometry("900x600")
            
            # 概要フレーム
            summary_frame = ttk.Frame(diff_window)
            summary_frame.pack(fill=tk.X, padx=10, pady=10)
            
            ttk.Label(
                summary_frame,
                text="コピー元とコピー先のオブジェクト差分",
                font=("Arial", 11, "bold")
            ).pack(anchor="w")
            
            # 統計情報
            stats_text = f"選択: {len(selected_objects)}件 | ソースのみ: {len(only_in_source)}件 | ターゲットのみ: {len(only_in_target)}件 | 両方に存在: {len(in_both)}件"
            ttk.Label(
                summary_frame,
                text=stats_text,
                foreground="blue"
            ).pack(anchor="w", pady=5)
            
            # ノートブック（タブ）
            notebook = ttk.Notebook(diff_window)
            notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            # タブ1: ソースのみ（TNS表示付き）
            self._create_diff_tab(notebook, f"ソースのみ [{src_label}]", only_in_source, "このオブジェクトは新規作成されます")
            
            # タブ2: ターゲットのみ（TNS表示付き・WCフィルタ適用済み）
            self._create_diff_tab(notebook, f"ターゲットのみ [{tgt_label}]", only_in_target, "このオブジェクトはターゲットに既に存在します")
            
            # タブ3: 両方に存在（ソース・ターゲット両方の日付を表示）
            self._create_diff_tab(notebook, "両方に存在", in_both, "このオブジェクトは上書きされます", target_dict=target_dict)
            
            # ボタンフレーム
            button_frame = ttk.Frame(diff_window)
            button_frame.pack(pady=10)

            # ユーザーが選択した結果を保持
            user_choice = {'continue': False}

            if view_only:
                # 参照専用モード: 閉じるボタンのみ
                ttk.Button(
                    button_frame,
                    text="閉じる",
                    command=diff_window.destroy,
                    width=15
                ).pack(side=tk.LEFT, padx=5)
                diff_window.wait_window()
                return True
            else:
                # コピー実行フロー: 続行 / キャンセル
                def on_continue():
                    user_choice['continue'] = True
                    diff_window.destroy()

                ttk.Button(
                    button_frame,
                    text="続行",
                    command=on_continue,
                    width=15
                ).pack(side=tk.LEFT, padx=5)

                ttk.Button(
                    button_frame,
                    text="キャンセル",
                    command=diff_window.destroy,
                    width=15
                ).pack(side=tk.LEFT, padx=5)

                # ウィンドウが閉じられるまで待機
                diff_window.wait_window()

                return user_choice['continue']
        
        except Exception as e:
            error_msg = f"差分確認エラー: {str(e)}"
            self._log(error_msg, "error")
            logging.error(error_msg, exc_info=True)
            messagebox.showerror("エラー", error_msg)
            return False
    
    def _create_diff_tab(
        self,
        notebook: ttk.Notebook,
        tab_name: str,
        objects: List[DatabaseObject],
        description: str,
        target_dict: Optional[Dict] = None
    ) -> None:
        """差分タブを作成。target_dict が与えられた場合はソース・ターゲット両方の日付を表示。"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=f"{tab_name} ({len(objects)}件)")

        # ツールバー
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, padx=10, pady=(5, 0))

        ttk.Label(
            toolbar,
            text=description,
            foreground="gray",
            font=("Arial", 9)
        ).pack(side=tk.LEFT)

        # ツリービュー
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        if target_dict is not None:
            # 両方に存在: ソース・ターゲット両方の作成日・更新日＋DDL比較列を表示
            cols = ("type", "src_created", "src_updated", "tgt_created", "tgt_updated", "ddl_diff")
            _HEADING = {
                "#0": "オブジェクト名",
                "type": "種類",
                "src_created": "ソース作成日",
                "src_updated": "ソース更新日",
                "tgt_created": "ターゲット作成日",
                "tgt_updated": "ターゲット更新日",
                "ddl_diff": "DDL差異",
            }
            col_widths = {"type": 120, "src_created": 140, "src_updated": 140,
                          "tgt_created": 140, "tgt_updated": 140, "ddl_diff": 90}
        else:
            cols = ("type", "created")
            _HEADING = {"#0": "オブジェクト名", "type": "種類", "created": "作成日"}
            col_widths = {"type": 120, "created": 150}

        tree = ttk.Treeview(
            tree_frame,
            columns=cols,
            show="tree headings",
            height=15,
            yscrollcommand=scrollbar.set,
            selectmode="extended"
        )
        tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)

        # 列設定
        tree.column("#0", width=250, minwidth=150, anchor="w")
        for col in cols:
            tree.column(col, width=col_widths[col], minwidth=80, anchor="center")

        # ソート状態
        sort_state: Dict[str, bool] = {}

        def sort_diff_tree(col: str) -> None:
            asc = not sort_state.get(col, False)
            sort_state[col] = asc
            if col == "#0":
                items = [(tree.item(iid, "text").lower(), iid) for iid in tree.get_children("")]
            else:
                items = [(tree.set(iid, col).lower(), iid) for iid in tree.get_children("")]
            items.sort(reverse=not asc)
            for idx, (_, iid) in enumerate(items):
                tree.move(iid, "", idx)
            for c, label in _HEADING.items():
                ind = (" ▲" if asc else " ▼") if c == col else ""
                a = "w" if c == "#0" else "center"
                tree.heading(c, text=label + ind, anchor=a)

        # ヘッダー設定（クリックでソート）
        for col, label in _HEADING.items():
            a = "w" if col == "#0" else "center"
            tree.heading(col, text=label, anchor=a,
                         command=lambda _c=col: sort_diff_tree(_c))

        # CSV出力
        def export_diff_csv() -> None:
            filepath = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile=f"{tab_name.split('[')[0].strip()}.csv"
            )
            if not filepath:
                return
            try:
                with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(list(_HEADING.values()))
                    for iid in tree.get_children(""):
                        name = tree.item(iid, "text")
                        vals = tree.item(iid, "values")
                        writer.writerow([name] + list(vals))
                messagebox.showinfo("CSV出力", f"保存しました:\n{filepath}")
            except Exception as e:
                messagebox.showerror("エラー", f"CSV出力エラー: {e}")

        # クリップボードコピー
        def copy_diff_names() -> None:
            selected = tree.selection()
            items = selected if selected else tree.get_children("")
            names = [tree.item(iid, "text") for iid in items]
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(names))

        # ツールバーにボタン追加
        ttk.Button(toolbar, text="CSV出力", command=export_diff_csv,
                   width=10).pack(side=tk.RIGHT, padx=5)
        ttk.Button(toolbar, text="名前コピー", command=copy_diff_names,
                   width=10).pack(side=tk.RIGHT, padx=5)

        # 両方に存在タブの場合のみDDL比較ボタンを追加
        if target_dict is not None:
            ddl_progress_label = ttk.Label(toolbar, text="", foreground="blue", font=("Arial", 9))
            ddl_progress_label.pack(side=tk.RIGHT, padx=10)

            ddl_btn = ttk.Button(toolbar, text="DDL比較実行", width=14)
            ddl_btn.pack(side=tk.RIGHT, padx=5)

            def _run_ddl_compare():
                ddl_btn.config(state="disabled")
                iids = list(tree.get_children(""))
                total = len(iids)

                def _worker():
                    for i, iid in enumerate(iids, 1):
                        name = tree.item(iid, "text")
                        vals = list(tree.item(iid, "values"))
                        obj_type_val = vals[0]
                        try:
                            obj_type_enum = ObjectType(obj_type_val)
                        except ValueError:
                            result_str = "取得失敗"
                        else:
                            try:
                                same = self.db_manager.compare_object_ddl(name, obj_type_enum)
                                if same is None:
                                    result_str = "取得失敗"
                                elif same:
                                    result_str = "同一"
                                else:
                                    result_str = "★差異あり"
                            except Exception:
                                result_str = "取得失敗"

                        vals[5] = result_str  # ddl_diff列 (index 5)
                        iid_cap = iid  # closure capture
                        vals_cap = vals[:]
                        result_cap = result_str
                        self.root.after(0, lambda _i=iid_cap, _v=vals_cap, _r=result_cap: (
                            tree.item(_i, values=_v),
                            tree.item(_i, tags=("diff",) if _r == "★差異あり" else ("same",) if _r == "同一" else ()),
                        ))
                        self.root.after(0, ddl_progress_label.config,
                                        {"text": f"比較中... {i}/{total}"})

                    self.root.after(0, ddl_progress_label.config, {"text": f"完了 ({total}件)"})
                    self.root.after(0, ddl_btn.config, {"state": "normal"})

                tree.tag_configure("diff", foreground="red")
                tree.tag_configure("same", foreground="gray")
                import threading as _t
                _t.Thread(target=_worker, daemon=True).start()

            ddl_btn.config(command=_run_ddl_compare)

            # ダブルクリックでDDL比較ウィンドウを開く
            def _on_double_click(event):
                iid = tree.identify_row(event.y)
                if not iid:
                    return
                name = tree.item(iid, "text")
                obj_type_val = tree.set(iid, "type")
                try:
                    obj_type_enum = ObjectType(obj_type_val)
                except ValueError:
                    return
                self._show_ddl_diff_window(name, obj_type_enum)

            tree.bind("<Double-1>", _on_double_click)

        # オブジェクトを表示
        for obj in objects:
            if target_dict is not None:
                tgt = target_dict.get((obj.name, obj.object_type))
                values = (
                    obj.object_type.value,
                    obj.created or "N/A",
                    obj.last_ddl_time or "N/A",
                    (tgt.created if tgt else None) or "N/A",
                    (tgt.last_ddl_time if tgt else None) or "N/A",
                    "─",
                )
            else:
                values = (obj.object_type.value, obj.created or "N/A")
            tree.insert("", "end", text=obj.name, values=values)


    def _show_ddl_diff_window(self, object_name: str, object_type: ObjectType) -> None:
        """ソース/ターゲットのDDLをサイドバイサイドで比較するウィンドウを表示。"""
        win = tk.Toplevel(self.root)
        win.title(f"DDL比較: {object_type.value} {object_name}")
        win.geometry("1200x700")

        # 上部の情報バー
        info_frame = ttk.Frame(win)
        info_frame.pack(fill=tk.X, padx=10, pady=(8, 4))
        ttk.Label(info_frame, text=f"{object_type.value}  {object_name}",
                  font=("Arial", 11, "bold")).pack(side=tk.LEFT)
        status_label = ttk.Label(info_frame, text="取得中...", foreground="blue")
        status_label.pack(side=tk.LEFT, padx=20)

        # 左右ペイン
        pane = ttk.PanedWindow(win, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        def _make_pane(title: str) -> scrolledtext.ScrolledText:
            outer = ttk.LabelFrame(pane, text=title)
            pane.add(outer, weight=1)
            txt = scrolledtext.ScrolledText(
                outer, font=("Courier", 9), wrap=tk.NONE,
                state="disabled"
            )
            # 横スクロール
            hsb = ttk.Scrollbar(outer, orient="horizontal", command=txt.xview)
            hsb.pack(side=tk.BOTTOM, fill=tk.X)
            txt.configure(xscrollcommand=hsb.set)
            txt.pack(fill=tk.BOTH, expand=True)
            return txt

        src_text = _make_pane("ソース")
        tgt_text = _make_pane("ターゲット")

        # 差分のハイライト色
        for t in (src_text, tgt_text):
            t.tag_configure("diff_line", background="#ffe0e0")
            t.tag_configure("same_line", background="")

        def _set_text(widget: scrolledtext.ScrolledText, content: str) -> None:
            widget.configure(state="normal")
            widget.delete("1.0", tk.END)
            widget.insert(tk.END, content)
            widget.configure(state="disabled")

        def _highlight_diff(
            src_t: scrolledtext.ScrolledText,
            tgt_t: scrolledtext.ScrolledText,
            src_ddl: str,
            tgt_ddl: str
        ) -> None:
            """行単位で差分行をハイライト。"""
            import difflib
            src_lines = src_ddl.splitlines()
            tgt_lines = tgt_ddl.splitlines()
            matcher = difflib.SequenceMatcher(None, src_lines, tgt_lines)

            for t in (src_t, tgt_t):
                t.configure(state="normal")
                t.tag_remove("diff_line", "1.0", tk.END)

            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag != "equal":
                    for lineno in range(i1 + 1, i2 + 1):
                        src_t.tag_add("diff_line", f"{lineno}.0", f"{lineno}.end+1c")
                    for lineno in range(j1 + 1, j2 + 1):
                        tgt_t.tag_add("diff_line", f"{lineno}.0", f"{lineno}.end+1c")

            for t in (src_t, tgt_t):
                t.configure(state="disabled")

        def _worker():
            try:
                src_ddl = self.db_manager.get_object_ddl(
                    object_name, object_type, use_target=False) or "(DDL取得失敗)"
                tgt_ddl = self.db_manager.get_object_ddl(
                    object_name, object_type, use_target=True) or "(DDL取得失敗)"
            except Exception as e:
                src_ddl = tgt_ddl = f"(取得エラー: {e})"

            import re as _re
            def _norm(s: str) -> str:
                return _re.sub(r'\s+', ' ', s).strip().upper()

            is_same = _norm(src_ddl) == _norm(tgt_ddl)
            status = "同一" if is_same else "★差異あり"
            color = "gray" if is_same else "red"

            self.root.after(0, _set_text, src_text, src_ddl)
            self.root.after(0, _set_text, tgt_text, tgt_ddl)
            self.root.after(0, status_label.config, {"text": status, "foreground": color})
            if not is_same:
                self.root.after(0, _highlight_diff, src_text, tgt_text, src_ddl, tgt_ddl)

        import threading as _t
        _t.Thread(target=_worker, daemon=True).start()

    def _execute_copy_thread(self, selected_objects: List[DatabaseObject], is_dry_run: bool = False) -> None:
        """コピーを実行（スレッド）。
        
        Args:
            selected_objects: コピーする選択されたオブジェクト
            is_dry_run: ドライランモードか
        """
        self.root.after(0, self._set_executing_state, True)
        self.root.after(0, self.progress.config, {'maximum': len(selected_objects)})
        self.root.after(0, self.progress.config, {'value': 0})
        
        try:
            self._log("=" * 60)
            if is_dry_run:
                self._log("【ドライランモード】検証を開始します...")
            else:
                self._log("コピー処理を開始します...")
            self._log("=" * 60)
            
            self._log(f"対象: {len(selected_objects)}件のオブジェクト")
            
            # 進捗コールバック
            def progress_callback(current: int, total: int, message: str) -> None:
                progress_percent = (current / total * 100) if total > 0 else 0
                progress_text = f"進捗: {current}/{total} ({progress_percent:.0f}%) - {message}"
                self.root.after(0, self.progress_text.config, {'text': progress_text})
                self.root.after(0, self.progress.config, {'value': current})
                self.root.after(0, self.progress.update)
            
            # コピー実行（specific_objectsパラメータで選択されたオブジェクトを渡す）
            results = self.db_manager.copy_objects(
                object_types=[],  # specific_objectsを使うため不要
                drop_before_create=self.drop_before_create.get(),
                skip_errors=self.skip_errors.get(),
                specific_objects=selected_objects,
                is_dry_run=is_dry_run,
                progress_callback=progress_callback
            )
            
            # 結果をログに表示
            self._log("\n" + "=" * 60)
            if is_dry_run:
                self._log("ドライラン結果")
            else:
                self._log("コピー結果")
            self._log("=" * 60)
            
            success_count = sum(1 for r in results if r.success)
            total_count = len(results)
            
            for result in results:
                status = "✓" if result.success else "✗"
                self._log(
                    f"{status} {result.object_type.name:<12} {result.object_name}",
                    "success" if result.success else "error"
                )
                if result.error_message:
                    self._log(f"  エラー: {result.error_message}", "error")
            
            self._log("\n" + "=" * 60)
            self._log(f"完了: {success_count}/{total_count} 件成功")
            self._log("=" * 60)
            
            # 進捗表示をリセット
            self.root.after(0, self.progress_text.config, {'text': f"完了: {success_count}/{total_count} 件成功"})
            
            # 完了メッセージ
            message = f"{'ドライラン' if is_dry_run else 'コピー'}が完了しました\n\n成功: {success_count}/{total_count} 件"
            self.root.after(0, messagebox.showinfo, "完了", message)
        
        except Exception as e:
            error_msg = f"実行エラー: {str(e)}"
            self._log(error_msg, "error")
            logging.error(error_msg, exc_info=True)
            self.root.after(0, messagebox.showerror, "エラー", error_msg)
        
        finally:
            self.root.after(0, self._set_executing_state, False)

    def _execute_dry_run(self) -> None:
        """ドライランを実行。"""
        if not self.db_manager:
            messagebox.showwarning("警告", "先に接続テストを実行してください")
            return
        
        # 選択されたオブジェクトを取得
        selected_objects = self._get_selected_objects()
        
        if not selected_objects:
            messagebox.showwarning("警告", "検証するオブジェクトを選択してください")
            return
        
        # 確認ダイアログ
        obj_count = len(selected_objects)
        type_counts = {}
        for obj in selected_objects:
            type_name = obj.object_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        type_summary = "\n".join([f"  {name}: {count}件" for name, count in sorted(type_counts.items())])
        message = f"以下のオブジェクトの検証を行います:\n\n{type_summary}\n\n合計: {obj_count}件\n\n続行しますか？"
        
        if not messagebox.askyesno("確認", message):
            return
        
        # 別スレッドで実行
        thread = threading.Thread(target=self._execute_copy_thread, args=(selected_objects, True))
        thread.daemon = True
        thread.start()

    def _set_executing_state(self, executing: bool) -> None:
        """実行中の状態を設定。
        
        Args:
            executing: 実行中かどうか
        """
        if executing:
            self.execute_button.config(state=tk.DISABLED)
            self.dry_run_button.config(state=tk.DISABLED)
            self.progress.config(value=0)
            self.status_label.config(text="実行中...", foreground="orange")
        else:
            self.execute_button.config(state=tk.NORMAL)
            self.dry_run_button.config(state=tk.NORMAL)
            self.progress.config(value=0)
            self.progress_text.config(text="準備完了")
            self.status_label.config(text="準備完了", foreground="green")

    def _on_tns_selected(self, prefix: str) -> None:
        """TNSエントリが選択されたときの処理。
        
        Args:
            prefix: source または target
        """
        if prefix not in self.tns_combos:
            return
        
        selected = self.tns_combos[prefix].get()
        
        if selected == "（手動入力）" or not self.tns_parser:
            # 手動入力モード: フィールドを編集可能に
            self.entries[f"{prefix}_host"].config(state="normal")
            self.entries[f"{prefix}_port"].config(state="normal")
            self.entries[f"{prefix}_service"].config(state="normal")
            # フィールドをクリア
            self.entries[f"{prefix}_host"].delete(0, tk.END)
            self.entries[f"{prefix}_port"].delete(0, tk.END)
            self.entries[f"{prefix}_port"].insert(0, "1521")
            self.entries[f"{prefix}_service"].delete(0, tk.END)
            return
        
        # TNSエントリを取得
        entry = self.tns_parser.get_entry(selected)
        
        if entry:
            # 接続情報を自動入力
            self.entries[f"{prefix}_host"].config(state="normal")
            self.entries[f"{prefix}_host"].delete(0, tk.END)
            self.entries[f"{prefix}_host"].insert(0, entry.host)
            self.entries[f"{prefix}_host"].config(state="readonly")
            
            self.entries[f"{prefix}_port"].config(state="normal")
            self.entries[f"{prefix}_port"].delete(0, tk.END)
            self.entries[f"{prefix}_port"].insert(0, str(entry.port))
            self.entries[f"{prefix}_port"].config(state="readonly")
            
            service = entry.service_name or entry.sid or ""
            self.entries[f"{prefix}_service"].config(state="normal")
            self.entries[f"{prefix}_service"].delete(0, tk.END)
            self.entries[f"{prefix}_service"].insert(0, service)
            self.entries[f"{prefix}_service"].config(state="readonly")
            
            self._log(f"TNSエントリ '{selected}' の接続情報を読み込みました（接続情報は自動入力、認証情報は手動入力してください）", "success")
        else:
            # HOST が解析できなかった場合（BEQプロトコル等）
            messagebox.showwarning(
                "TNSエントリ解析失敗",
                f"TNSエントリ '{selected}' のHOST/PORT情報を解析できませんでした。\n\n"
                "BEQプロトコル（ローカルIPC）または非標準形式の可能性があります。\n"
                "ホスト・ポート・サービス名を手動で入力してください。"
            )
            # フィールドを編集可能に戻す
            for field in (f"{prefix}_host", f"{prefix}_port", f"{prefix}_service"):
                self.entries[field].config(state="normal")
            self._log(f"警告: TNSエントリ '{selected}' のHOST情報を解析できませんでした。手動で入力してください。", "warning")
    
    def _select_tnsnames_file(self) -> None:
        """tnsnames.ora ファイルを選択。"""
        filename = filedialog.askopenfilename(
            title="tnsnames.ora ファイルを選択",
            filetypes=[
                ("Oracle TNS ファイル", "*.ora"),
                ("すべてのファイル", "*.*")
            ]
        )
        
        if filename:
            try:
                self.tns_parser = TnsNamesParser(filename)
                
                if self.tns_parser.has_tnsnames():
                    self._log(f"tnsnames.ora を読み込みました: {filename}", "success")
                    
                    # ドロップダウンを更新
                    self._update_tns_combos()
                    
                    # 詳細情報をダイアログに表示
                    self._show_tnsnames_dialog()
                else:
                    messagebox.showerror("エラー", "有効な tnsnames.ora ファイルではありません")
            
            except Exception as e:
                error_msg = f"tnsnames.ora の読み込みエラー: {str(e)}"
                self._log(error_msg, "error")
                logging.error(error_msg, exc_info=True)
                messagebox.showerror("エラー", error_msg)
    
    def _update_tns_combos(self) -> None:
        """TNSエントリドロップダウンを更新。"""
        if not self.tns_parser or not self.tns_parser.has_tnsnames():
            for combo in self.tns_combos.values():
                combo.config(values=["（手動入力）", "tnsnames.ora が見つかりません"])
            return

        tns_entries = sorted(self.tns_parser.get_entries().keys())
        combo_values = ["（手動入力）"] + tns_entries

        for prefix, combo in self.tns_combos.items():
            combo.config(values=combo_values)
            combo.set("（手動入力）")
            # 選択イベントを再バインド（手動読込後も機能するように）
            combo.unbind("<<ComboboxSelected>>")
            combo.bind(
                "<<ComboboxSelected>>",
                lambda e, p=prefix: self._on_tns_selected(p)
            )
    
    def _show_tnsnames_entries(self) -> None:
        """tnsnames.ora の読み込み結果をダイアログに表示。"""
        if not self.tns_parser or not self.tns_parser.has_tnsnames():
            messagebox.showwarning("警告", "tnsnames.ora が読み込まれていません")
            return
        
        self._show_tnsnames_dialog()
    
    def _show_tnsnames_dialog(self) -> None:
        """tnsnames.ora の詳細情報をダイアログ表示。"""
        if not self.tns_parser or not self.tns_parser.has_tnsnames():
            return
        
        entries = self.tns_parser.get_entries()
        if not entries:
            messagebox.showinfo("情報", "tnsnames.ora にエントリがありません")
            return
        
        # ダイアログウィンドウを作成
        dialog = tk.Toplevel(self.root)
        dialog.title("tnsnames.ora エントリ一覧")
        dialog.geometry("900x600")
        
        # ヘッダー
        header_frame = ttk.Frame(dialog)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(
            header_frame,
            text=f"tnsnames.ora: {self.tns_parser.get_tnsnames_path()}",
            foreground="green",
            font=("Arial", 10, "bold")
        ).pack(anchor="w")
        
        ttk.Label(
            header_frame,
            text=f"読み込まれたエントリ: {len(entries)} 件",
            foreground="blue"
        ).pack(anchor="w", pady=5)
        
        # スクロール可能なテキスト表示
        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        content_text = tk.Text(
            text_frame,
            height=20,
            width=100,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set
        )
        scrollbar.config(command=content_text.yview)
        content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # エントリ情報をテキストに挿入
        content = self.tns_parser.display_entries()
        content_text.insert(tk.END, content)
        content_text.config(state=tk.DISABLED)
        
        # ボタンフレーム
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        
        ttk.Button(
            button_frame,
            text="閉じる",
            command=dialog.destroy,
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="クリップボードにコピー",
            command=lambda: self._copy_to_clipboard(content),
            width=25
        ).pack(side=tk.LEFT, padx=5)
    
    def _copy_to_clipboard(self, text: str) -> None:
        """テキストをクリップボードにコピー。"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("成功", "クリップボードにコピーしました")

    def _save_config(self) -> None:
        """設定を保存。"""
        # パスワード保存の警告
        save_password = messagebox.askyesno(
            "設定保存の確認",
            "接続設定を保存します。\n\n"
            "⚠️ パスワードは平文で保存されます。\n"
            "セキュリティ上のリスクがあります。\n\n"
            "パスワードを含めて保存しますか？\n\n"
            "※「いいえ」を選択するとパスワード以外を保存します。"
        )
        
        try:
            config = {
                "source": {
                    "host": self.entries["source_host"].get().strip(),
                    "port": self.entries["source_port"].get().strip(),
                    "service": self.entries["source_service"].get().strip(),
                    "username": self.entries["source_username"].get().strip(),
                },
                "target": {
                    "host": self.entries["target_host"].get().strip(),
                    "port": self.entries["target_port"].get().strip(),
                    "service": self.entries["target_service"].get().strip(),
                    "username": self.entries["target_username"].get().strip(),
                },
                "connection_mode": {
                    "thick_mode": self.thick_mode_var.get(),
                    "client_lib_dir": self.client_lib_entry.get().strip() or "",
                }
            }
            
            # パスワードを保存する場合
            if save_password:
                config["source"]["password"] = self.entries["source_password"].get()
                config["target"]["password"] = self.entries["target_password"].get()
            
            # ファイルダイアログで保存先を選択
            filename = filedialog.asksaveasfilename(
                title="設定ファイルを保存",
                defaultextension=".yaml",
                filetypes=[
                    ("YAML ファイル", "*.yaml"),
                    ("すべてのファイル", "*.*")
                ],
                initialfile="db_connection_config.yaml"
            )
            
            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
                
                self._log(f"設定を保存しました: {filename}", "success")
                messagebox.showinfo("成功", f"設定ファイルを保存しました\n\n{filename}")
        
        except Exception as e:
            error_msg = f"設定保存エラー: {str(e)}"
            self._log(error_msg, "error")
            logging.error(error_msg, exc_info=True)
            messagebox.showerror("エラー", error_msg)

    def _load_config(self) -> None:
        """設定を読込。"""
        try:
            # ファイルダイアログで読み込むファイルを選択
            filename = filedialog.askopenfilename(
                title="設定ファイルを開く",
                filetypes=[
                    ("YAML ファイル", "*.yaml"),
                    ("すべてのファイル", "*.*")
                ]
            )
            
            if not filename:
                return
            
            with open(filename, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # ソースDB設定を読み込み
            if "source" in config:
                source = config["source"]
                self.entries["source_host"].delete(0, tk.END)
                self.entries["source_host"].insert(0, source.get("host", ""))
                
                self.entries["source_port"].delete(0, tk.END)
                self.entries["source_port"].insert(0, source.get("port", "1521"))
                
                self.entries["source_service"].delete(0, tk.END)
                self.entries["source_service"].insert(0, source.get("service", ""))
                
                self.entries["source_username"].delete(0, tk.END)
                self.entries["source_username"].insert(0, source.get("username", ""))
                
                if "password" in source:
                    self.entries["source_password"].delete(0, tk.END)
                    self.entries["source_password"].insert(0, source["password"])
            
            # ターゲットDB設定を読み込み
            if "target" in config:
                target = config["target"]
                self.entries["target_host"].delete(0, tk.END)
                self.entries["target_host"].insert(0, target.get("host", ""))
                
                self.entries["target_port"].delete(0, tk.END)
                self.entries["target_port"].insert(0, target.get("port", "1521"))
                
                self.entries["target_service"].delete(0, tk.END)
                self.entries["target_service"].insert(0, target.get("service", ""))
                
                self.entries["target_username"].delete(0, tk.END)
                self.entries["target_username"].insert(0, target.get("username", ""))
                
                if "password" in target:
                    self.entries["target_password"].delete(0, tk.END)
                    self.entries["target_password"].insert(0, target["password"])

            # 接続モード設定を読み込み
            if "connection_mode" in config:
                mode = config["connection_mode"]
                self.thick_mode_var.set(bool(mode.get("thick_mode", False)))
                self._on_mode_changed()
                lib_dir = mode.get("client_lib_dir", "")
                if lib_dir:
                    self.client_lib_entry.delete(0, tk.END)
                    self.client_lib_entry.insert(0, lib_dir)

            self._log(f"設定を読み込みました: {filename}", "success")
            messagebox.showinfo("成功", f"設定ファイルを読み込みました\n\n{filename}")
        
        except Exception as e:
            error_msg = f"設定読込エラー: {str(e)}"
            self._log(error_msg, "error")
            logging.error(error_msg, exc_info=True)
            messagebox.showerror("エラー", error_msg)

    def _clear_log(self) -> None:
        """ログをクリア。"""
        self.log_text.delete(1.0, tk.END)
        self.error_logs.clear()

    def _log(self, message: str, level: str = "info") -> None:
        """ログを出力。
        
        Args:
            message: メッセージ
            level: ログレベル (info/success/error/warning)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        # ログファイルにも記録
        if level == "error":
            logging.error(message)
        elif level == "warning":
            logging.warning(message)
        else:
            logging.info(message)
        
        # GUIに表示
        self.log_text.insert(tk.END, log_message)
        
        # 色付けとエラー保存
        if level == "success":
            # 最後の行を緑色に
            last_line = self.log_text.index(tk.END)
            start = f"{last_line} - 1 lines"
            self.log_text.tag_add("success", start, tk.END)
            self.log_text.tag_config("success", foreground="green")
        elif level == "error":
            last_line = self.log_text.index(tk.END)
            start = f"{last_line} - 1 lines"
            self.log_text.tag_add("error", start, tk.END)
            self.log_text.tag_config("error", foreground="red")
            # エラー情報を保存
            self.error_logs.append(log_message.strip())
        elif level == "warning":
            last_line = self.log_text.index(tk.END)
            start = f"{last_line} - 1 lines"
            self.log_text.tag_add("warning", start, tk.END)
            self.log_text.tag_config("warning", foreground="orange")
        
        # 自動スクロール
        self.log_text.see(tk.END)

    def _show_error_summary(self) -> None:
        """エラーサマリーを表示。"""
        if not self.error_logs:
            messagebox.showinfo("エラー情報", "エラーログはありません")
            return
        
        # エラーサマリーウィンドウを作成
        error_window = tk.Toplevel(self.root)
        error_window.title("エラーサマリー")
        error_window.geometry("800x600")
        
        # タイトル
        ttk.Label(
            error_window,
            text=f"合計 {len(self.error_logs)} 件のエラーが発生しました",
            font=("Arial", 10, "bold"),
            foreground="red"
        ).pack(pady=10)
        
        # スクロール可能なテキスト表示
        error_frame = ttk.Frame(error_window)
        error_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(error_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        error_text = tk.Text(
            error_frame,
            font=("Courier", 9),
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set
        )
        error_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=error_text.yview)
        
        # エラーログを表示
        for idx, error in enumerate(self.error_logs, 1):
            error_text.insert(tk.END, f"{idx}. {error}\n\n")
        
        error_text.config(state=tk.DISABLED)  # 読み取り専用
        
        # ボタンフレーム
        button_frame = ttk.Frame(error_window)
        button_frame.pack(pady=10)
        
        ttk.Button(
            button_frame,
            text="コピー",
            command=lambda: self._copy_error_text(error_text),
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="閉じる",
            command=error_window.destroy,
            width=15
        ).pack(side=tk.LEFT, padx=5)
    
    def _copy_error_text(self, text_widget: tk.Text) -> None:
        """エラーテキストをクリップボードにコピー。"""
        try:
            error_text = text_widget.get(1.0, tk.END)
            self.root.clipboard_clear()
            self.root.clipboard_append(error_text)
            messagebox.showinfo("完了", "エラーログをクリップボードにコピーしました")
        except Exception as e:
            messagebox.showerror("エラー", f"コピーに失敗しました: {e}")


def main():
    """メイン関数。"""
    root = tk.Tk()
    app = DBCopyToolGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
