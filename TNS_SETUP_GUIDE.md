# tnsnames.ora 設定ガイド

## 概要

Oracle DB オブジェクトコピーツール GUI では、`tnsnames.ora` ファイルから読み込んだデータベース接続情報を使用して、コピー元とコピー先を簡単に設定できます。

## 機能

### 1. tnsnames.ora の自動検出
- アプリケーション起動時に、以下の場所から `tnsnames.ora` を自動検出します：
  - `TNS_ADMIN` 環境変数で指定されたディレクトリ
  - `ORACLE_HOME/network/admin/` ディレクトリ
  - Windows: `C:\Oracle\instantclient\network\admin\` など

### 2. エントリ一覧の表示
- 接続設定タブを開くと、読み込まれたエントリが自動的に表示されます
- 各エントリの次の情報が表示されます：
  - ホスト名
  - ポート番号
  - Service Name または SID
  - 接続文字列（複数の形式）
  - JDBC URL
  - SQLPlus 接続形式

### 3. ドロップダウン選択機能
- ソースデータベースとターゲットデータベースの設定フレームに、TNS エントリ選択用のドロップダウン（Combobox）があります
- 「（手動入力）」を選択して手動で入力することもできます

### 4. 自動入力
- ドロップダウンからエントリを選択すると、以下が自動的に入力されます：
  - ホスト名
  - ポート番号（デフォルト: 1521）
  - サービス名/SID

## 使用手順

### ステップ 1: アプリケーション起動
```bash
python db_copy_gui.py
```

### ステップ 2: 接続設定タブを確認
- アプリケーションが起動すると、「接続設定」タブが表示されます
- `tnsnames.ora` が正常に読み込まれていれば、上部に以下が表示されます：
  - ファイルパス（緑色）
  - 読み込まれたエントリ数
  - エントリ一覧（スクロール可能）

### ステップ 3: ソースデータベースを設定
1. 「ソースデータベース（コピー元）」フレームの「TNS エントリ」ドロップダウンをクリック
2. 一覧から エントリ名を選択（例：`DEV`）
3. 自動的に以下が入力されます：
   - ホスト: `dev-server.example.com`
   - ポート: `1521`
   - サービス名/SID: `devdb`
4. ユーザー名とパスワードを入力

### ステップ 4: ターゲットデータベースを設定
1. 「ターゲットデータベース（コピー先）」フレームの「TNS エントリ」ドロップダウンをクリック
2. 別のエントリ名を選択（例：`PROD`）
3. 自動的に接続情報が入力されます
4. ユーザー名とパスワードを入力

### ステップ 5: 接続テスト（オプション）
- 「接続テスト」ボタンをクリックして、入力した接続情報が正しいか確認

## tnsnames.ora ファイルの配置

### Windows での一般的な場所
```
C:\oracle\network\admin\tnsnames.ora
C:\app\oracle\product\network\admin\tnsnames.ora
C:\Oracle\instantclient\network\admin\tnsnames.ora
```

### Linux での一般的な場所
```
/usr/lib/oracle/network/admin/tnsnames.ora
/etc/oracle/tnsnames.ora
~/oracle/network/admin/tnsnames.ora
```

### カスタム位置を指定
- 「tnsnames.ora を選択」ボタンをクリックして、ファイルを手動で選択できます

## tnsnames.ora ファイル形式

### 例：SERVICE_NAME を使用する場合
```
DEV =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = dev-server.example.com)(PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = devdb)
    )
  )
```

### 例：SID を使用する場合
```
LEGACY =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = legacy-server.example.com)(PORT = 1521))
    (CONNECT_DATA =
      (SID = oradb)
    )
  )
```

## トラブルシューティング

### tnsnames.ora が見つからない場合
- 「tnsnames.ora を選択」ボタンをクリックして、ファイルを手動で選択してください
- ファイル選択後、読み込み結果がダイアログに表示されます

### エントリが正しく読み込まれない場合
- ファイルのエンコーディングを確認してください（UTF-8 または CP932 に対応）
- ファイルの形式が上記の サンプルと一致していることを確認してください
- 「読み込み結果を表示」ボタンをクリックして、詳細情報を確認してください

## GUI インターフェース概要

```
┌─────────────────────────────────────────────────────────┐
│ Oracle DB オブジェクトコピーツール                          │
├─────────────────────────────────────────────────────────┤
│ [接続設定]  [オブジェクト選択]  [実行とログ]                    │
├─────────────────────────────────────────────────────────┤
│                                                           │
│ tnsnames.ora: C:\...  [tnsnames.ora を選択] [読み込み結果を表示] │
│                                                           │
│ ┌─ tnsnames.ora エントリ一覧 ──────────────────────────┐ │
│ │ DEV (dev-server.example.com:1521/devdb)              │ │
│ │ TEST (test-server.example.com:1521/testdb)           │ │
│ │ PROD (prod-server.example.com:1521/proddb)           │ │
│ │ LOCALHOST (localhost:1521/ORCL)                      │ │
│ │ LEGACY (legacy-server.example.com:1521:oradb)        │ │
│ └───────────────────────────────────────────────────────┘ │
│                                                           │
│ ┌─ ソースデータベース（コピー元） ──────────────────────────┐ │
│ │ TNS エントリ:      [▼ （手動入力）       ]              │ │
│ │ ホスト:           [                    ]              │ │
│ │ ポート:           [1521                 ]              │ │
│ │ サービス名/SID:    [                    ]              │ │
│ │ ユーザー名:       [                    ]              │ │
│ │ パスワード:       [                    ]              │ │
│ └───────────────────────────────────────────────────────┘ │
│                                                           │
│ ┌─ ターゲットデータベース（コピー先） ────────────────────────┐ │
│ │ TNS エントリ:      [▼ （手動入力）       ]              │ │
│ │ ホスト:           [                    ]              │ │
│ │ ポート:           [1521                 ]              │ │
│ │ サービス名/SID:    [                    ]              │ │
│ │ ユーザー名:       [                    ]              │ │
│ │ パスワード:       [                    ]              │ │
│ └───────────────────────────────────────────────────────┘ │
│                                                           │
│                        [接続テスト]                         │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

## API（プログラム内での使用）

### TNS エントリへのアクセス

```python
from tnsnames_parser import TnsNamesParser

# パーサーを初期化
parser = TnsNamesParser()

# 全エントリを取得
entries = parser.get_entries()  # Dict[str, TnsEntry]

# 特定のエントリを取得
dev_entry = parser.get_entry('DEV')

# 接続文字列を組み立て
if dev_entry:
    connection_string = dev_entry.get_connection_string()
    # => "dev-server.example.com:1521/devdb"
    
    jdbc_url = dev_entry.get_jdbc_url()
    # => "jdbc:oracle:thin:@dev-server.example.com:1521/devdb"
    
    sqlplus_conn = dev_entry.get_sqlplus_string('scott')
    # => "scott@dev-server.example.com:1521/devdb"
```

## 設定の保存

- 手動で入力した設定は、アプリケーション内に保存されます
- `config.yaml` ファイルで設定を永続化できます（オプション）

---

**最終更新：2026年3月1日**
