from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_UP
from pathlib import Path
from typing import Any, Iterable


def is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().upper() in {"TRUE", "1", "YES", "SI", "SÍ", "ON", "ACTIVE"}


def as_decimal(value: Any, *, field: str = "value") -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} is not numeric: {value!r}") from exc


def round_decimal(value: Decimal, decimals: int | None, mode: str = "NEAREST") -> Decimal:
    if decimals is None:
        return value
    quantum = Decimal("1").scaleb(-int(decimals))
    mode_u = (mode or "NEAREST").strip().upper()
    rounding = ROUND_UP if mode_u == "UP" else ROUND_HALF_UP
    return value.quantize(quantum, rounding=rounding)


def scalar_for_excel(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def split_pipe(value: Any) -> list[str]:
    text = clean_text(value)
    return [part.strip() for part in text.split("|") if part.strip()]


def ensure_file(path: Path, label: str) -> Path:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def normalize_control_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        t = value.strip()
        try:
            d = Decimal(t)
            if d == d.to_integral_value():
                return int(d)
        except InvalidOperation:
            pass
        return t.upper()
    return value


@dataclass(frozen=True)
class Table:
    headers: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]


def require_columns(table: Table, required: Iterable[str], sheet: str) -> None:
    missing = [c for c in required if c not in table.headers]
    if missing:
        raise ValueError(f"Sheet {sheet!r} is missing columns: {', '.join(missing)}")
