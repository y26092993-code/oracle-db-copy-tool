"""tnsnames.ora ファイルのパーサー.

Oracle の tnsnames.ora ファイルを解析して、接続情報を取得します。
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, List
import logging
import os

logger = logging.getLogger(__name__)


@dataclass
class TnsEntry:
    """TNS エントリ情報。"""
    name: str
    host: str
    port: int
    service_name: Optional[str] = None
    sid: Optional[str] = None
    
    def __str__(self) -> str:
        """文字列表現。"""
        service_info = self.service_name or self.sid or "?"
        return f"{self.name} ({self.host}:{self.port}/{service_info})"
    
    def get_connection_string(self) -> str:
        """簡潔形式の接続文字列を取得。
        
        Returns:
            host:port/service_name または host:port:sid の形式
        """
        if self.service_name:
            return f"{self.host}:{self.port}/{self.service_name}"
        else:
            return f"{self.host}:{self.port}:{self.sid}"
    
    def get_sqlplus_string(self, username: str = "user") -> str:
        """SQLPlus 用の接続文字列を取得。
        
        Args:
            username: ユーザー名
            
        Returns:
            SQLPlus 形式の接続文字列
        """
        if self.service_name:
            return f"{username}@{self.host}:{self.port}/{self.service_name}"
        else:
            return f"{username}@{self.host}:{self.port}:{self.sid}"
    
    def get_jdbc_url(self) -> str:
        """JDBC URL を取得。
        
        Returns:
            JDBC 接続 URL
        """
        if self.service_name:
            return f"jdbc:oracle:thin:@{self.host}:{self.port}/{self.service_name}"
        else:
            return f"jdbc:oracle:thin:@{self.host}:{self.port}:{self.sid}"
    
    def get_description_block(self) -> str:
        """tnsnames.ora 形式の DESCRIPTION ブロックを取得。
        
        Returns:
            DESCRIPTION = (...) 形式の文字列
        """
        service_param = f"(SERVICE_NAME = {self.service_name})" if self.service_name else f"(SID = {self.sid})"
        
        return f"""({self.name} =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = {self.host})(PORT = {self.port}))
    (CONNECT_DATA = {service_param})
  )
)"""
    
    def get_info_dict(self) -> Dict[str, str]:
        """接続情報を辞書で取得。
        
        Returns:
            接続情報の辞書
        """
        return {
            "name": self.name,
            "host": self.host,
            "port": str(self.port),
            "service_name": self.service_name or "N/A",
            "sid": self.sid or "N/A",
            "connection_string": self.get_connection_string(),
            "jdbc_url": self.get_jdbc_url(),
            "sqlplus": self.get_sqlplus_string(),
        }


class TnsNamesParser:
    """tnsnames.ora ファイルのパーサークラス。"""
    
    # tnsnames.ora の一般的な場所
    COMMON_PATHS = [
        r"C:\oracle\network\admin",
        r"C:\app\oracle\product\network\admin",
        r"C:\Oracle\instantclient\network\admin",
        "/usr/lib/oracle/network/admin",
        "/etc/oracle",
        "~/oracle/network/admin",
    ]
    
    def __init__(self, tnsnames_path: Optional[str] = None):
        """初期化。
        
        Args:
            tnsnames_path: tnsnames.ora ファイルのパス
                          指定しない場合は自動検索
        """
        self.tnsnames_path: Optional[Path] = None
        self.entries: Dict[str, TnsEntry] = {}
        
        if tnsnames_path:
            path = Path(tnsnames_path)
            if path.exists():
                self.tnsnames_path = path
                logging.info(f"tnsnames.ora: {self.tnsnames_path}")
            else:
                logging.warning(f"指定されたtnsnames.oraが見つかりません: {tnsnames_path}")
        else:
            # 自動検索
            self.tnsnames_path = self._find_tnsnames()
        
        if self.tnsnames_path:
            self._parse()
    
    def _find_tnsnames(self) -> Optional[Path]:
        """tnsnames.ora ファイルを自動検索。
        
        Returns:
            見つかったパス、見つからない場合は None
        """
        # 環境変数 TNS_ADMIN から探す
        tns_admin = os.environ.get('TNS_ADMIN')
        if tns_admin:
            path = Path(tns_admin) / "tnsnames.ora"
            if path.exists():
                logging.info(f"tnsnames.ora を TNS_ADMIN から検出: {path}")
                return path
        
        # 環境変数 ORACLE_HOME から探す
        oracle_home = os.environ.get('ORACLE_HOME')
        if oracle_home:
            path = Path(oracle_home) / "network" / "admin" / "tnsnames.ora"
            if path.exists():
                logging.info(f"tnsnames.ora を ORACLE_HOME から検出: {path}")
                return path
        
        # 一般的な場所を探す
        for common_path in self.COMMON_PATHS:
            path = Path(common_path).expanduser() / "tnsnames.ora"
            if path.exists():
                logging.info(f"tnsnames.ora を検出: {path}")
                return path
        
        logging.warning("tnsnames.ora が見つかりませんでした")
        return None
    
    def _parse(self) -> None:
        """tnsnames.ora ファイルを解析。"""
        if not self.tnsnames_path:
            return
        
        try:
            with open(self.tnsnames_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # UTF-8 で読めない場合は別のエンコーディングを試す
            try:
                with open(self.tnsnames_path, 'r', encoding='cp932') as f:
                    content = f.read()
            except Exception as e:
                logging.error(f"tnsnames.ora の読み込みエラー: {e}")
                return
        
        # コメントを除去
        lines = []
        for line in content.split('\n'):
            # # で始まるコメント行を除去
            if line.strip().startswith('#'):
                continue
            # 行内コメントを除去
            if '#' in line:
                line = line[:line.index('#')]
            lines.append(line)
        
        content = '\n'.join(lines)
        
        # エントリを解析
        # NAME = (DESCRIPTION = ... ) の形式
        pattern = r'(\w+)\s*=\s*\(DESCRIPTION\s*='
        
        for match in re.finditer(pattern, content, re.IGNORECASE):
            entry_name = match.group(1).strip()
            
            # NAME = ( の位置を見つける
            name_start = match.start()
            entry_paren_start = content.find('(', name_start)
            
            # 括弧のネストレベルを追跡して、対応する閉じ括弧を見つける
            paren_count = 0
            entry_paren_end = -1
            
            for i in range(entry_paren_start, len(content)):
                if content[i] == '(':
                    paren_count += 1
                elif content[i] == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        entry_paren_end = i
                        break
            
            if entry_paren_end == -1:
                logging.warning(f"{entry_name}: 対応する閉じ括弧が見つかりません")
                continue
            
            # DESCRIPTION = の後の内容を抽出
            entry_content = content[match.end():entry_paren_end].strip()
            
            entry = self._parse_entry(entry_name, entry_content)
            if entry:
                self.entries[entry_name.upper()] = entry
        
        logging.info(f"tnsnames.ora から {len(self.entries)} 件のエントリを読み込みました")
    
    def _parse_entry(self, name: str, content: str) -> Optional[TnsEntry]:
        """個別のTNSエントリを解析。
        
        Args:
            name: エントリ名
            content: エントリの内容（DESCRIPTION = ... の内側）
            
        Returns:
            TnsEntry または None
        """
        host = None
        port = None
        service_name = None
        sid = None
        
        # 簡潔な方法：正規表現で直接抽出
        # ADDRESS ブロック内の HOST と PORT を探す
        host_match = re.search(r'ADDRESS\s*=.*?\(HOST\s*=\s*([^\s\)]+)', content, re.IGNORECASE | re.DOTALL)
        if host_match:
            host = host_match.group(1).strip()
        
        port_match = re.search(r'ADDRESS\s*=.*?\(PORT\s*=\s*(\d+)', content, re.IGNORECASE | re.DOTALL)
        if port_match:
            port = int(port_match.group(1))
        
        # CONNECT_DATA ブロック内の SERVICE_NAME と SID を探す
        service_match = re.search(r'SERVICE_NAME\s*=\s*([^\s\)]+)', content, re.IGNORECASE)
        if service_match:
            service_name = service_match.group(1).strip()
        
        sid_match = re.search(r'SID\s*=\s*([^\s\)]+)', content, re.IGNORECASE)
        if sid_match:
            sid = sid_match.group(1).strip()
        
        # 必須フィールドの検証
        if not host:
            logging.warning(f"{name}: HOST が見つかりません")
            return None
        
        if not port:
            logging.warning(f"{name}: PORT が見つかりません")
            return None
        
        if not service_name and not sid:
            logging.warning(f"{name}: SERVICE_NAME も SID も見つかりません")
            return None
        
        return TnsEntry(
            name=name,
            host=host,
            port=port,
            service_name=service_name,
            sid=sid
        )
    
    def get_entries(self) -> Dict[str, TnsEntry]:
        """全てのTNSエントリを取得。
        
        Returns:
            エントリ名をキーとする辞書
        """
        return self.entries
    
    def get_entry(self, name: str) -> Optional[TnsEntry]:
        """指定した名前のTNSエントリを取得。
        
        Args:
            name: エントリ名（大文字小文字を区別しない）
            
        Returns:
            TnsEntry または None
        """
        return self.entries.get(name.upper())
    
    def has_tnsnames(self) -> bool:
        """tnsnames.ora ファイルが見つかったかどうか。
        
        Returns:
            見つかった場合 True
        """
        return self.tnsnames_path is not None
    
    def get_tnsnames_path(self) -> Optional[Path]:
        """tnsnames.ora ファイルのパスを取得。
        
        Returns:
            パス、見つからない場合は None
        """
        return self.tnsnames_path
    
    def display_entries(self) -> str:
        """読み込んだエントリの接続文字列を表示用の文字列で取得。
        
        Returns:
            フォーマットされた接続文字列情報
        """
        if not self.entries:
            return "No entries loaded from tnsnames.ora"
        
        output_lines = []
        output_lines.append(f"tnsnames.ora: {self.tnsnames_path}")
        output_lines.append(f"Entries loaded: {len(self.entries)}\n")
        
        for name in sorted(self.entries.keys()):
            entry = self.entries[name]
            output_lines.append(f"【{entry.name}】")
            output_lines.append(f"  Host:              {entry.host}")
            output_lines.append(f"  Port:              {entry.port}")
            output_lines.append(f"  Service Name:      {entry.service_name or 'N/A'}")
            output_lines.append(f"  SID:               {entry.sid or 'N/A'}")
            output_lines.append(f"  Connection String: {entry.get_connection_string()}")
            output_lines.append(f"  JDBC URL:          {entry.get_jdbc_url()}")
            output_lines.append(f"  SQLPlus:           {entry.get_sqlplus_string()}")
            output_lines.append("")
        
        return "\n".join(output_lines)
    
    def print_entries(self) -> None:
        """読み込んだエントリの接続文字列をコンソールに表示。"""
        print(self.display_entries())
