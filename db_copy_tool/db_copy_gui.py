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

from db_manager import (
    DatabaseManager,
    DatabaseObject,
    ObjectType,
    CopyResult,
    ConnectionConfig
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
        self.root.geometry("1000x700")
        
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
        # tnsnames.ora 読み込みボタン
        tns_toolbar = ttk.Frame(self.connection_frame)
        tns_toolbar.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        
        if self.tns_parser and self.tns_parser.has_tnsnames():
            info_text = f"tnsnames.ora: {self.tns_parser.get_tnsnames_path()}"
            ttk.Label(
                tns_toolbar,
                text=info_text,
                foreground="green"
            ).pack(side=tk.LEFT, padx=5)
        else:
            ttk.Label(
                tns_toolbar,
                text="tnsnames.ora が見つかりません",
                foreground="orange"
            ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            tns_toolbar,
            text="tnsnames.ora を選択",
            command=self._select_tnsnames_file,
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        # ソースDB設定
        source_frame = ttk.LabelFrame(
            self.connection_frame,
            text="ソースデータベース（コピー元）",
            padding=10
        )
        source_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        
        self._create_db_fields(source_frame, "source")
        
        # ターゲットDB設定
        target_frame = ttk.LabelFrame(
            self.connection_frame,
            text="ターゲットデータベース（コピー先）",
            padding=10
        )
        target_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        
        self._create_db_fields(target_frame, "target")
        
        # 接続テストボタン
        button_frame = ttk.Frame(self.connection_frame)
        button_frame.grid(row=3, column=0, pady=10)
        
        ttk.Button(
            button_frame,
            text="接続テスト",
            command=self._test_connections,
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="設定を保存",
            command=self._save_config,
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame,
            text="設定を読込",
            command=self._load_config,
            width=20
        ).pack(side=tk.LEFT, padx=5)

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
        
        # TNSエントリ選択（tnsnames.oraが利用可能な場合）
        row = 0
        if self.tns_parser and self.tns_parser.has_tnsnames():
            ttk.Label(parent, text="TNS エントリ:").grid(
                row=row, column=0, sticky="e", padx=5, pady=5
            )
            
            tns_entries = list(self.tns_parser.get_entries().keys())
            tns_combo = ttk.Combobox(
                parent,
                values=["（手動入力）"] + tns_entries,
                state="readonly",
                width=38
            )
            tns_combo.set("（手動入力）")
            tns_combo.grid(row=row, column=1, sticky="ew", padx=5, pady=5)
            tns_combo.bind("<<ComboboxSelected>>", 
                          lambda e, p=prefix: self._on_tns_selected(p))
            
            self.tns_combos[prefix] = tns_combo
            row += 1
        
        fields = [
            ("ホスト:", "host"),
            ("ポート:", "port"),
            ("サービス名/SID:", "service"),
            ("ユーザー名:", "username"),
            ("パスワード:", "password"),
        ]
        
        for i, (label, field) in enumerate(fields):
            ttk.Label(parent, text=label).grid(
                row=row + i, column=0, sticky="e", padx=5, pady=5
            )
            
            entry = ttk.Entry(parent, width=40)
            entry.grid(row=row + i, column=1, sticky="ew", padx=5, pady=5)
            
            # パスワードフィールドは表示を隠す
            if field == "password":
                entry.config(show="*")
            
            # デフォルト値
            if field == "port":
                entry.insert(0, "1521")
            
            self.entries[f"{prefix}_{field}"] = entry
        
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
        self.object_tree.column("#0", width=50, minwidth=50, anchor="center")
        self.object_tree.column("name", width=250, minwidth=150, anchor="w")
        self.object_tree.column("type", width=120, minwidth=100, anchor="center")
        self.object_tree.column("created", width=150, minwidth=120, anchor="center")
        self.object_tree.column("updated", width=150, minwidth=120, anchor="center")
        
        # ヘッダーの設定
        self.object_tree.heading("#0", text="✓", anchor="center")
        self.object_tree.heading("name", text="オブジェクト名", anchor="w")
        self.object_tree.heading("type", text="種類", anchor="center")
        self.object_tree.heading("created", text="作成日", anchor="center")
        self.object_tree.heading("updated", text="更新日", anchor="center")
        
        # チェックボックスのクリックイベント
        self.object_tree.bind("<Button-1>", self._on_tree_click)
        
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
            self.db_manager = DatabaseManager(source_config, target_config)
            
            # 接続テスト
            if self.db_manager.test_connections():
                self._log("✓ 両方のデータベースに正常に接続できました", "success")
                messagebox.showinfo("成功", "接続テストに成功しました")
            else:
                self._log("✗ 接続テストに失敗しました", "error")
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
            if not self._show_diff_confirmation(selected_objects):
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

    def _show_diff_confirmation(self, selected_objects: List[DatabaseObject]) -> bool:
        """差分確認ウィンドウを表示。
        
        Args:
            selected_objects: コピー対象のオブジェクト
            
        Returns:
            ユーザーが続行を選択した場合True、キャンセルした場合False
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
            
            # タブ1: ソースのみ
            self._create_diff_tab(notebook, "ソースのみ", only_in_source, "このオブジェクトは新規作成されます")
            
            # タブ2: ターゲットのみ
            self._create_diff_tab(notebook, "ターゲットのみ", only_in_target, "このオブジェクトはターゲットに既に存在します")
            
            # タブ3: 両方に存在
            self._create_diff_tab(notebook, "両方に存在", in_both, "このオブジェクトは上書きされます")
            
            # ボタンフレーム
            button_frame = ttk.Frame(diff_window)
            button_frame.pack(pady=10)
            
            # ユーザーが選択した結果を保持
            user_choice = {'continue': False}
            
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
    
    def _create_diff_tab(self, notebook: ttk.Notebook, tab_name: str, objects: List[DatabaseObject], description: str) -> None:
        """差分タブを作成。
        
        Args:
            notebook: ノートブックウィジェット
            tab_name: タブ名
            objects: 表示するオブジェクト
            description: 説明テキスト
        """
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=f"{tab_name} ({len(objects)}件)")
        
        # 説明
        ttk.Label(
            frame,
            text=description,
            foreground="gray",
            font=("Arial", 9)
        ).pack(anchor="w", padx=10, pady=5)
        
        # ツリービュー
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        tree = ttk.Treeview(
            tree_frame,
            columns=("type", "created"),
            show="tree headings",
            height=15,
            yscrollcommand=scrollbar.set
        )
        tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)
        
        # 列設定
        tree.column("#0", width=300, minwidth=200, anchor="w")
        tree.column("type", width=120, minwidth=100, anchor="center")
        tree.column("created", width=150, minwidth=120, anchor="center")
        
        # ヘッダー設定
        tree.heading("#0", text="オブジェクト名", anchor="w")
        tree.heading("type", text="種類", anchor="center")
        tree.heading("created", text="作成日", anchor="center")
        
        # オブジェクトを表示
        for obj in objects:
            tree.insert(
                "",
                "end",
                text=obj.name,
                values=(obj.object_type.value, obj.created or "N/A")
            )


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
            return
        
        # TNSエントリを取得
        entry = self.tns_parser.get_entry(selected)
        
        if entry:
            # 接続情報を自動入力
            self.entries[f"{prefix}_host"].delete(0, tk.END)
            self.entries[f"{prefix}_host"].insert(0, entry.host)
            
            self.entries[f"{prefix}_port"].delete(0, tk.END)
            self.entries[f"{prefix}_port"].insert(0, str(entry.port))
            
            service = entry.service_name or entry.sid or ""
            self.entries[f"{prefix}_service"].delete(0, tk.END)
            self.entries[f"{prefix}_service"].insert(0, service)
            
            self._log(f"TNSエントリ '{selected}' の接続情報を読み込みました", "success")
    
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
                    
                    # UIを再構築（TNSエントリのドロップダウンを更新）
                    messagebox.showinfo(
                        "成功",
                        f"tnsnames.ora を読み込みました\n\n"
                        f"エントリ数: {len(self.tns_parser.get_entries())}\n\n"
                        f"アプリケーションを再起動してください"
                    )
                else:
                    messagebox.showerror("エラー", "有効な tnsnames.ora ファイルではありません")
            
            except Exception as e:
                error_msg = f"tnsnames.ora の読み込みエラー: {str(e)}"
                self._log(error_msg, "error")
                logging.error(error_msg, exc_info=True)
                messagebox.showerror("エラー", error_msg)

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
