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
    MOLD_HEATING_RE = re.compile(
        r"^MoldHeating(?P<zone>\d+)(?P<ccp>_ccp)?\.(?P<field>[^.]+)$"
    )
    BARREL_HEATING_RE = re.compile(
        r"^HeatingZoneControl(?P<zone>\d+)\.(?P<field>[^.]+)$"
    )
    ALL_HOT_RUNNING_RE = re.compile(
        r"^AllHotRunning1\\HotRunnerParameter(?P<zone>\d+)\.(?P<field>[^.]+)$"
    )
    LEGACY_ALL_HOT_RUNNING_MACHINES = frozenset({"112C", "114B", "114C", "124A"})
    # Haitian exports keep sHeatingMode=1 for unused barrel zones. In the
    # validated Gen III exports those unused channels retain this exact factory
    # profile. Treat it as inactive before Data.xlsx maps sHeatingMode to ON/OFF.
    BARREL_INACTIVE_PROFILE = {
        "sHeatingSet": Decimal(1600),
        "sHeatingMax": Decimal(100),
        "sHeatingMin": Decimal(100),
        "sHeatingStandby": Decimal(1500),
    }

    def __init__(
        self,
        *,
        encoding: str = "gb18030",
        header_lines: int = 4,
        validate_crc: bool = True,
        machine: str | None = None,
    ):
        self.encoding = encoding
        self.header_lines = int(header_lines)
        self.validate_crc = bool(validate_crc)
        self.machine = str(machine or "").strip().upper()
        self.crc_mode: str | None = None
        self.ignored_trailer_lines: list[int] = []
        self.process_warnings: list[str] = []
        self.hrs_source: str | None = None
        self.hrs_primary_active_zones: tuple[int, ...] = ()
        self.hrs_ccp_active_zones: tuple[int, ...] = ()
        self.hrs_all_hot_running_active_zones: tuple[int, ...] = ()
        self.barrel_default_inactive_zones: tuple[int, ...] = ()

    def parse(self, path: Path) -> dict[str, list[ParamRecord]]:
        self.crc_mode = None
        self.ignored_trailer_lines = []
        self.process_warnings = []
        self.hrs_source = None
        self.hrs_primary_active_zones = ()
        self.hrs_ccp_active_zones = ()
        self.hrs_all_hot_running_active_zones = ()
        self.barrel_default_inactive_zones = ()

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

        self._normalize_barrel_heating_records(result)
        used_all_hot_running = self._normalize_all_hot_running_records(result)
        self._normalize_mold_heating_records(result)
        if used_all_hot_running:
            self.hrs_source = "AllHotRunning1"
        return result

    def _normalize_barrel_heating_records(
        self, records: dict[str, list[ParamRecord]]
    ) -> None:
        """Normalize factory-default unused barrel channels to OFF.

        ``HeatingZoneControlN.sHeatingMode`` is not a reliable physical
        enable flag in Haitian exports: unused channels can retain mode 1.
        The validated machine exports identify those unused channels with a
        complete factory profile (160 C setpoint, 150 C standby and 100/100
        limits). Only when *all* profile fields match exactly do we override
        the stale mode to 0. Any partial or different profile is left intact.
        """
        zones: dict[int, dict[str, list[ParamRecord]]] = {}
        for key, recs in records.items():
            match = self.BARREL_HEATING_RE.match(key)
            if not match:
                continue
            zone = int(match.group("zone"))
            field = match.group("field")
            zones.setdefault(zone, {})[field] = recs

        inactive: list[int] = []
        for zone, fields in zones.items():
            mode_records = fields.get("sHeatingMode")
            if not mode_records:
                continue

            profile_matches = True
            for field, expected in self.BARREL_INACTIVE_PROFILE.items():
                recs = fields.get(field)
                if not recs:
                    profile_matches = False
                    break
                rec = self._select_consistent_record(
                    f"HeatingZoneControl{zone}.{field}", recs
                )
                if rec.raw_value != expected:
                    profile_matches = False
                    break

            if not profile_matches:
                continue

            mode_rec = self._select_consistent_record(
                f"HeatingZoneControl{zone}.sHeatingMode", mode_records
            )
            mode_key = f"HeatingZoneControl{zone}.sHeatingMode"
            records[mode_key] = [
                ParamRecord(
                    key=mode_key,
                    raw_value=Decimal(0),
                    unit=mode_rec.unit,
                    meta1=mode_rec.meta1,
                    meta2=mode_rec.meta2,
                    meta3=mode_rec.meta3,
                )
            ]
            inactive.append(zone)

        self.barrel_default_inactive_zones = tuple(sorted(inactive))

    def _normalize_all_hot_running_records(
        self, records: dict[str, list[ParamRecord]]
    ) -> bool:
        """Normalize the legacy Gen V HRS namespace used by 112C/114B/114C/124A.

        These four controllers export hot-runner zones as
        ``AllHotRunning1\\HotRunnerParameterN`` instead of the
        ``MoldHeatingN`` namespace expected by Data.xlsx.  The physical enable
        signal is ``sswitch`` and the temperature setpoint is ``sSetValue``.

        The compatibility path is intentionally machine-scoped and only runs
        when the normal MoldHeating/MoldHeating_ccp switch namespaces are
        absent.  That keeps future exports from these machines, should they
        adopt the standard namespace on the normal parser path.
        """
        if self.machine not in self.LEGACY_ALL_HOT_RUNNING_MACHINES:
            return False

        _primary_active, primary_has_switches = self._heating_active_zones(
            records, ccp=False
        )
        _ccp_active, ccp_has_switches = self._heating_active_zones(
            records, ccp=True
        )
        if primary_has_switches or ccp_has_switches:
            return False

        zones: dict[int, dict[str, list[ParamRecord]]] = {}
        for key, recs in list(records.items()):
            match = self.ALL_HOT_RUNNING_RE.match(key)
            if not match:
                continue
            zone = int(match.group("zone"))
            field = match.group("field")
            zones.setdefault(zone, {})[field] = recs

        if not zones:
            return False

        active: list[int] = []
        normalized_any = False
        # Gen V templates/Data.xlsx expose 40 HRS zones.  The controller may
        # export 64 physical channels; zones above 40 are intentionally ignored.
        for zone in sorted(z for z in zones if 1 <= z <= 40):
            fields = zones[zone]
            set_records = fields.get("sSetValue")
            switch_records = fields.get("sswitch")
            if not set_records or not switch_records:
                continue

            set_rec = self._select_consistent_record(
                f"AllHotRunning1\\HotRunnerParameter{zone}.sSetValue",
                set_records,
            )
            switch_rec = self._select_consistent_record(
                f"AllHotRunning1\\HotRunnerParameter{zone}.sswitch",
                switch_records,
            )

            set_key = f"MoldHeating{zone}.sHeatingSet"
            switch_key = f"MoldHeating{zone}.sHeatingZoneSwitch"
            records[set_key] = [
                ParamRecord(
                    key=set_key,
                    raw_value=set_rec.raw_value,
                    unit=set_rec.unit,
                    meta1=set_rec.meta1,
                    meta2=set_rec.meta2,
                    meta3=set_rec.meta3,
                )
            ]
            records[switch_key] = [
                ParamRecord(
                    key=switch_key,
                    raw_value=switch_rec.raw_value,
                    unit=switch_rec.unit,
                    meta1=switch_rec.meta1,
                    meta2=switch_rec.meta2,
                    meta3=switch_rec.meta3,
                )
            ]
            normalized_any = True
            if self._heating_switch_is_on(switch_key, switch_rec.raw_value):
                active.append(zone)

        self.hrs_all_hot_running_active_zones = tuple(active)
        return normalized_any

    def _normalize_mold_heating_records(
        self, records: dict[str, list[ParamRecord]]
    ) -> None:
        """Normalize hot-runner records to the legacy ``MoldHeatingN`` keys.

        Haitian exports can store HRS data in either ``MoldHeatingN`` or
        ``MoldHeatingN_ccp``. The normal namespace has first priority. If all
        its zones are OFF, the CCP namespace is used as a fallback. When both
        namespaces contain active zones, the normal namespace remains the
        source of truth and a non-blocking process warning is collected.

        Zone ON/OFF state is taken from ``sHeatingZoneSwitch``. Some exports
        retain ``sHeatingMode = 1`` even when the physical zone switch is OFF,
        so using ``sHeatingMode`` directly can falsely activate HRS zones.

        For backward compatibility, files that do not expose any
        ``sHeatingZoneSwitch`` keys are left untouched.
        """
        primary_active, primary_has_switches = self._heating_active_zones(
            records, ccp=False
        )
        ccp_active, ccp_has_switches = self._heating_active_zones(
            records, ccp=True
        )

        self.hrs_primary_active_zones = primary_active
        self.hrs_ccp_active_zones = ccp_active

        if not primary_has_switches and not ccp_has_switches:
            return

        if primary_active:
            use_ccp = False
        elif ccp_active:
            use_ccp = True
        else:
            # Both namespaces are OFF. Keep MoldHeating as first priority when
            # it exists; otherwise normalize the CCP namespace as all OFF.
            use_ccp = not primary_has_switches and ccp_has_switches

        self.hrs_source = "MoldHeating_ccp" if use_ccp else "MoldHeating"

        if primary_active and ccp_active:
            primary_text = ", ".join(str(z) for z in primary_active)
            ccp_text = ", ".join(str(z) for z in ccp_active)
            self.process_warnings.append(
                "Colada caliente: se detectaron zonas activas simultaneamente "
                f"en MoldHeating ({primary_text}) y MoldHeating_ccp ({ccp_text}). "
                "Se utilizo MoldHeating por prioridad. Revisar las zonas HRS."
            )

        self._apply_heating_source(records, use_ccp=use_ccp)

    def _heating_active_zones(
        self,
        records: dict[str, list[ParamRecord]],
        *,
        ccp: bool,
    ) -> tuple[tuple[int, ...], bool]:
        active: set[int] = set()
        has_switches = False
        for key in records:
            match = self.MOLD_HEATING_RE.match(key)
            if not match or match.group("field") != "sHeatingZoneSwitch":
                continue
            is_ccp = bool(match.group("ccp"))
            if is_ccp != ccp:
                continue
            has_switches = True
            rec = self._select_consistent_record(key, records[key])
            if self._heating_switch_is_on(key, rec.raw_value):
                active.add(int(match.group("zone")))
        return tuple(sorted(active)), has_switches

    def _apply_heating_source(
        self,
        records: dict[str, list[ParamRecord]],
        *,
        use_ccp: bool,
    ) -> None:
        selected: dict[int, dict[str, list[ParamRecord]]] = {}
        for key, recs in list(records.items()):
            match = self.MOLD_HEATING_RE.match(key)
            if not match:
                continue
            is_ccp = bool(match.group("ccp"))
            if is_ccp != use_ccp:
                continue
            zone = int(match.group("zone"))
            field = match.group("field")
            selected.setdefault(zone, {})[field] = recs

        for zone, fields in selected.items():
            target_prefix = f"MoldHeating{zone}"

            # CCP is normalized into the legacy namespace expected by Data.xlsx.
            if use_ccp:
                for field, recs in fields.items():
                    target_key = f"{target_prefix}.{field}"
                    records[target_key] = [
                        ParamRecord(
                            key=target_key,
                            raw_value=rec.raw_value,
                            unit=rec.unit,
                            meta1=rec.meta1,
                            meta2=rec.meta2,
                            meta3=rec.meta3,
                        )
                        for rec in recs
                    ]

            # Data.xlsx currently maps HRSZoneNMode from sHeatingMode. Feed that
            # existing key with the real physical switch state instead.
            switch_records = fields.get("sHeatingZoneSwitch")
            if switch_records:
                switch_rec = self._select_consistent_record(
                    (
                        f"MoldHeating{zone}_ccp.sHeatingZoneSwitch"
                        if use_ccp
                        else f"MoldHeating{zone}.sHeatingZoneSwitch"
                    ),
                    switch_records,
                )
                mode_key = f"{target_prefix}.sHeatingMode"
                records[mode_key] = [
                    ParamRecord(
                        key=mode_key,
                        raw_value=switch_rec.raw_value,
                        unit=switch_rec.unit,
                        meta1=switch_rec.meta1,
                        meta2=switch_rec.meta2,
                        meta3=switch_rec.meta3,
                    )
                ]

    @staticmethod
    def _select_consistent_record(
        source_name: str, records: list[ParamRecord]
    ) -> ParamRecord:
        if len(records) == 1:
            return records[0]
        signature = {(r.raw_value, r.unit) for r in records}
        if len(signature) == 1:
            return records[0]
        raise SourceDataError(
            f"Param.dat contains conflicting duplicate values for {source_name}"
        )

    @staticmethod
    def _heating_switch_is_on(source_name: str, raw_value: Decimal | str) -> bool:
        try:
            value = (
                raw_value
                if isinstance(raw_value, Decimal)
                else Decimal(str(raw_value).strip())
            )
        except (InvalidOperation, ValueError) as exc:
            raise SourceDataError(
                f"Invalid hot-runner switch value {raw_value!r} for {source_name}"
            ) from exc
        return value != 0


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
