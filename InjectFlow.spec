# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path(SPECPATH).resolve()

hiddenimports = [
    "pythoncom",
    "pywintypes",
    "win32timezone",
    "win32com",
    "win32com.client",
]

excludes = [
    "pytest",
    "tests",
    "tkinterdnd2",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "wx",
    "cefpython3",
]

a = Analysis(
    [str(ROOT / "launcher_web.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="InjectFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "icono.ico"),
    version=str(ROOT / "release_tools" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="InjectFlow",
)
