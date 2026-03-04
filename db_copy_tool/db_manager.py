"""Oracle データベース接続とオブジェクト管理モジュール.

Oracle DBのオブジェクトを管理し、別のDBへコピーする機能を提供。
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Tuple, Callable, Any
import logging
import fnmatch

try:
    import oracledb
except ImportError:
    try:
        import cx_Oracle as oracledb
    except ImportError:
        raise ImportError("oracledb または cx_Oracle のインストールが必要です")


class ObjectType(Enum):
    """データベースオブジェクトの種類。"""
    TABLE = "TABLE"
    VIEW = "VIEW"
    PROCEDURE = "PROCEDURE"
    FUNCTION = "FUNCTION"
    PACKAGE = "PACKAGE"
    PACKAGE_BODY = "PACKAGE BODY"
    TRIGGER = "TRIGGER"
    SEQUENCE = "SEQUENCE"
    SYNONYM = "SYNONYM"
    TYPE = "TYPE"


@dataclass
class ConnectionConfig:
    """データベース接続設定。"""
    host: str
    port: int
    service: str
    username: str
    password: str
    
    def get_dsn(self) -> str:
        """DSN文字列を取得。
        
        Returns:
            DSN文字列
        """
        return f"{self.host}:{self.port}/{self.service}"


@dataclass
class DatabaseObject:
    """データベースオブジェクト。"""
    name: str
    object_type: ObjectType
    owner: str
    status: Optional[str] = None
    created: Optional[str] = None
    last_ddl_time: Optional[str] = None


@dataclass
class CopyResult:
    """コピー結果。"""
    object_name: str
    object_type: ObjectType
    success: bool
    error_message: Optional[str] = None


class DatabaseManager:
    """データベース接続とオブジェクト管理クラス。"""
    
    def __init__(
        self,
        source_config: ConnectionConfig,
        target_config: ConnectionConfig
    ):
        """初期化。
        
        Args:
            source_config: ソースDB接続設定
            target_config: ターゲットDB接続設定
        """
        self.source_config = source_config
        self.target_config = target_config
        self.source_conn: Optional[oracledb.Connection] = None
        self.target_conn: Optional[oracledb.Connection] = None
        
        logging.info("DatabaseManager初期化完了")

    def _create_connection(self, config: ConnectionConfig) -> oracledb.Connection:
        """ドライバ互換性を考慮してDB接続を作成。"""
        connect_kwargs: Dict[str, Any] = {
            "user": config.username,
            "password": config.password,
            "dsn": config.get_dsn(),
            "encoding": "UTF-8",
            "nencoding": "UTF-8",
        }

        try:
            return oracledb.connect(**connect_kwargs)
        except TypeError as exc:
            error_text = str(exc)
            if "unexpected keyword argument 'encoding'" in error_text or "unexpected keyword argument 'nencoding'" in error_text:
                logging.info("DBドライバが encoding/nencoding 未対応のため、標準設定で再接続します")
                connect_kwargs.pop("encoding", None)
                connect_kwargs.pop("nencoding", None)
                return oracledb.connect(**connect_kwargs)
            raise
    
    def connect_source(self) -> oracledb.Connection:
        """ソースDBに接続。
        
        Returns:
            接続オブジェクト
        """
        if not self.source_conn:
            logging.info(f"ソースDB接続: {self.source_config.get_dsn()}")
            self.source_conn = self._create_connection(self.source_config)
            logging.info("ソースDB接続成功")
        return self.source_conn
    
    def connect_target(self) -> oracledb.Connection:
        """ターゲットDBに接続。
        
        Returns:
            接続オブジェクト
        """
        if not self.target_conn:
            logging.info(f"ターゲットDB接続: {self.target_config.get_dsn()}")
            self.target_conn = self._create_connection(self.target_config)
            logging.info("ターゲットDB接続成功")
        return self.target_conn
    
    def disconnect(self) -> None:
        """両方のDB接続を切断。"""
        if self.source_conn:
            self.source_conn.close()
            self.source_conn = None
            logging.info("ソースDB切断")
        
        if self.target_conn:
            self.target_conn.close()
            self.target_conn = None
            logging.info("ターゲットDB切断")
    
    def test_connections(self) -> bool:
        """接続テストを実行。
        
        Returns:
            両方の接続が成功した場合True
        """
        try:
            # ソース接続テスト
            source_conn = self.connect_source()
            cursor = source_conn.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.fetchone()
            cursor.close()
            logging.info("ソースDB接続テスト成功")
            
            # ターゲット接続テスト
            target_conn = self.connect_target()
            cursor = target_conn.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.fetchone()
            cursor.close()
            logging.info("ターゲットDB接続テスト成功")
            
            return True
        
        except Exception as e:
            logging.error(f"接続テスト失敗: {e}", exc_info=True)
            return False
    
    def filter_objects_by_pattern(
        self,
        objects: List[DatabaseObject],
        patterns: Optional[List[str]] = None
    ) -> List[DatabaseObject]:
        """ワイルドカードパターンでオブジェクトをフィルタリング。
        
        Args:
            objects: オブジェクト一覧
            patterns: ワイルドカードパターンのリスト
                     Noneまたは空リストの場合は全件返す
            
        Returns:
            フィルタリングされたオブジェクト一覧
        
        Examples:
            patterns = ["USER_%", "%_TMP"]
            → USER_で始まるまたは_TMPで終わるオブジェクト
        
        Note:
            Oracleスタイルのワイルドカードを使用:
            - % : 任意の文字列（0文字以上）
            - _ : 任意の1文字
        """
        if not patterns:
            return objects
        
        filtered = []
        for obj in objects:
            # いずれかのパターンにマッチすれば含める
            for pattern in patterns:
                # Oracleスタイル(%, _)をfnmatchスタイル(*, ?)に変換
                fnmatch_pattern = pattern.replace('%', '*').replace('_', '?')
                if fnmatch.fnmatch(obj.name.upper(), fnmatch_pattern.upper()):
                    filtered.append(obj)
                    break
        
        logging.info(f"フィルタ適用: {len(objects)} 件 → {len(filtered)} 件")
        return filtered
    
    def get_source_objects(
        self,
        object_types: List[ObjectType],
        name_patterns: Optional[List[str]] = None
    ) -> List[DatabaseObject]:
        """ソースDBのオブジェクト一覧を取得。
        
        Args:
            object_types: 取得するオブジェクトタイプ
            name_patterns: オブジェクト名のフィルタパターン
                          例: ["USER_%", "%_TMP"]
            
        Returns:
            オブジェクト一覧
        """
        conn = self.connect_source()
        cursor = conn.cursor()
        
        objects: List[DatabaseObject] = []
        
        for obj_type in object_types:
            try:
                # オブジェクトタイプに応じたクエリ
                if obj_type == ObjectType.PACKAGE:
                    # パッケージとパッケージボディを両方取得
                    query = """
                        SELECT object_name, object_type, owner, status,
                               TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS') as created,
                               TO_CHAR(last_ddl_time, 'YYYY-MM-DD HH24:MI:SS') as last_ddl_time
                        FROM user_objects
                        WHERE object_type IN ('PACKAGE', 'PACKAGE BODY')
                        ORDER BY object_name, object_type
                    """
                else:
                    query = f"""
                        SELECT object_name, object_type, owner, status,
                               TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS') as created,
                               TO_CHAR(last_ddl_time, 'YYYY-MM-DD HH24:MI:SS') as last_ddl_time
                        FROM user_objects
                        WHERE object_type = '{obj_type.value}'
                        ORDER BY object_name
                    """
                
                cursor.execute(query)
                
                for row in cursor:
                    obj_name, obj_type_str, owner, status, created, last_ddl_time = row
                    
                    # object_typeの変換
                    try:
                        obj_type_enum = ObjectType(obj_type_str)
                    except ValueError:
                        obj_type_enum = obj_type
                    
                    objects.append(DatabaseObject(
                        name=obj_name,
                        object_type=obj_type_enum,
                        owner=owner,
                        status=status,
                        created=created,
                        last_ddl_time=last_ddl_time
                    ))
                
                logging.info(f"{obj_type.value}: {len([o for o in objects if o.object_type == obj_type])} 件")
            
            except Exception as e:
                logging.error(f"{obj_type.value}の取得エラー: {e}")
        
        cursor.close()
        
        # フィルタ適用
        if name_patterns:
            objects = self.filter_objects_by_pattern(objects, name_patterns)
        
        return objects
    
    def get_target_objects(
        self,
        object_types: List[ObjectType],
        name_patterns: Optional[List[str]] = None
    ) -> List[DatabaseObject]:
        """ターゲットDBのオブジェクト一覧を取得。
        
        Args:
            object_types: 取得するオブジェクトタイプ
            name_patterns: オブジェクト名のフィルタパターン
                          例: ["USER_%", "%_TMP"]
            
        Returns:
            オブジェクト一覧
        """
        conn = self.connect_target()
        cursor = conn.cursor()
        
        objects: List[DatabaseObject] = []
        
        for obj_type in object_types:
            try:
                # オブジェクトタイプに応じたクエリ
                if obj_type == ObjectType.PACKAGE:
                    query = """
                        SELECT object_name, object_type, owner, status,
                               TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS') as created,
                               TO_CHAR(last_ddl_time, 'YYYY-MM-DD HH24:MI:SS') as last_ddl_time
                        FROM user_objects
                        WHERE object_type IN ('PACKAGE', 'PACKAGE BODY')
                        ORDER BY object_name, object_type
                    """
                else:
                    query = f"""
                        SELECT object_name, object_type, owner, status,
                               TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS') as created,
                               TO_CHAR(last_ddl_time, 'YYYY-MM-DD HH24:MI:SS') as last_ddl_time
                        FROM user_objects
                        WHERE object_type = '{obj_type.value}'
                        ORDER BY object_name
                    """
                
                cursor.execute(query)
                
                for row in cursor:
                    obj_name, obj_type_str, owner, status, created, last_ddl_time = row
                    
                    try:
                        obj_type_enum = ObjectType(obj_type_str)
                    except ValueError:
                        obj_type_enum = obj_type
                    
                    objects.append(DatabaseObject(
                        name=obj_name,
                        object_type=obj_type_enum,
                        owner=owner,
                        status=status,
                        created=created,
                        last_ddl_time=last_ddl_time
                    ))
                
                logging.info(f"[TARGET] {obj_type.value}: {len([o for o in objects if o.object_type == obj_type])} 件")
            
            except Exception as e:
                logging.error(f"[TARGET] {obj_type.value}の取得エラー: {e}")
        
        cursor.close()
        
        # フィルタ適用
        if name_patterns:
            objects = self.filter_objects_by_pattern(objects, name_patterns)
        
        return objects
    
    def compare_objects(
        self,
        source_objects: List[DatabaseObject],
        target_objects: List[DatabaseObject]
    ) -> Dict[str, List[DatabaseObject]]:
        """ソースとターゲットのオブジェクトを比較。
        
        Args:
            source_objects: ソースDB側のオブジェクト
            target_objects: ターゲットDB側のオブジェクト
            
        Returns:
            比較結果の辞書
            {
                'only_in_source': ターゲットに存在しないオブジェクト,
                'only_in_target': ソースに存在しないオブジェクト,
                'in_both': 両方に存在するオブジェクト
            }
        """
        # オブジェクト名とタイプのキーを作成
        source_keys = {(obj.name, obj.object_type) for obj in source_objects}
        target_keys = {(obj.name, obj.object_type) for obj in target_objects}
        
        # 比較結果を辞書で保存
        source_dict = {(obj.name, obj.object_type): obj for obj in source_objects}
        target_dict = {(obj.name, obj.object_type): obj for obj in target_objects}
        
        only_in_source = [source_dict[key] for key in source_keys - target_keys]
        only_in_target = [target_dict[key] for key in target_keys - source_keys]
        in_both = [source_dict[key] for key in source_keys & target_keys]
        
        return {
            'only_in_source': only_in_source,
            'only_in_target': only_in_target,
            'in_both': in_both
        }
    
    def get_object_ddl(
        self,
        object_name: str,
        object_type: ObjectType
    ) -> Optional[str]:
        """オブジェクトのDDLを取得。
        
        Args:
            object_name: オブジェクト名
            object_type: オブジェクトタイプ
            
        Returns:
            DDL文字列、取得失敗時はNone
        """
        conn = self.connect_source()
        cursor = conn.cursor()
        
        try:
            if object_type in [ObjectType.PROCEDURE, ObjectType.FUNCTION, ObjectType.PACKAGE, ObjectType.PACKAGE_BODY, ObjectType.TRIGGER]:
                # ストアドプログラムの場合、user_sourceから取得
                query = """
                    SELECT text
                    FROM user_source
                    WHERE name = :name
                    AND type = :type
                    ORDER BY line
                """
                cursor.execute(query, {
                    'name': object_name.upper(),
                    'type': object_type.value
                })
                
                lines = [row[0] for row in cursor]
                
                if lines:
                    ddl = "".join(lines)
                    return f"CREATE OR REPLACE {ddl}"
                else:
                    return None
            
            elif object_type == ObjectType.VIEW:
                # ビューの場合
                query = """
                    SELECT text
                    FROM user_views
                    WHERE view_name = :name
                """
                cursor.execute(query, {'name': object_name.upper()})
                row = cursor.fetchone()
                
                if row:
                    return f"CREATE OR REPLACE VIEW {object_name} AS\n{row[0]}"
                else:
                    return None
            
            elif object_type == ObjectType.SEQUENCE:
                # シーケンスの場合
                query = """
                    SELECT min_value, max_value, increment_by, cycle_flag, cache_size
                    FROM user_sequences
                    WHERE sequence_name = :name
                """
                cursor.execute(query, {'name': object_name.upper()})
                row = cursor.fetchone()
                
                if row:
                    min_val, max_val, incr, cycle, cache = row
                    ddl = f"CREATE SEQUENCE {object_name}\n"
                    ddl += f"  MINVALUE {min_val}\n"
                    ddl += f"  MAXVALUE {max_val}\n"
                    ddl += f"  INCREMENT BY {incr}\n"
                    ddl += f"  {'CYCLE' if cycle == 'Y' else 'NOCYCLE'}\n"
                    ddl += f"  CACHE {cache}"
                    return ddl
                else:
                    return None
            
            else:
                # その他の場合はDBMS_METADATAを使用
                query = """
                    SELECT DBMS_METADATA.GET_DDL(:type, :name) FROM DUAL
                """
                cursor.execute(query, {
                    'type': object_type.value,
                    'name': object_name.upper()
                })
                row = cursor.fetchone()
                
                if row and row[0]:
                    # CLOBを文字列に変換
                    ddl = row[0].read() if hasattr(row[0], 'read') else str(row[0])
                    return ddl
                else:
                    return None
        
        except Exception as e:
            logging.error(f"DDL取得エラー ({object_name}): {e}", exc_info=True)
            return None
        
        finally:
            cursor.close()
    
    def drop_object(
        self,
        object_name: str,
        object_type: ObjectType
    ) -> Tuple[bool, Optional[str]]:
        """ターゲットDBのオブジェクトを削除。
        
        Args:
            object_name: オブジェクト名
            object_type: オブジェクトタイプ
            
        Returns:
            (成功フラグ, エラーメッセージ)
        """
        conn = self.connect_target()
        cursor = conn.cursor()
        
        try:
            # DROP文を作成
            if object_type == ObjectType.PACKAGE:
                # パッケージの場合、BODYを先に削除
                drop_sql = f"DROP PACKAGE {object_name}"
            else:
                drop_sql = f"DROP {object_type.value} {object_name}"
            
            logging.info(f"実行: {drop_sql}")
            cursor.execute(drop_sql)
            conn.commit()
            
            return True, None
        
        except Exception as e:
            # オブジェクトが存在しない場合のエラーは無視
            error_str = str(e).upper()
            if "ORA-04043" in error_str or "NOT EXIST" in error_str:
                logging.info(f"{object_name} は存在しません（スキップ）")
                return True, None
            else:
                logging.error(f"DROP失敗 ({object_name}): {e}")
                return False, str(e)
        
        finally:
            cursor.close()
    
    def create_object(
        self,
        ddl: str,
        object_name: str
    ) -> Tuple[bool, Optional[str]]:
        """ターゲットDBにオブジェクトを作成。
        
        Args:
            ddl: DDL文
            object_name: オブジェクト名（ログ用）
            
        Returns:
            (成功フラグ, エラーメッセージ)
        """
        conn = self.connect_target()
        cursor = conn.cursor()
        
        try:
            logging.info(f"オブジェクト作成: {object_name}")
            cursor.execute(ddl)
            conn.commit()
            
            return True, None
        
        except Exception as e:
            logging.error(f"CREATE失敗 ({object_name}): {e}")
            return False, str(e)
        
        finally:
            cursor.close()
    
    def copy_objects(
        self,
        object_types: List[ObjectType],
        drop_before_create: bool = True,
        skip_errors: bool = True,
        name_patterns: Optional[List[str]] = None,
        specific_objects: Optional[List[DatabaseObject]] = None,
        is_dry_run: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[CopyResult]:
        """オブジェクトをコピー。
        
        Args:
            object_types: コピーするオブジェクトタイプ
            drop_before_create: 作成前に削除するか
            skip_errors: エラー発生時も続行するか
            name_patterns: オブジェクト名のフィルタパターン
            specific_objects: 特定のオブジェクトリスト（指定された場合はこれを使用）
            is_dry_run: ドライランモード（検証のみ、実行しない）
            progress_callback: 進捗コールバック(現在数, 総数, メッセージ)
            
        Returns:
            コピー結果のリスト
        """
        results: List[CopyResult] = []
        
        # オブジェクト一覧取得（specific_objectsが指定されていない場合）
        if specific_objects is not None:
            objects = specific_objects
        else:
            objects = self.get_source_objects(object_types, name_patterns)
        
        # オブジェクトを優先度順にソート（パッケージ優先）
        objects = self._sort_objects_by_priority(objects)
        
        total_count = len(objects)
        logging.info(f"コピー対象: {total_count} 件")
        
        if is_dry_run:
            logging.info("【ドライランモード】実際のコピーは実行されません")
        
        for idx, obj in enumerate(objects, 1):
            # 進捗コールバック
            if progress_callback:
                progress_callback(idx, total_count, f"{obj.object_type.value} {obj.name}")
            
            logging.info(f"[{idx}/{total_count}] 処理中: {obj.object_type.value} {obj.name}")
            
            try:
                # DDL取得
                ddl = self.get_object_ddl(obj.name, obj.object_type)
                
                if not ddl:
                    error_msg = "DDLの取得に失敗しました"
                    logging.error(error_msg)
                    results.append(CopyResult(
                        object_name=obj.name,
                        object_type=obj.object_type,
                        success=False,
                        error_message=error_msg
                    ))
                    
                    if not skip_errors:
                        break
                    continue
                
                # DROP実行
                should_drop = False
                if obj.object_type not in [ObjectType.TABLE, ObjectType.VIEW]:
                    should_drop = True
                elif drop_before_create:
                    should_drop = True
                
                if should_drop:
                    if is_dry_run:
                        logging.info(f"[DRY-RUN] DROP {obj.object_type.value} {obj.name}")
                        success, error = True, None
                    else:
                        success, error = self.drop_object(obj.name, obj.object_type)
                    
                    if not success and not skip_errors:
                        results.append(CopyResult(
                            object_name=obj.name,
                            object_type=obj.object_type,
                            success=False,
                            error_message=f"DROP失敗: {error}"
                        ))
                        break
                
                # CREATE実行
                if is_dry_run:
                    logging.info(f"[DRY-RUN] CREATE {obj.object_type.value} {obj.name}")
                    success, error = True, None
                else:
                    success, error = self.create_object(ddl, obj.name)
                
                results.append(CopyResult(
                    object_name=obj.name,
                    object_type=obj.object_type,
                    success=success,
                    error_message=error
                ))
                
                if not success and not skip_errors:
                    break
            
            except Exception as e:
                error_msg = f"予期しないエラー: {e}"
                logging.error(error_msg, exc_info=True)
                
                results.append(CopyResult(
                    object_name=obj.name,
                    object_type=obj.object_type,
                    success=False,
                    error_message=error_msg
                ))
                
                if not skip_errors:
                    break
        
        return results
    
    def _sort_objects_by_priority(self, objects: List[DatabaseObject]) -> List[DatabaseObject]:
        """オブジェクトを優先度順にソート（パッケージ優先）。
        
        コピー順序：
        1. PACKAGE と PACKAGE BODY（依存関係を考慮）
        2. SEQUENCE（シーケンス依存オブジェクト用）
        3. PROCEDURE, FUNCTION（プロシージャ/ファンクション）
        4. TRIGGER（トリガー）
        5. VIEW, SYNONYM（ビュー・シノニム）
        6. TABLE（テーブル）
        7. その他
        
        Args:
            objects: オブジェクト一覧
            
        Returns:
            ソート済みのオブジェクト一覧
        """
        priority_map = {
            ObjectType.PACKAGE: 1,
            ObjectType.PACKAGE_BODY: 1,
            ObjectType.SEQUENCE: 2,
            ObjectType.PROCEDURE: 3,
            ObjectType.FUNCTION: 3,
            ObjectType.TRIGGER: 4,
            ObjectType.VIEW: 5,
            ObjectType.SYNONYM: 5,
            ObjectType.TABLE: 6,
            ObjectType.TYPE: 7,
        }
        
        def get_priority(obj: DatabaseObject) -> Tuple[int, str]:
            priority = priority_map.get(obj.object_type, 99)
            return (priority, obj.name.upper())
        
        sorted_objects = sorted(objects, key=get_priority)
        logging.info(f"オブジェクトを優先度順にソート: PACKAGE優先")
        
        return sorted_objects

    
    def __del__(self):
        """デストラクタ。"""
        self.disconnect()
