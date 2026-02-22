"""
OracleDB SQLファイル一括実行アプリケーション

指定フォルダ内のSQLファイル（*.sql）をアルファベット順に読み込み、
OracleDBへ一括実行します。
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import oracledb
import yaml


# ---------------------------------------------------------------------------
# ロギング設定
# ---------------------------------------------------------------------------

def setup_logging(log_dir: str) -> logging.Logger:
    """標準出力とファイルの両方にログを出力するロガーを設定する。"""
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir_path / f"oracle_execution_{timestamp}.log"

    logger = logging.getLogger("oracle_executor")
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ファイルハンドラー
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # コンソールハンドラー
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info("ログファイル: %s", log_file)
    return logger


# ---------------------------------------------------------------------------
# 設定読み込み
# ---------------------------------------------------------------------------

def load_config(config_path: str) -> dict:
    """YAMLファイルから接続設定を読み込む。"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# SQLファイル収集
# ---------------------------------------------------------------------------

def collect_sql_files(sql_dir: str) -> List[Path]:
    """指定ディレクトリからSQLファイルをアルファベット順に収集する。"""
    dir_path = Path(sql_dir)
    if not dir_path.exists():
        raise NotADirectoryError(f"SQLディレクトリが見つかりません: {sql_dir}")
    files = sorted(dir_path.glob("*.sql"))
    return files


# ---------------------------------------------------------------------------
# Oracle接続
# ---------------------------------------------------------------------------

_PLACEHOLDER_VALUES = {"your_username", "your_password", "your_user", "your_pass"}


def create_connection(config: dict) -> oracledb.Connection:
    """設定情報からOracleDB接続を作成する。"""
    db = config.get("database", {})
    host = db.get("host", "localhost")
    port = int(db.get("port", 1521))
    service_name: Optional[str] = db.get("service_name")
    sid: Optional[str] = db.get("sid")
    user: str = db["user"]
    password: str = db["password"]

    if user in _PLACEHOLDER_VALUES or password in _PLACEHOLDER_VALUES:
        raise ValueError(
            "設定ファイルのユーザー名またはパスワードがサンプル値のままです。"
            " config.yaml を実際の接続情報に更新してください。"
        )

    if service_name:
        dsn = oracledb.makedsn(host, port, service_name=service_name)
    elif sid:
        dsn = oracledb.makedsn(host, port, sid=sid)
    else:
        raise ValueError("設定ファイルに service_name または sid を指定してください。")

    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    return conn


# ---------------------------------------------------------------------------
# SQL実行
# ---------------------------------------------------------------------------

def execute_sql_file(
    cursor: oracledb.Cursor,
    sql_file: Path,
    logger: logging.Logger,
) -> bool:
    """単一SQLファイルを実行する。成功時True、失敗時Falseを返す。"""
    sql_text = sql_file.read_text(encoding="utf-8").strip()
    if not sql_text:
        logger.warning("[SKIP] 空ファイルをスキップ: %s", sql_file.name)
        return True

    # セミコロン区切りで複数ステートメントに分割（末尾の空文字を除外）
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]

    for stmt in statements:
        logger.debug("実行SQL:\n%s", stmt)
        cursor.execute(stmt)

    logger.info("[OK] %s", sql_file.name)
    return True


def run(
    connection: oracledb.Connection,
    sql_files: List[Path],
    error_mode: str,
    autocommit: bool,
    logger: logging.Logger,
    input_func=input,
) -> bool:
    """SQLファイルを順番に実行する。全ファイル成功時True、いずれか失敗時Falseを返す。"""
    success_count = 0
    failure_count = 0

    for sql_file in sql_files:
        logger.info("--- 実行開始: %s ---", sql_file.name)
        cursor = connection.cursor()
        try:
            execute_sql_file(cursor, sql_file, logger)
            if autocommit:
                connection.commit()
                logger.debug("コミット完了: %s", sql_file.name)
            success_count += 1
        except oracledb.DatabaseError as exc:
            failure_count += 1
            logger.error("[ERROR] %s: %s", sql_file.name, exc)

            try:
                connection.rollback()
                logger.info("ロールバック完了: %s", sql_file.name)
            except oracledb.DatabaseError as rb_exc:
                logger.error("ロールバック失敗: %s", rb_exc)

            if error_mode == "stop":
                answer = input_func(
                    "\nエラーが発生しました。処理を継続しますか？ [y/N]: "
                ).strip().lower()
                if answer != "y":
                    logger.info("ユーザーにより処理が中断されました。")
                    break
                logger.info("ユーザーにより処理を継続します。")
            else:
                logger.info("error-mode=continue のためスキップして次のファイルへ進みます。")
        finally:
            cursor.close()

    logger.info(
        "実行結果サマリー: 成功=%d, 失敗=%d, 合計=%d",
        success_count,
        failure_count,
        len(sql_files),
    )
    return failure_count == 0


# ---------------------------------------------------------------------------
# メインエントリーポイント
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """コマンドライン引数を解析する。"""
    parser = argparse.ArgumentParser(
        description="OracleDB SQLファイル一括実行アプリケーション",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 基本的な使用方法（エラー時中断、自動コミット有効）
  python oracle.py --config config.yaml --sql-dir ./sql

  # エラーを無視して続行、自動コミット無効
  python oracle.py --config config.yaml --sql-dir ./sql --error-mode continue --autocommit false

  # ログ出力先を指定
  python oracle.py --config config.yaml --sql-dir ./sql --log-dir ./my_logs
        """,
    )
    parser.add_argument(
        "--config",
        required=True,
        help="YAML設定ファイルのパス（必須）",
    )
    parser.add_argument(
        "--sql-dir",
        required=True,
        help="SQLファイルが格納されているディレクトリパス（必須）",
    )
    parser.add_argument(
        "--error-mode",
        choices=["stop", "continue"],
        default="stop",
        help="エラー時の動作: stop（中断・確認） or continue（スキップ）。デフォルト: stop",
    )
    parser.add_argument(
        "--autocommit",
        choices=["true", "false"],
        default="true",
        help="自動コミット: true or false。デフォルト: true",
    )
    parser.add_argument(
        "--log-dir",
        default="./logs",
        help="ログファイル出力先ディレクトリ。デフォルト: ./logs",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """メイン処理。終了コード（0=成功、1=失敗）を返す。"""
    args = parse_args(argv)
    logger = setup_logging(args.log_dir)

    logger.info("========== Oracle SQL一括実行 開始 ==========")
    logger.info("設定ファイル : %s", args.config)
    logger.info("SQLディレクトリ: %s", args.sql_dir)
    logger.info("エラーモード  : %s", args.error_mode)
    logger.info("自動コミット  : %s", args.autocommit)
    logger.info("ログディレクトリ: %s", args.log_dir)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, yaml.YAMLError) as exc:
        logger.error("設定ファイルの読み込みエラー: %s", exc)
        return 1

    try:
        sql_files = collect_sql_files(args.sql_dir)
    except NotADirectoryError as exc:
        logger.error("%s", exc)
        return 1

    if not sql_files:
        logger.warning("SQLファイルが見つかりませんでした: %s", args.sql_dir)
        return 0

    logger.info("実行対象SQLファイル数: %d", len(sql_files))
    for f in sql_files:
        logger.info("  - %s", f.name)

    # 接続テスト
    try:
        connection = create_connection(config)
        logger.info("データベース接続成功")
    except (oracledb.DatabaseError, KeyError, ValueError) as exc:
        logger.error("データベース接続エラー: %s", exc)
        return 1

    autocommit = args.autocommit.lower() == "true"

    try:
        all_ok = run(
            connection=connection,
            sql_files=sql_files,
            error_mode=args.error_mode,
            autocommit=autocommit,
            logger=logger,
        )
    finally:
        try:
            connection.close()
            logger.info("データベース接続を切断しました。")
        except oracledb.DatabaseError:
            pass

    logger.info("========== Oracle SQL一括実行 終了 ==========")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
