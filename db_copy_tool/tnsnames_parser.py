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
        
        # エントリを解析（正規表現）
        # TNSエントリのパターン: NAME = (DESCRIPTION = ... )
        pattern = r'(\w+)\s*=\s*\(DESCRIPTION\s*=\s*(.+?)\)(?:\s*\n|$)'
        
        for match in re.finditer(pattern, content, re.DOTALL | re.IGNORECASE):
            entry_name = match.group(1).strip()
            entry_content = match.group(2).strip()
            
            entry = self._parse_entry(entry_name, entry_content)
            if entry:
                self.entries[entry_name.upper()] = entry
        
        logging.info(f"tnsnames.ora から {len(self.entries)} 件のエントリを読み込みました")
    
    def _parse_entry(self, name: str, content: str) -> Optional[TnsEntry]:
        """個別のTNSエントリを解析。
        
        Args:
            name: エントリ名
            content: エントリの内容
            
        Returns:
            TnsEntry または None
        """
        # HOST を抽出
        host_match = re.search(r'HOST\s*=\s*([^\s\)]+)', content, re.IGNORECASE)
        if not host_match:
            logging.warning(f"{name}: HOST が見つかりません")
            return None
        host = host_match.group(1).strip()
        
        # PORT を抽出
        port_match = re.search(r'PORT\s*=\s*(\d+)', content, re.IGNORECASE)
        if not port_match:
            logging.warning(f"{name}: PORT が見つかりません")
            return None
        port = int(port_match.group(1))
        
        # SERVICE_NAME を抽出
        service_match = re.search(r'SERVICE_NAME\s*=\s*([^\s\)]+)', content, re.IGNORECASE)
        service_name = service_match.group(1).strip() if service_match else None
        
        # SID を抽出（SERVICE_NAME がない場合）
        sid_match = re.search(r'SID\s*=\s*([^\s\)]+)', content, re.IGNORECASE)
        sid = sid_match.group(1).strip() if sid_match else None
        
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
