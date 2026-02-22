# Oracle Connect Project

## oracle.py - SQLファイル一括実行アプリケーション

指定フォルダ内の SQLファイル（`*.sql`）をアルファベット順に OracleDB へ一括実行するツールです。

### ファイル構成

```
python/
├── oracle.py          # メインアプリケーション（SQLファイル一括実行）
├── config.yaml        # 接続設定ファイルのサンプル
├── requirements.txt   # 必要なPythonパッケージ
└── sql/               # 実行するSQLファイルを格納するディレクトリ（例）
    ├── 01_create.sql
    └── 02_insert.sql
```

### セットアップ

```powershell
# 依存パッケージのインストール
pip install -r requirements.txt
```

### 設定ファイル（config.yaml）の編集

```yaml
database:
  host: localhost         # ホスト名
  port: 1521              # ポート番号
  service_name: ORCL      # サービス名（または sid: ORCL）
  user: your_username     # ユーザー名
  password: your_password # パスワード
```

### コマンドライン引数

| 引数 | 説明 | デフォルト |
|------|------|----------|
| `--config` | YAML設定ファイルのパス（必須） | - |
| `--sql-dir` | SQLファイルが格納されているディレクトリ（必須） | - |
| `--error-mode` | エラー時の動作: `stop`（確認後継続/中断）または `continue`（スキップ） | `stop` |
| `--autocommit` | 自動コミット: `true` または `false` | `true` |
| `--log-dir` | ログファイル出力先ディレクトリ | `./logs` |

### 使用例

```bash
# 基本的な使用方法（エラー時中断、自動コミット有効）
python oracle.py --config config.yaml --sql-dir ./sql

# エラーを無視して続行、自動コミット無効
python oracle.py --config config.yaml --sql-dir ./sql --error-mode continue --autocommit false

# ログ出力先を指定
python oracle.py --config config.yaml --sql-dir ./sql --log-dir ./my_logs
```

### ログ出力

- ログは標準出力とファイルの両方に出力されます。
- ログファイル名: `logs/oracle_execution_YYYYMMDD_HHMMSS.log`
- 各SQLファイルの実行結果（成功/失敗）、エラーメッセージ、実行開始・終了時刻を記録します。

### エラーハンドリング

- **中断モード（`--error-mode stop`）**: エラー発生時にユーザーへ継続/終了を確認します。
- **無視モード（`--error-mode continue`）**: エラーをログに記録して次のファイルへ進みます。
- エラー発生時は自動的にロールバックを実行します。

---

APPSプロジェクトを参考に作成したPython版Oracle接続アプリケーションです。

## プロジェクト構成

```
oracleConnect/
├── config/                  # 設定ファイル
│   ├── config.yaml         # メイン設定
│   └── config-dev.yaml     # 開発環境用設定
├── src/
│   ├── database/
│   │   └── oracle_client.py    # Oracle接続クライアント
│   └── config/
│       └── database_config.py  # 設定管理
├── examples/
│   └── sample_app.py       # サンプルアプリケーション
└── requirements.txt        # 依存パッケージ
```

## 主な機能

- **接続プーリング**: 効率的なデータベース接続管理
- **CRUD操作**: SELECT, INSERT, UPDATE, DELETE操作のサポート
- **バッチ処理**: 複数レコードの一括処理
- **設定管理**: YAMLファイルまたは環境変数での設定
- **エラーハンドリング**: トランザクション管理とロールバック
- **複数データベース対応**: 複数のOracle DBを同時に管理
- **スキーマ切り替え**: 動的にスキーマを切り替えて実行
- **接続マネージャー**: データベース接続の一元管理

## セットアップ

### 1. 仮想環境の作成と有効化

```powershell
# 仮想環境作成
python -m venv .venv

# 仮想環境有効化
.venv\Scripts\Activate.ps1
```

### 2. 依存パッケージのインストール

```powershell
pip install -r requirements.txt
```

### 3. データベース設定

`config/config.yaml` を編集して、Oracle接続情報を設定します:

#### 複数データベース設定

```yaml
databases:
  # デフォルトのデータベース
  default:
    user: jx
    password: jx
    host: localhost
    port: 1521
    service_name: jx
    schema: jx  # 省略可能
    min_pool_size: 1
    max_pool_size: 10
    increment: 1

  # 開発用データベース
  dev:
    user: jx_dev
    password: jx_dev
    host: localhost
    port: 1521
    service_name: jx
    schema: jx_dev
    min_pool_size: 1
    max_pool_size: 5
    increment: 1
```

#### 環境変数での設定

```powershell
# デフォルトDB
$env:ORACLE_USER = "jx"
$env:ORACLE_PASSWORD = "jx"
$env:ORACLE_HOST = "localhost"
$env:ORACLE_PORT = "1521"
$env:ORACLE_SERVICE_NAME = "jx"
$env:ORACLE_SCHEMA = "jx"

# 開発用DB（プレフィックスを変更）
$env:ORACLE_DEV_USER = "jx_dev"
$env:ORACLE_DEV_PASSWORD = "jx_dev"
```

## 使用方法

### サンプルアプリケーションの実行

#### 基本的なCRUD操作
```powershell
python examples/sample_app.py
```

#### 複数データベース/スキーマ切り替え
```powershell
python examples/multi_database_app.py
```

### プログラムでの使用例

#### 1. 単一データベース接続

```python
from src.database.oracle_client import OracleClient
from src.config.database_config import DatabaseConfig

# 設定の読み込み
config = DatabaseConfig.from_yaml("config/config.yaml", "default")

# クライアントの作成
with OracleClient(
    user=config.user,
    password=config.password,
    host=config.host,
    port=config.port,
    service_name=config.service_name,
    schema=config.schema,
) as client:
    # SELECT クエリ
    results = client.execute_query("SELECT * FROM your_table")
    
    # スキーマを指定してクエリ実行
    results = client.execute_query(
        "SELECT * FROM your_table",
        schema="other_schema"
    )
```

#### 2. 複数データベース管理

```python
from src.database.connection_manager import ConnectionManager

# 複数データベースの管理
with ConnectionManager() as manager:
    # 設定ファイルから全DB読み込み
    manager.load_from_yaml("config/config.yaml")
    
    # デフォルトDBで実行
    client = manager.get_client()
    results = client.execute_query("SELECT * FROM table1")
    
    # データベースを切り替え
    manager.switch_database("dev")
    client = manager.get_client()
    results = client.execute_query("SELECT * FROM table2")
    
    # 特定のDBを直接指定
    client = manager.get_client("test")
    results = client.execute_query("SELECT * FROM table3")
```

#### 3. スキーマの動的切り替え

```python
from src.database.oracle_client import OracleClient

with OracleClient(user="jx", password="jx", service_name="jx") as client:
    # デフォルトスキーマで実行
    client.execute_query("SELECT * FROM table1")
    
    # スキーマを変更
    client.set_schema("other_schema")
    client.execute_query("SELECT * FROM table2")
    
    # クエリごとにスキーマ指定
    client.execute_query("SELECT * FROM table3", schema="temp_schema")
```

## APPSプロジェクトとの対応

このプロジェクトは、以下のAPPSプロジェクトの設計を参考にしています:

### データベース接続設定
- APPS: `back/jx_online/src/main/resources/application.yaml`
- Python: `config/config.yaml`

### 接続クライアント
- APPS: Doma2 + Oracle UCP (Universal Connection Pool)
- Python: python-oracledb + 接続プーリング

### 設定管理
- APPS: Spring Boot の環境変数 + application.yaml
- Python: 環境変数 + config.yaml

## ベストプラクティス

### PEP8準拠
- 全コードはPEP8スタイルガイドに準拠
- Black フォーマッターで自動整形可能

### 型ヒント
- すべての関数とメソッドに型ヒントを使用
- mypy による静的型チェック対応

### エラーハンドリング
- 適切な例外処理とロールバック機能
- ログ出力による追跡可能性

### セキュリティ
- パスワードはログに出力しない
- 環境変数での機密情報管理をサポート

## トラブルシューティング

### 接続エラーが発生する場合

1. Oracleデータベースが起動しているか確認
2. 接続情報（ホスト、ポート、サービス名）が正しいか確認
3. ユーザー名とパスワードが正しいか確認
4. ファイアウォール設定を確認

### パッケージのインポートエラー

```powershell
# 仮想環境を再作成
Remove-Item -Recurse -Force .venv
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 開発ツール

### コードフォーマット

```powershell
black src/ examples/
```

### リンター

```powershell
flake8 src/ examples/
pylint src/ examples/
```

### 型チェック

```powershell
mypy src/ examples/
```

### テスト実行

```powershell
pytest tests/ -v --cov=src
```

## 実行ファイル（EXE）の作成

### クイックビルド

```powershell
# ビルドスクリプトを実行
.\build.bat
```

### 配布パッケージの作成

```powershell
# 配布用ZIPファイルを作成
.\create_package.bat
```

### 手動ビルド

```powershell
# PyInstallerでビルド
pyinstaller ImageEntryGUI3.spec --clean
```

詳細は[BUILD_INSTRUCTIONS.md](BUILD_INSTRUCTIONS.md)を参照してください。

### 成果物

- `dist\ImageEntryGUI3.exe` - ワンファイル版実行ファイル（約50MB）
- `dist\ImageEntryGUI3\` - ワンフォルダ版（高速起動）

## ライセンス

Copyright (c) 2025 Oracle Connect Project.

## 参考資料

- [python-oracledb ドキュメント](https://python-oracledb.readthedocs.io/)
- [Oracle Database SQL言語リファレンス](https://docs.oracle.com/en/database/)
- [PEP 8 -- Style Guide for Python Code](https://www.python.org/dev/peps/pep-0008/)
