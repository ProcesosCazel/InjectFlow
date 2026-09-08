from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRITICAL_RELATIVE = (
    Path("data/Data.xlsx"),
    Path("data/Mapeo.xlsx"),
    Path("plantillas/Haitian Zeres Gen V.xlsx"),
    Path("plantillas/Haitian Zeres Gen III.xlsx"),
    Path("web/index.html"),
    Path("web/js/main.js"),
    Path("web/css/styles.css"),
    Path("web/assets/LogoCazel.webp"),
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"[ERROR] {message}")


def main() -> int:
    if len(sys.argv) != 2:
        fail("Uso: verify_distribution.py <carpeta_distribucion>")

    dist = Path(sys.argv[1]).resolve()
    if not dist.is_dir():
        fail(f"No existe la distribucion: {dist}")

    exe = dist / "InjectFlow.exe"
    if not exe.is_file():
        fail("Falta InjectFlow.exe")

    internal = dist / "_internal"
    if not internal.is_dir():
        fail("Falta la carpeta _internal de PyInstaller")

    for relative in CRITICAL_RELATIVE:
        source = ROOT / relative
        target = dist / relative
        if not target.is_file():
            fail(f"Falta {relative.as_posix()} en la distribucion")
        if sha256(source) != sha256(target):
            fail(f"Hash diferente para {relative.as_posix()}")

    for folder in (dist / "input", dist / "output"):
        if not folder.is_dir():
            fail(f"Falta carpeta {folder.name}")

    if (dist / "data" / "Historial.csv").exists():
        fail("La distribucion inicial no debe incluir Historial.csv")

    generated = list((dist / "output").glob("*.xlsx"))
    if generated:
        fail("La distribucion inicial contiene hojas generadas en output/")

    manifest = dist / "RELEASE_ASSET_SHA256.txt"
    lines = [
        "SHA-256 - INJECTFLOW v2.0 DISTRIBUTION",
        "",
        f"{sha256(exe)}  InjectFlow.exe",
    ]
    for relative in CRITICAL_RELATIVE:
        lines.append(f"{sha256(dist / relative)}  {relative.as_posix()}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("[OK] InjectFlow.exe presente")
    print("[OK] _internal presente")
    print("[OK] Activos externos identicos al codigo fuente")
    print("[OK] input/ y output/ preparados")
    print("[OK] Historial y output iniciales limpios")
    print(f"[OK] Manifest generado: {manifest.name}")
    print("\nDISTRIBUCION v2.0: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
