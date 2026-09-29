from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta
from pathlib import Path


HISTORY_FIELDS = (
    "FECHA_HORA",
    "MAQUINA",
    "MOLDE",
    "MODO",
    "ARCHIVO_GENERADO",
)
HISTORY_DATETIME_FORMAT = "%d-%m-%Y %H:%M:%S"
HISTORY_RETENTION_DAYS = 90

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename_component(value: str, *, fallback: str = "SIN_DATO") -> str:
    """Return a Windows-safe filename component without changing displayed data."""
    text = _INVALID_FILENAME_CHARS.sub("-", str(value).strip())
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def build_dynamic_output_path(
    output_dir: Path,
    *,
    mold: str,
    machine: str,
    when: datetime | None = None,
) -> Path:
    """Build a unique output path such as I-1560_128_04-09-2026_14-15.xlsx.

    Windows does not permit ':' in filenames, so the time separator is '-'. If a
    file with the same mold/machine/minute already exists, _02, _03, ... is added
    instead of overwriting an earlier generation.
    """
    stamp = when or datetime.now()
    mold_part = sanitize_filename_component(mold, fallback="SIN_MOLDE")
    machine_part = sanitize_filename_component(machine, fallback="SIN_MAQUINA")
    base = f"{mold_part}_{machine_part}_{stamp.strftime('%d-%m-%Y_%H-%M')}"

    output_dir = Path(output_dir)
    candidate = output_dir / f"{base}.xlsx"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"{base}_{counter:02d}.xlsx"
        counter += 1
    return candidate


def _parse_history_datetime(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in (HISTORY_DATETIME_FORMAT, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _read_history_rows(history_path: Path) -> list[dict[str, str]]:
    history_path = Path(history_path)
    if not history_path.exists():
        return []

    rows: list[dict[str, str]] = []
    with history_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not row:
                continue
            rows.append({field: str(row.get(field, "") or "") for field in HISTORY_FIELDS})
    return rows


def _write_history_rows(history_path: Path, rows: list[dict[str, str]]) -> None:
    history_path = Path(history_path)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = history_path.with_suffix(history_path.suffix + ".tmp")

    try:
        with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HISTORY_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(history_path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def cleanup_generation_history(
    history_path: Path,
    *,
    when: datetime | None = None,
    retention_days: int = HISTORY_RETENTION_DAYS,
) -> int:
    """Delete history rows older than the configured retention period.

    The generated Excel files are never deleted. A row exactly 90 days old is
    kept; only rows strictly older than the cutoff are removed.

    This function is safe to call repeatedly. If the history file does not yet
    exist, it simply returns 0 and does not create an empty file.

    Returns the number of rows that remain after cleanup.
    """
    history_path = Path(history_path)
    if not history_path.exists():
        return 0

    now = when or datetime.now()
    cutoff = now - timedelta(days=int(retention_days))
    rows = _read_history_rows(history_path)

    kept: list[dict[str, str]] = []
    removed = 0
    for row in rows:
        parsed = _parse_history_datetime(row.get("FECHA_HORA", ""))

        # Filas antiguas creadas por versiones previas que no puedan interpretar
        # la fecha se conservan para no destruir información manual/auditada.
        if parsed is None or parsed >= cutoff:
            kept.append(row)
        else:
            removed += 1

    if removed:
        _write_history_rows(history_path, kept)

    return len(kept)


def append_generation_history(
    history_path: Path,
    *,
    machine: str,
    mold: str,
    mode: str,
    output_path: Path,
    when: datetime | None = None,
    retention_days: int = HISTORY_RETENTION_DAYS,
) -> int:
    """Append one successful generation and enforce the 90-day retention policy.

    Cleanup happens every time a successful sheet is generated. The GUI also
    calls cleanup on application startup and before opening Historial.csv, so the
    retention policy remains active even when no new sheet is generated.

    Only history rows are deleted; generated Excel files are never deleted.
    Returns the number of history rows kept after the update.
    """
    now = when or datetime.now()
    cutoff = now - timedelta(days=int(retention_days))
    history_path = Path(history_path)
    history_path.parent.mkdir(parents=True, exist_ok=True)

    kept: list[dict[str, str]] = []
    if history_path.exists():
        rows = _read_history_rows(history_path)
        for row in rows:
            parsed = _parse_history_datetime(row.get("FECHA_HORA", ""))
            if parsed is None or parsed >= cutoff:
                kept.append(row)

    kept.append(
        {
            "FECHA_HORA": now.strftime(HISTORY_DATETIME_FORMAT),
            "MAQUINA": str(machine).strip().upper(),
            "MOLDE": str(mold).strip(),
            "MODO": str(mode).strip(),
            "ARCHIVO_GENERADO": Path(output_path).name,
        }
    )

    _write_history_rows(history_path, kept)
    return len(kept)
