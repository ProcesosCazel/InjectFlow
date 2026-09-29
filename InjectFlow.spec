# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path(SPECPATH).resolve()

# Los archivos de negocio (data/, plantillas/, web/) se mantienen fuera de
# _internal y se copian junto a InjectFlow.exe mediante CREAR_INJECTFLOW_EXE.bat.
# Esto conserva el comportamiento existente de runtime_root()/project_root():
# Data.xlsx, Mapeo.xlsx y las plantillas pueden actualizarse sin recompilar.

a = Analysis(
    ['launcher_web.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        'clr',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'pythoncom',
        'pywintypes',
        # pywin32 loads this module dynamically while converting COM date/time
        # values. PyInstaller cannot always discover that import automatically.
        'win32timezone',
        'win32com',
        'win32com.client',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'cefpython3',
        'gi',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='InjectFlow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'icono.ico'),
    version=str(ROOT / 'build_tools' / 'InjectFlow_version_info.txt'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='InjectFlow',
)
