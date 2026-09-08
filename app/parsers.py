from __future__ import annotations

import csv
import io
import re
import zlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .errors import SourceDataError


@dataclass(frozen=True)
class ParamRecord:
    key: str
    raw_value: Decimal | str
    unit: str
    meta1: str
    meta2: str
    meta3: str


class ParamDatParser:
    CRC_RE = re.compile(rb"\[CRC:\s*16#([0-9A-Fa-f]{8})\]")

    def __init__(self, *, encoding: str = "gb18030", header_lines: int = 4, validate_crc: bool = True):
        self.encoding = encoding
        self.header_lines = int(header_lines)
        self.validate_crc = bool(validate_crc)
        self.crc_mode: str | None = None
        self.ignored_trailer_lines: list[int] = []

    def parse(self, path: Path) -> dict[str, list[ParamRecord]]:
        raw = Path(path).read_bytes()
        parts = raw.splitlines(keepends=True)
        if len(parts) <= self.header_lines:
            raise SourceDataError("Param.dat does not contain the expected header and records")
        header = b"".join(parts[: self.header_lines])
        body = b"".join(parts[self.header_lines :])

        match = self.CRC_RE.search(header)
        if self.validate_crc:
            if not match:
                raise SourceDataError("Param.dat CRC header was not found")
            expected = int(match.group(1), 16)
            candidates = [
                ("BODY_EXACT", body),
                ("BODY_NO_FINAL_EOL", body.rstrip(b"\r\n")),
            ]
            found = None
            for mode, candidate in candidates:
                actual = zlib.crc32(candidate) & 0xFFFFFFFF
                if actual == expected:
                    found = mode
                    break
            if found is None:
                actual = zlib.crc32(body) & 0xFFFFFFFF
                raise SourceDataError(
                    f"Param.dat CRC32 mismatch. Expected {expected:08X}, calculated {actual:08X}"
                )
            self.crc_mode = found

        try:
            text = body.decode(self.encoding)
        except UnicodeDecodeError as exc:
            raise SourceDataError(f"Param.dat cannot be decoded with {self.encoding}: {exc}") from exc

        result: dict[str, list[ParamRecord]] = {}
        parsed_lines: list[tuple[int, list[str] | None]] = []

        # First classify every non-empty line. Some machine exports append a
        # short non-CSV trailer after the last parameter record. We allow such
        # trailer lines only when they form a contiguous suffix of the file.
        # Malformed lines embedded between valid parameter records remain fatal.
        for line_no, line in enumerate(text.splitlines(), start=self.header_lines + 1):
            if not line.strip():
                continue
            try:
                row = next(csv.reader([line]))
            except csv.Error:
                parsed_lines.append((line_no, None))
                continue
            if row and row[-1] == "":
                row = row[:-1]
            parsed_lines.append((line_no, row if len(row) >= 6 else None))

        valid_positions = [i for i, (_, row) in enumerate(parsed_lines) if row is not None]
        if not valid_positions:
            raise SourceDataError("Param.dat does not contain any valid parameter records")

        last_valid_pos = valid_positions[-1]
        malformed_inside = [
            line_no
            for i, (line_no, row) in enumerate(parsed_lines)
            if row is None and i < last_valid_pos
        ]
        if malformed_inside:
            raise SourceDataError(
                f"Param.dat has malformed records at lines: {malformed_inside[:10]}"
            )

        self.ignored_trailer_lines = [
            line_no
            for i, (line_no, row) in enumerate(parsed_lines)
            if row is None and i > last_valid_pos
        ]

        for _, row in parsed_lines[: last_valid_pos + 1]:
            if row is None:
                continue
            key, raw_value, unit, meta1, meta2, meta3 = row[:6]
            value: Decimal | str
            try:
                value = Decimal(raw_value.strip())
            except (InvalidOperation, AttributeError):
                value = raw_value
            rec = ParamRecord(key=key, raw_value=value, unit=unit, meta1=meta1, meta2=meta2, meta3=meta3)
            result.setdefault(key, []).append(rec)
        return result


class ResulCsvParser:
    def __init__(self, *, encoding: str = "ascii", record_size: int = 300, header_records: int = 1):
        self.encoding = encoding
        self.record_size = int(record_size)
        self.header_records = int(header_records)

    def parse(self, path: Path) -> tuple[list[str], list[dict[str, str]]]:
        raw = Path(path).read_bytes()
        if b"\x00" in raw and len(raw) % self.record_size == 0:
            rows = self._parse_fixed_blocks(raw)
        else:
            rows = self._parse_normal_csv(raw)
        if len(rows) <= self.header_records:
            raise SourceDataError("Resul.csv does not contain enough records")
        header = rows[0]
        if header and header[0] == "":
            header[0] = "Record"
        data_rows: list[dict[str, str]] = []
        for n, row in enumerate(rows[self.header_records :], start=1):
            if len(row) != len(header):
                raise SourceDataError(
                    f"Resul.csv record {n} has {len(row)} columns; expected {len(header)}"
                )
            data_rows.append(dict(zip(header, row)))
        return header, data_rows

    def _parse_fixed_blocks(self, raw: bytes) -> list[list[str]]:
        rows: list[list[str]] = []
        for pos in range(0, len(raw), self.record_size):
            block = raw[pos : pos + self.record_size]
            payload = block.split(b"\x00", 1)[0].rstrip(b"\r\n")
            if not payload:
                continue
            try:
                text = payload.decode(self.encoding)
            except UnicodeDecodeError as exc:
                raise SourceDataError(f"Resul.csv block cannot be decoded with {self.encoding}: {exc}") from exc
            rows.append(next(csv.reader([text])))
        return rows

    def _parse_normal_csv(self, raw: bytes) -> list[list[str]]:
        try:
            text = raw.decode(self.encoding)
        except UnicodeDecodeError:
            text = raw.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(text)))
