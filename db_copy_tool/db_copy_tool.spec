# -*- mode: python ; coding: utf-8 -*-
# PyInstaller specファイル
# Oracle DB オブジェクトコピーツール

block_cipher = None

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
        'cffi',
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        'tkinter.messagebox',
        'tkinter.filedialog',
    ],
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
