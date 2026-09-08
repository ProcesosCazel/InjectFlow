from __future__ import annotations

import importlib.metadata
import platform
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Al ejecutar este archivo directamente (python release_tools\preflight_release.py),
# Python agrega release_tools/ a sys.path, pero no la raiz del proyecto.
# Insertamos explicitamente la raiz para que los imports del paquete app/
# funcionen igual que cuando InjectFlow se ejecuta desde launcher_web.py.
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)


def fail(message: str) -> None:
    raise SystemExit(f"[ERROR] {message}")


def ok(message: str) -> None:
    print(f"[OK] {message}")


def main() -> int:
    if platform.system() != "Windows":
        fail("El build oficial de InjectFlow.exe debe ejecutarse en Windows.")
    ok("Sistema operativo Windows")

    if struct.calcsize("P") * 8 != 64:
        fail("Se requiere Python de 64 bits para la release oficial.")
    ok(f"Python {platform.python_version()} de 64 bits")

    required = [
        ROOT / "launcher_web.py",
        ROOT / "loading_screen.py",
        ROOT / "preview_renderer.py",
        ROOT / "web_api.py",
        ROOT / "data" / "Data.xlsx",
        ROOT / "data" / "Mapeo.xlsx",
        ROOT / "plantillas" / "Haitian Zeres Gen V.xlsx",
        ROOT / "plantillas" / "Haitian Zeres Gen III.xlsx",
        ROOT / "web" / "index.html",
        ROOT / "web" / "js" / "main.js",
        ROOT / "web" / "css" / "styles.css",
        ROOT / "web" / "assets" / "LogoCazel.webp",
        ROOT / "icono.ico",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        fail("Faltan archivos de release: " + ", ".join(missing))
    ok("Archivos de release disponibles")

    import openpyxl  # noqa: F401
    import webview  # noqa: F401
    import pythoncom  # type: ignore  # noqa: F401
    import win32timezone  # type: ignore  # noqa: F401
    import win32com.client  # type: ignore

    ok(f"openpyxl {importlib.metadata.version('openpyxl')}")
    ok(f"pywebview {importlib.metadata.version('pywebview')}")
    ok(f"pywin32 {importlib.metadata.version('pywin32')}")
    ok(f"PyInstaller {importlib.metadata.version('pyinstaller')}")
    ok("win32timezone disponible en el entorno de build")

    spec_text = (ROOT / "InjectFlow.spec").read_text(encoding="utf-8")
    if '"win32timezone"' not in spec_text:
        fail("InjectFlow.spec no declara win32timezone como hidden import de PyInstaller.")
    ok("Hidden import win32timezone configurado en InjectFlow.spec")

    from app.catalogs import MappingCatalog

    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    if len(mapping.machines) != 26:
        fail(f"Se esperaban 26 maquinas en v2.0; se detectaron {len(mapping.machines)}.")
    ok("Mapeo.xlsx carga 26 maquinas")

    excel = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        version = str(excel.Version)
        ok(f"Microsoft Excel COM disponible (version {version})")
    except Exception as exc:
        fail(f"Microsoft Excel COM no esta disponible: {exc}")
    finally:
        if excel is not None:
            try:
                excel.Quit()
            except Exception:
                pass

    print("\nPREFLIGHT RELEASE v2.0: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
