def connect_source(self) -> oracledb.Connection:
    """ソースDBに接続。\n    \n    Returns:\n        接続オブジェクト\n    """
    if not self.source_conn:
        logging.info(f"ソースDB接続: {self.source_config.get_dsn()}")
        try:
            # 接続パラメータを準備
            conn_params = {
                'user': self.source_config.username,
                'password': self.source_config.password,
                'dsn': self.source_config.get_dsn()
            }
            
            # thick mode の場合のみエンコーディングパラメータを追加
            # python-oracledb の thin mode (デフォルト) では encoding パラメータは不要
            try:
                if hasattr(oracledb, 'is_thin_mode') and not oracledb.is_thin_mode():
                    conn_params['encoding'] = 'UTF-8'
                    conn_params['nencoding'] = 'UTF-8'
            except:
                # is_thin_mode が使えない場合はパラメータを追加しない
                pass
            
            self.source_conn = oracledb.connect(**conn_params)
            logging.info("ソースDB接続成功")
        except Exception as e:
            logging.error(f"ソースDB接続エラー: {e}", exc_info=True)
            raise
    return self.source_conn

def connect_target(self) -> oracledb.Connection:
    """ターゲットDBに接続。\n    \n    Returns:\n        接続オブジェクト\n    """
    if not self.target_conn:
        logging.info(f"ターゲットDB接続: {self.target_config.get_dsn()}")
        try:
            # 接続パラメータを準備
            conn_params = {
                'user': self.target_config.username,
                'password': self.target_config.password,
                'dsn': self.target_config.get_dsn()
            }
            
            # thick mode の場合のみエンコーディングパラメータを追加
            # python-oracledb の thin mode (デフォルト) では encoding パラメータは不要
            try:
                if hasattr(oracledb, 'is_thin_mode') and not oracledb.is_thin_mode():
                    conn_params['encoding'] = 'UTF-8'
                    conn_params['nencoding'] = 'UTF-8'
            except:
                # is_thin_mode が使えない場合はパラメータを追加しない
                pass
            
            self.target_conn = oracledb.connect(**conn_params)
            logging.info("ターゲットDB接続成功")
        except Exception as e:
            logging.error(f"ターゲットDB接続エラー: {e}", exc_info=True)
            raise
    return self.target_conn
