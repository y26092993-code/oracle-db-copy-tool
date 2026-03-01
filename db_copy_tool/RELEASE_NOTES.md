# Oracle DB Copy Tool - Release Notes

## v1.0.0 - 2026年3月1日

### 概要
Oracle Database間でテーブル・ビュー・ストアドプロシージャなどのオブジェクトをコピーするスタンドアロンGUIツール

### 主な機能
- ✅ **tnsnames.ora統合**
  - tnsnames.oraファイルの自動検出・読み込み
  - 接続情報のドロップダウン選択で簡単設定
  - 複数接続情報の管理

- ✅ **TNS対応UI**
  - 方法1: TNSエントリから選択（自動入力）
  - 方法2: 手動で接続情報を入力
  - 認証情報は常に必須入力
  - UI改善で視認性向上

- ✅ **オブジェクトコピー機能**
  - テーブル定義のコピー
  - ビュー定義のコピー
  - ストアドプロシージャのコピー
  - インデックス定義のコピー
  - データのコピーオプション選択可

- ✅ **接続テスト機能**
  - ソース・ターゲットDB双方の接続確認
  - エラー詳細表示

- ✅ **実行・ログ機能**
  - リアルタイムログ表示
  - エラーサマリー表示
  - 実行結果の詳細確認

### 必要環境
- **OS**: Windows 10以上
- **Python**: 3.10以上（ソースから実行する場合）
- **Oracle Client**: Basic/Standard/Enterprise Edition対応
- **接続方式**: TNS/直接接続（ホスト:ポート:サービス名）

### インストール
#### 実行ファイルの使用（Windows）
```bash
# db_copy_tool/dist/DBCopyTool.exe を実行
DBCopyTool.exe
```

#### ソースコードから実行
```bash
# リポジトリをクローン
git clone https://github.com/y26092993-code/oracle-db-copy-tool.git
cd oracle-db-copy-tool/db_copy_tool

# 仮想環境を作成
python -m venv venv
.\venv\Scripts\Activate.ps1

# 依存パッケージをインストール
pip install -r requirements.txt

# GUIを起動
python db_copy_gui.py
```

### 使用方法

#### 1. 接続設定タブ
- **TNS エントリ選択** → tnsnames.oraから接続先を選択
- または**手動入力** → ホスト、ポート、サービス名を入力
- **ユーザー名** と **パスワード** を入力
- **接続テスト** ボタンで接続確認

#### 2. オブジェクト選択タブ
- コピーしたいオブジェクトタイプをチェック
- 対象オブジェクトをリストから選択

#### 3. 実行とログタブ
- **実行開始** ボタンでコピー処理を開始
- ログで進捗状況を確認
- エラーが発生した場合はエラーサマリーで確認

### 改善内容（v1.0.0）

#### UI/UX改善
- ウィンドウサイズを1200x900に拡大
- 接続設定を3セクションに分割表示
- 必須項目を明確に表示（赤字表記）
- TNS選択時に接続情報がreadonly になって編集不可に

#### tnsnames.ora解析
- 括弧のネスト構造に対応した正確なパース
- ADDRESS、CONNECT_DATA ブロックの完全抽出
- SERVICE_NAME/SID 両方に対応

#### 接続機能
- 複数の接続文字列形式に対応
  - 簡潔形式: `host:port/service`
  - JDBC URL形式
  - SQLPlus形式

### 既知の制限事項
- ローカルファイルシステムのみサポート（NETCOREなど外部記憶域非対応）
- 大量のオブジェクトコピー時は処理時間が長くなる可能性あり
- PASSWORD_VERIFY_FUNCTION付きのアカウントは接続に失敗する場合あり

### サポート・フィードバック
- **GitHub Issues**: https://github.com/y26092993-code/oracle-db-copy-tool/issues
- **バグ報告**: 詳細なエラーログと再現手順をお願いします

### ライセンス
本ツールはMITライセンスの下で公開されています。

### 変更履歴

**v1.0.0**
- 初回リリース
- 基本的なDB オブジェクトコピー機能を実装
- TNS統合機能を実装
- UI/UX改善を完了
