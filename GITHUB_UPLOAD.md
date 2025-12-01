# GitHub アップロード手順

## 1. Gitリポジトリの初期化

プロジェクトディレクトリで以下のコマンドを実行:

```bash
# Gitリポジトリを初期化
git init

# ユーザー情報を設定（初回のみ）
git config user.name "Your Name"
git config user.email "your.email@example.com"

# すべてのファイルをステージング
git add .

# 初回コミット
git commit -m "Initial commit: CSV to Excel Converter"
```

## 2. GitHubリポジトリの作成

1. GitHubにログイン: https://github.com
2. 右上の「+」→「New repository」をクリック
3. リポジトリ情報を入力:
   - Repository name: `csv-to-excel-converter`（または任意の名前）
   - Description: `CSV to Excel変換ツール - ドラッグ&ドロップ対応GUIアプリ`
   - Public または Private を選択
   - ❌ Initialize with README のチェックは**外す**（既にREADMEがあるため）
4. 「Create repository」をクリック

## 3. ローカルとGitHubを接続

GitHubで表示される手順、または以下のコマンドを実行:

```bash
# リモートリポジトリを追加（URLは自分のリポジトリに置き換え）
git remote add origin https://github.com/yourusername/csv-to-excel-converter.git

# メインブランチ名をmainに変更（推奨）
git branch -M main

# GitHubにプッシュ
git push -u origin main
```

## 4. 認証設定

### Personal Access Token を使用する場合（推奨）

1. GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. 「Generate new token (classic)」をクリック
3. スコープで「repo」にチェック
4. トークンを生成してコピー
5. プッシュ時にパスワードの代わりにトークンを使用

### SSH鍵を使用する場合

```bash
# SSH鍵を生成
ssh-keygen -t ed25519 -C "your.email@example.com"

# 公開鍵をコピー
cat ~/.ssh/id_ed25519.pub

# GitHubのSettings → SSH and GPG keys → New SSH key に追加

# リモートURLをSSHに変更
git remote set-url origin git@github.com:yourusername/csv-to-excel-converter.git
```

## 5. 継続的な更新

変更をGitHubに反映する手順:

```bash
# 変更したファイルを確認
git status

# 変更をステージング
git add .

# コミット
git commit -m "機能追加: シート名の重複処理を改善"

# GitHubにプッシュ
git push
```

## 6. リリースの作成（オプション）

EXEファイルをリリースとして配布する場合:

1. GitHubリポジトリページで「Releases」をクリック
2. 「Create a new release」をクリック
3. タグを作成: `v1.0.0`
4. リリース名: `CSV to Excel Converter v1.0.0`
5. 説明を記入
6. `dist/CsvToExcel.exe` をアップロード
7. 「Publish release」をクリック

## 7. README.mdのカスタマイズ

`README_CsvToExcel.md` を `README.md` にリネームまたは内容をコピーして、以下を更新:

- GitHubユーザー名
- リポジトリURL
- スクリーンショット（あれば追加）
- 作成者情報

## コミットメッセージの例

```bash
# 機能追加
git commit -m "feat: 並列処理による高速化を実装"

# バグ修正
git commit -m "fix: 空CSVファイルでエラーが発生する問題を修正"

# ドキュメント更新
git commit -m "docs: README.mdに使用方法を追加"

# リファクタリング
git commit -m "refactor: シート名正規化処理を関数化"
```

## トラブルシューティング

### 認証エラーが発生する場合

```bash
# 認証情報をクリア
git credential-manager-core erase https://github.com

# 再度プッシュを試す
git push
```

### 大きなファイルの警告

```bash
# 100MBを超えるファイルは.gitignoreに追加
# 既にコミット済みの場合は履歴から削除
git filter-branch --tree-filter 'rm -f large_file.csv' HEAD
```

### コミット前の確認

```bash
# 何が変更されたか確認
git diff

# ステージングされた内容を確認
git diff --staged
```
