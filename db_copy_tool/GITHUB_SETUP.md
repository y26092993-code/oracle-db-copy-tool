# db_copy_tool を GitHub リポジトリに登録する手順

## 方法1: 新しいリポジトリを作成する（推奨）

### ステップ1: GitHubで新しいリポジトリを作成

1. GitHub（https://github.com）にログイン
2. 右上の「+」→「New repository」をクリック
3. リポジトリ名を入力（例: `oracle-db-copy-tool`）
4. 説明を入力（例: `Oracle DB Object Copy Tool with GUI`）
5. Public または Private を選択
6. **「Initialize this repository with a README」はチェックしない**
7. 「Create repository」をクリック

### ステップ2: ローカルでGitリポジトリを初期化

```powershell
# db_copy_tool フォルダに移動
cd C:\Users\hiyok\oracleConnect\db_copy_tool

# Gitリポジトリを初期化
git init

# .gitignore ファイルを作成（不要なファイルを除外）
@"
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
*.egg
*.egg-info/
dist/
build/
*.spec.bak

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log

# Database
*.db
*.sqlite

# Config (機密情報がある場合)
config.yaml
"@ | Out-File -FilePath .gitignore -Encoding utf8
```

### ステップ3: ファイルをコミット

```powershell
# すべてのファイルをステージング
git add .

# 初回コミット
git commit -m "Initial commit: Oracle DB Object Copy Tool"
```

### ステップ4: GitHubリポジトリと連携

GitHubで作成したリポジトリのURLを使用（例: `https://github.com/yourusername/oracle-db-copy-tool.git`）

```powershell
# リモートリポジトリを追加（URLは自分のものに置き換え）
git remote add origin https://github.com/yourusername/oracle-db-copy-tool.git

# mainブランチにリネーム（必要に応じて）
git branch -M main

# GitHubにプッシュ
git push -u origin main
```

### ステップ5: プッシュ時の認証

プッシュ時に認証が求められます：

**オプションA: Personal Access Token（推奨）**
1. GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. 「Generate new token」→「Generate new token (classic)」
3. Note: `db_copy_tool` など
4. Expiration: 適切な期限を選択
5. Select scopes: `repo` にチェック
6. 「Generate token」をクリック
7. トークンをコピー（表示は1回のみ）
8. プッシュ時にパスワードの代わりにトークンを使用

**オプションB: GitHub CLI**
```powershell
# GitHub CLIをインストール済みの場合
gh auth login
```

---

## 方法2: 既存のリポジトリのサブディレクトリとして追加

現在の oracleConnect リポジトリに db_copy_tool を含める場合：

```powershell
# ルートディレクトリに移動
cd C:\Users\hiyok\oracleConnect

# db_copy_tool フォルダを追加
git add db_copy_tool/

# コミット
git commit -m "Add Oracle DB Object Copy Tool"

# プッシュ
git push
```

---

## 方法3: Git Submodule として管理（高度）

db_copy_tool を独立したリポジトリにしつつ、oracleConnect からも参照する場合：

### 3-1. まず方法1で別リポジトリを作成

### 3-2. oracleConnect リポジトリから参照

```powershell
cd C:\Users\hiyok\oracleConnect

# 現在の db_copy_tool フォルダを削除（バックアップ推奨）
# Move-Item db_copy_tool db_copy_tool_backup

# サブモジュールとして追加
git submodule add https://github.com/yourusername/oracle-db-copy-tool.git db_copy_tool

# コミット
git commit -m "Add db_copy_tool as submodule"

# プッシュ
git push
```

---

## おすすめの設定

### README.md の充実

db_copy_tool/README.md は既に詳細ですが、以下を追加すると良いでしょう：

- バッジ（License, Python Version など）
- スクリーンショット
- インストールコマンド
- コントリビューションガイドライン

### LICENSE ファイルの追加

```powershell
cd C:\Users\hiyok\oracleConnect\db_copy_tool

# MIT License の例
@"
MIT License

Copyright (c) 2026 [Your Name]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"@ | Out-File -FilePath LICENSE -Encoding utf8
```

### GitHub Actions の追加（オプション）

自動テストやビルドを設定する場合は `.github/workflows` を作成

---

## トラブルシューティング

### エラー: "fatal: not a git repository"
```powershell
# Gitリポジトリが初期化されていない
git init
```

### エラー: "remote origin already exists"
```powershell
# 既存のリモートを削除
git remote remove origin

# 新しいリモートを追加
git remote add origin https://github.com/yourusername/repo.git
```

### エラー: "failed to push some refs"
```powershell
# リモートの変更を取得してマージ
git pull origin main --allow-unrelated-histories

# 再度プッシュ
git push -u origin main
```

### 大きなファイルの警告
```powershell
# 100MB以上のファイルがある場合はGit LFSを使用
git lfs install
git lfs track "*.exe"
git add .gitattributes
```

---

## どの方法を選ぶべきか？

| 方法 | メリット | デメリット | 推奨ケース |
|------|---------|-----------|-----------|
| **方法1: 新規リポジトリ** | 独立して管理できる<br>専用のIssue/PRが使える | oracleConnectとは別管理 | db_copy_toolを独立した<br>プロジェクトとして公開 |
| **方法2: サブディレクトリ** | 管理が簡単<br>1つのリポジトリで完結 | 独立性が低い | oracleConnectの一部として<br>管理したい |
| **方法3: Submodule** | 独立性と関連性の両立 | 管理が複雑 | 複数プロジェクトで<br>共有したい |

## 推奨: 方法1（新規リポジトリ）

db_copy_tool は単独で動作する完成度の高いツールなので、**独立したリポジトリとして公開する**のが最適です。

以下のコマンドで実行できます：

```powershell
# 1. db_copy_toolに移動
cd C:\Users\hiyok\oracleConnect\db_copy_tool

# 2. Gitリポジトリを初期化
git init

# 3. .gitignoreを作成（上記参照）

# 4. すべてのファイルを追加
git add .

# 5. 初回コミット
git commit -m "Initial commit: Oracle DB Object Copy Tool with GUI, tnsnames.ora support, and wildcard filtering"

# 6. GitHubでリポジトリを作成後、リモートを追加
git remote add origin https://github.com/yourusername/oracle-db-copy-tool.git

# 7. プッシュ
git branch -M main
git push -u origin main
```

実行の前にGitHubでリポジトリを作成してください！
