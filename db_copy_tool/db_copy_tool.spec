# -*- mode: python ; coding: utf-8 -*-
# PyInstaller specファイル
# Oracle DB オブジェクトコピーツール

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# oracledb thin mode が動作するよう、cryptography関連を明示的に同梱する。
oracledb_hiddenimports = collect_submodules('oracledb')
cryptography_x509_hiddenimports = collect_submodules('cryptography.x509')
cryptography_hazmat_hiddenimports = collect_submodules('cryptography.hazmat')

a = Analysis(
    ['db_copy_gui.py'],
    pathex=['.'],  # 現在のディレクトリのモジュールを検索
    binaries=[],
    datas=[
        ('db_manager.py', '.'),
        ('tnsnames_parser.py', '.'),
    ],
    hiddenimports=[
        'db_manager',
        'tnsnames_parser',
        'oracledb',
        'cryptography',
        'cryptography.x509',
        'cryptography.x509.oid',
        'cryptography.hazmat',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.primitives.kdf',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'cryptography.hazmat.primitives.kdf.hkdf',
        'cryptography.hazmat.primitives.kdf.scrypt',
        'cryptography.hazmat.backends',
        'cryptography.hazmat.backends.openssl',
        'cffi',
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        'tkinter.messagebox',
        'tkinter.filedialog',
    ] + oracledb_hiddenimports + cryptography_x509_hiddenimports + cryptography_hazmat_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DBCopyTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # コンソールウィンドウを表示しない
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # アイコンファイルがあればここに指定
)
