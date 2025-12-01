# Git インストール手順（Windows）

## Git がインストールされていない場合

PowerShellで `git` コマンドが認識されない場合は、Gitをインストールする必要があります。

## インストール方法

### 方法1: 公式サイトからダウンロード（推奨）

1. **Gitの公式サイトにアクセス**
   - https://git-scm.com/download/win

2. **インストーラーをダウンロード**
   - 「64-bit Git for Windows Setup」をクリック
   - 自動的にダウンロードが開始されます

3. **インストーラーを実行**
   - ダウンロードした `Git-x.xx.x-64-bit.exe` を実行
   
4. **インストール設定**（推奨設定）
   - **Select Components**: すべてデフォルトでOK
   - **Choosing the default editor**: お好みのエディタを選択（VS Code推奨）
   - **Adjusting your PATH environment**: 
     ✅ **「Git from the command line and also from 3rd-party software」を選択**（重要）
   - **Choosing HTTPS transport backend**: デフォルト（OpenSSL）でOK
   - **Configuring the line ending conversions**: 
     ✅ **「Checkout Windows-style, commit Unix-style line endings」を選択**
   - **Configuring the terminal emulator**: デフォルトでOK
   - その他の設定もすべてデフォルトでOK

5. **インストール完了**
   - 「Finish」をクリック

6. **PowerShellを再起動**
   - **重要**: PowerShellを一度閉じて、再度開く
   - これでPATHが反映されます

7. **動作確認**
   ```powershell
   git --version
   ```
   バージョン情報が表示されればOK

### 方法2: winget を使用（Windows 10/11）

PowerShellで以下を実行:

```powershell
winget install --id Git.Git -e --source winget
```

インストール後、PowerShellを再起動してください。

### 方法3: Chocolatey を使用（既にインストールしている場合）

```powershell
choco install git
```

## インストール後の初期設定

PowerShellを**再起動**してから、以下のコマンドを実行:

```powershell
# ユーザー名を設定
git config --global user.name "あなたの名前"

# メールアドレスを設定
git config --global user.email "your.email@example.com"

# デフォルトブランチ名をmainに設定（推奨）
git config --global init.defaultBranch main

# 設定を確認
git config --list
```

## GitHub との連携設定

### Personal Access Token の作成

1. GitHubにログイン: https://github.com
2. 右上のアイコン → Settings
3. 左メニュー最下部 → Developer settings
4. Personal access tokens → Tokens (classic)
5. Generate new token (classic)
6. Note: `CSV to Excel Converter`
7. Expiration: `90 days` （または任意）
8. Scopes: ✅ **repo** にチェック
9. Generate token
10. **トークンをコピーして安全な場所に保存**（再表示不可）

### 認証情報の保存（オプション）

```powershell
# 認証情報を保存（次回から入力不要）
git config --global credential.helper manager-core
```

## リポジトリの初期化（Gitインストール後）

PowerShellを再起動してから実行:

```powershell
# プロジェクトディレクトリに移動
cd C:\Users\hiyok\oracleConnect

# Gitリポジトリを初期化
git init

# ユーザー情報を設定（グローバル設定していない場合）
git config user.name "あなたの名前"
git config user.email "your.email@example.com"

# すべてのファイルをステージング
git add .

# 初回コミット
git commit -m "Initial commit: CSV to Excel Converter"

# GitHubリモートリポジトリを追加（事前にGitHubでリポジトリ作成済みの場合）
git remote add origin https://github.com/yourusername/csv-to-excel-converter.git

# メインブランチとして設定
git branch -M main

# GitHubにプッシュ
git push -u origin main
```

## トラブルシューティング

### PowerShell再起動後もgitが認識されない

1. **環境変数PATHを確認**
   ```powershell
   $env:Path -split ';' | Select-String git
   ```

2. **Gitの実行ファイルパスを確認**
   - 通常: `C:\Program Files\Git\cmd`
   - このパスが表示されない場合、手動でPATHに追加

3. **手動でPATHに追加**
   - 「システムのプロパティ」→「環境変数」
   - 「システム環境変数」の「Path」を編集
   - `C:\Program Files\Git\cmd` を追加
   - PowerShellを再起動

### SSL証明書エラーが発生する場合

```powershell
git config --global http.sslVerify false
```

※セキュリティリスクがあるため、問題が解決したら元に戻すことを推奨

## 参考リンク

- Git公式サイト: https://git-scm.com/
- Git日本語ドキュメント: https://git-scm.com/book/ja/v2
- GitHub Docs: https://docs.github.com/ja

## 次のステップ

Gitのインストールと設定が完了したら、`GITHUB_UPLOAD.md` の手順に従ってGitHubにアップロードしてください。
