from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any, Mapping

from .errors import SourceDataError
from .parsers import ParamRecord


class JupiterXmlParser:
    """Parse Haitian Jupiter TwoShot XML mold data into InjectFlow canonical records.

    The controller XML is normalized into ``Jupiter.*`` names so the existing
    DataResolver can consume the family without learning XML internals.

    308B/309 share the same process geometry.  The selected InjectFlow machine
    is authoritative; ``HMI_Data/MaschinenNR.`` is metadata only and is not used
    to choose machine-dependent conversions.
    """

    PREFIX = "Jupiter."
    MICROSECONDS_PER_SECOND = Decimal("1000000")
    PI = Decimal("3.1415926535897932384626433832795028841971693993751")

    # Template maxima.  For open/injection/hold, the controller count includes
    # the fixed End profile point.  Mould release is separate from open stages.
    MAX_MOLD_CLOSE_STAGES = 3
    MAX_MOLD_OPEN_STAGES = 5
    MAX_INJECTION_STAGES = 4
    MAX_HOLD_STAGES = 4
    MAX_CHARGE_STAGES = 1
    MAX_BARREL_ZONES = 5
    MAX_HRS_ZONES = 54
    MAX_CORES = 2
    MAX_VALVE_GATE_RAW = 48
    MAX_VALVE_GATE_ACTIVE = 9

    # Verified fallback constants from the official 308B/309 machine-data bases.
    # Production runs receive the same values from Data.xlsx/MachineConstants;
    # these fallbacks keep the parser deterministic in isolated unit tests.
    DEFAULT_MACHINE_CONSTANTS: dict[str, dict[str, Any]] = {
        "308B": {
            "MAX_CLAMP_TONS": Decimal("1080"),
            "MAX_CLAMP_PRESSURE_BAR": Decimal("238"),
            "MAX_MOLD_RELEASE_PRESSURE_BAR": Decimal("10"),
            "MOLD_CLOSE_MAX_SPEED_INTERNAL": Decimal("1083"),
            "MOLD_OPEN_MAX_SPEED_INTERNAL": Decimal("1090"),
            "CORE_MAX_SPEED_INTERNAL": Decimal("263.2"),
            "ROTARY_FAST_PRESSURE_MAX_BAR": Decimal("130"),
            "U1_SCREW_DIAMETER_MM": Decimal("70"),
            "U1_SCREW_STROKE_MM": Decimal("322"),
            "U1_SCREW_VOLUME_CM3": Decimal("1239.2013"),
            "U1_CYLINDER_COUNT": Decimal("1"),
            "U1_CYLINDER_DIAMETER_MM": Decimal("220"),
            "U1_PISTON_ROD_DIAMETER_MM": Decimal("190"),
            "U1_HMI_MAX_SPEED_FWD": Decimal("115"),
            "U1_HMI_MAX_SPEED_BWD": Decimal("150"),
            "U1_MAX_RPM": Decimal("247"),
            "U1_MAX_ROTATION_PLAST": Decimal("90.53023"),
            "U1_INJECTION_SPEED_TRANSFORM": "system.hmi.TrnsInjVolSpdRel",
            "U1_ROTATION_TRANSFORM": "system.hmi.TrnsRotationRelMax",
            "U2_SCREW_DIAMETER_MM": Decimal("50"),
            "U2_SCREW_STROKE_MM": Decimal("210"),
            "U2_SCREW_VOLUME_CM3": Decimal("412.33405"),
            "U2_CYLINDER_COUNT": Decimal("1"),
            "U2_CYLINDER_DIAMETER_MM": Decimal("150"),
            "U2_PISTON_ROD_DIAMETER_MM": Decimal("120"),
            "U2_HMI_MAX_SPEED_FWD": Decimal("118"),
            "U2_HMI_MAX_SPEED_BWD": Decimal("150"),
            "U2_MAX_RPM": Decimal("220"),
            "U2_MAX_ROTATION_PLAST": Decimal("57.595867"),
            "U2_INJECTION_SPEED_TRANSFORM": "system.hmi.TrnsInjVolSpdRel2",
            "U2_ROTATION_TRANSFORM": "system.hmi.TrnsRotationRelMax2",
        },
        "309": {
            "MAX_CLAMP_TONS": Decimal("1080"),
            "MAX_CLAMP_PRESSURE_BAR": Decimal("238"),
            "MAX_MOLD_RELEASE_PRESSURE_BAR": Decimal("10"),
            "MOLD_CLOSE_MAX_SPEED_INTERNAL": Decimal("1083"),
            "MOLD_OPEN_MAX_SPEED_INTERNAL": Decimal("1090"),
            "CORE_MAX_SPEED_INTERNAL": Decimal("263.2"),
            "ROTARY_FAST_PRESSURE_MAX_BAR": Decimal("130"),
            "U1_SCREW_DIAMETER_MM": Decimal("70"),
            "U1_SCREW_STROKE_MM": Decimal("322"),
            "U1_SCREW_VOLUME_CM3": Decimal("1239.2013"),
            "U1_CYLINDER_COUNT": Decimal("1"),
            "U1_CYLINDER_DIAMETER_MM": Decimal("220"),
            "U1_PISTON_ROD_DIAMETER_MM": Decimal("190"),
            "U1_HMI_MAX_SPEED_FWD": Decimal("115"),
            "U1_HMI_MAX_SPEED_BWD": Decimal("150"),
            "U1_MAX_RPM": Decimal("247"),
            "U1_MAX_ROTATION_PLAST": Decimal("90.53023"),
            "U1_INJECTION_SPEED_TRANSFORM": "system.hmi.TrnsInjVolSpdSpeed",
            "U1_ROTATION_TRANSFORM": "system.hmi.TrnsRotationRPM",
            "U2_SCREW_DIAMETER_MM": Decimal("50"),
            "U2_SCREW_STROKE_MM": Decimal("210"),
            "U2_SCREW_VOLUME_CM3": Decimal("412.33405"),
            "U2_CYLINDER_COUNT": Decimal("1"),
            "U2_CYLINDER_DIAMETER_MM": Decimal("150"),
            "U2_PISTON_ROD_DIAMETER_MM": Decimal("120"),
            "U2_HMI_MAX_SPEED_FWD": Decimal("118"),
            "U2_HMI_MAX_SPEED_BWD": Decimal("150"),
            "U2_MAX_RPM": Decimal("220"),
            "U2_MAX_ROTATION_PLAST": Decimal("57.595867"),
            "U2_INJECTION_SPEED_TRANSFORM": "system.hmi.TrnsInjVolSpdSpeed2",
            "U2_ROTATION_TRANSFORM": "system.hmi.TrnsRotationRPM2",
        },
    }

    _MOLD_RE = re.compile(r"(?<!\d)(?:I[-_ ]?)?(\d{3,6})(?!\d)", re.IGNORECASE)
    _HRS_USED_RE = re.compile(r"^HeatingMold1\.sv_ZoneRetain(?P<zone>\d+)\.bUsed$")

    def __init__(
        self,
        *,
        strict_template_limits: bool = True,
        machine: str | None = None,
        config: Mapping[str, Any] | None = None,
        machine_constants: Mapping[str, Mapping[str, Any]] | None = None,
    ):
        self.strict_template_limits = bool(strict_template_limits)
        self.selected_machine = str(machine).strip().upper() if machine else None
        self.config = dict(config or {})
        self.machine_constants = {
            str(machine_name).strip().upper(): dict(values)
            for machine_name, values in (machine_constants or {}).items()
        }
        self.process_warnings: list[str] = []
        self.raw_values: dict[str, str] = {}
        self.selected_profiles: dict[str, str] = {}
        self.active_hrs_zones: tuple[int, ...] = ()
        self.active_valve_gates: tuple[int, ...] = ()
        self.active_cores: tuple[str, ...] = ()
        self.version: str | None = None
        self.machine_number: str | None = None
        self.export_date: str | None = None
        self.comment: str | None = None
        self.mold_number: str | None = None

    def parse(self, path: Path) -> dict[str, list[ParamRecord]]:
        self._reset()
        source = Path(path)
        if not source.is_file():
            raise SourceDataError(f"Jupiter XML file was not found: {source}")

        try:
            tree = ET.parse(source)
        except ET.ParseError as exc:
            raise SourceDataError(f"Invalid Jupiter XML: {exc}") from exc
        except OSError as exc:
            raise SourceDataError(f"Cannot read Jupiter XML: {source}: {exc}") from exc

        root = tree.getroot()
        if root.tag != "HMI_Data":
            raise SourceDataError(
                f"Unexpected Jupiter XML root {root.tag!r}; expected 'HMI_Data'"
            )

        self.version = root.attrib.get("Version")
        self.machine_number = root.attrib.get("MaschinenNR.")
        self.export_date = root.attrib.get("Date")
        comment_node = root.find("Comment")
        if comment_node is not None:
            self.comment = comment_node.attrib.get("Text")
        if self.comment:
            match = self._MOLD_RE.search(self.comment)
            if match:
                self.mold_number = match.group(1)

        groups = root.findall("VarGroup")
        mold_group = next((g for g in groups if g.attrib.get("Name") == "VG_MoldData"), None)
        if mold_group is None:
            raise SourceDataError("Jupiter XML does not contain VarGroup 'VG_MoldData'")

        for variable in mold_group.findall("Variable"):
            name = variable.attrib.get("Name", "").strip()
            if not name:
                continue
            value = variable.findtext("Value")
            if value is None:
                value = ""
            if name in self.raw_values and self.raw_values[name] != value:
                raise SourceDataError(
                    f"Jupiter XML contains conflicting duplicate values for {name}"
                )
            self.raw_values[name] = value

        if not self.raw_values:
            raise SourceDataError("Jupiter XML contains no mold-data variables")

        result: dict[str, list[ParamRecord]] = {}
        self._normalize_mold_close(result)
        self._normalize_mold_open(result)
        self._normalize_injection(result, 1)
        self._normalize_injection(result, 2)
        self._normalize_hold(result, 1)
        self._normalize_hold(result, 2)
        self._normalize_charge(result, 1)
        self._normalize_charge(result, 2)
        self._normalize_hrs(result)
        self._normalize_barrel(result, 1)
        self._normalize_barrel(result, 2)
        self._normalize_rotary(result)
        self._normalize_cores(result)
        self._normalize_valve_gates(result)
        return result

    def _reset(self) -> None:
        self.process_warnings = []
        self.raw_values = {}
        self.selected_profiles = {}
        self.active_hrs_zones = ()
        self.active_valve_gates = ()
        self.active_cores = ()
        self.version = None
        self.machine_number = None
        self.export_date = None
        self.comment = None
        self.mold_number = None

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def _emit(
        self,
        result: dict[str, list[ParamRecord]],
        name: str,
        value: Decimal | str | int | float | bool,
        *,
        unit: str = "",
        raw_source: str = "",
    ) -> None:
        key = name if name.startswith(self.PREFIX) else f"{self.PREFIX}{name}"
        normalized: Decimal | str
        if isinstance(value, bool):
            normalized = Decimal(1 if value else 0)
        elif isinstance(value, Decimal):
            normalized = value
        elif isinstance(value, int):
            normalized = Decimal(value)
        elif isinstance(value, float):
            normalized = Decimal(str(value))
        else:
            normalized = str(value)
        result[key] = [
            ParamRecord(
                key=key,
                raw_value=normalized,
                unit=unit,
                meta1="JUPITER_XML",
                meta2=raw_source,
                meta3="",
            )
        ]

    def _raw(self, name: str, default: str | None = None) -> str | None:
        return self.raw_values.get(name, default)

    def _decimal(self, name: str, *, default: Decimal | None = None) -> Decimal:
        raw = self._raw(name)
        if raw is None or str(raw).strip() == "":
            if default is not None:
                return default
            raise SourceDataError(f"Jupiter XML source key not found: {name}")
        try:
            value = Decimal(str(raw).strip())
            if not value.is_finite():
                raise ValueError("non-finite numeric value")
            return value
        except (InvalidOperation, ValueError) as exc:
            raise SourceDataError(f"Invalid numeric value {raw!r} for {name}") from exc

    def _int(self, name: str, *, default: int | None = None) -> int:
        raw = self._raw(name)
        if raw is None or str(raw).strip() == "":
            if default is not None:
                return int(default)
            raise SourceDataError(f"Jupiter XML source key not found: {name}")
        try:
            value = Decimal(str(raw).strip())
            if not value.is_finite() or value != value.to_integral_value():
                raise ValueError("expected a finite integer")
            return int(value)
        except (InvalidOperation, ValueError, OverflowError) as exc:
            raise SourceDataError(f"Invalid integer value {raw!r} for {name}") from exc

    def _bool(self, name: str, *, default: bool | None = None) -> bool:
        raw = self._raw(name)
        if raw is None:
            if default is not None:
                return bool(default)
            raise SourceDataError(f"Jupiter XML source key not found: {name}")
        text = str(raw).strip().lower()
        if text in {"true", "1", "on", "yes"}:
            return True
        if text in {"false", "0", "off", "no"}:
            return False
        raise SourceDataError(f"Invalid boolean value {raw!r} for {name}")

    def _seconds(self, name: str, *, default: Decimal | None = None) -> Decimal:
        return self._decimal(name, default=default) / self.MICROSECONDS_PER_SECOND

    def _warn_once(self, message: str) -> None:
        if message not in self.process_warnings:
            self.process_warnings.append(message)

    def _check_limit(self, label: str, active: int, maximum: int) -> None:
        if active <= maximum:
            return
        message = (
            f"{label}: la receta XML usa {active} etapas/zonas y la plantilla "
            f"Jupiter admite maximo {maximum}."
        )
        if self.strict_template_limits:
            raise SourceDataError(message)
        self._warn_once(message)

    def _profile_value(
        self,
        root: str,
        point: int,
        field: str,
        *,
        default: Decimal = Decimal(0),
    ) -> Decimal:
        return self._decimal(
            f"{root}.Profile.Points[{point}].{field}", default=default
        )

    def _profile_endpoint(self, root: str, point: int) -> Decimal:
        """Return the destination/To value for profile point ``point``."""
        return self._profile_value(root, point + 1, "rStartPos")

    def _cfg_decimal(self, name: str, default: Decimal) -> Decimal:
        raw = self.config.get(name, default)
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError) as exc:
            raise SourceDataError(f"Invalid Jupiter configuration {name}={raw!r}") from exc
        if not value.is_finite() or value == 0:
            raise SourceDataError(f"Invalid Jupiter configuration {name}={raw!r}")
        return value

    def _machine_values(self) -> Mapping[str, Any]:
        if not self.selected_machine:
            return {}
        if self.selected_machine in self.machine_constants:
            return self.machine_constants[self.selected_machine]
        return self.DEFAULT_MACHINE_CONSTANTS.get(self.selected_machine, {})

    def _machine_raw(self, key: str, default: Any = None) -> Any:
        values = self._machine_values()
        if key in values:
            return values[key]
        if self.selected_machine in self.DEFAULT_MACHINE_CONSTANTS:
            defaults = self.DEFAULT_MACHINE_CONSTANTS[self.selected_machine]
            if key in defaults:
                return defaults[key]
        return default

    def _machine_decimal(self, key: str, default: Decimal | None = None) -> Decimal:
        raw = self._machine_raw(key, default)
        if raw is None:
            machine = self.selected_machine or "<sin maquina>"
            raise SourceDataError(
                f"Missing Jupiter machine constant {key} for {machine}."
            )
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError) as exc:
            raise SourceDataError(
                f"Invalid Jupiter machine constant {key}={raw!r} for {self.selected_machine}."
            ) from exc
        if not value.is_finite():
            raise SourceDataError(
                f"Invalid Jupiter machine constant {key}={raw!r} for {self.selected_machine}."
            )
        return value

    def _machine_text(self, key: str, default: str = "") -> str:
        raw = self._machine_raw(key, default)
        return str(raw).strip() if raw is not None else ""

    def _require_selected_machine(self) -> str:
        if not self.selected_machine:
            raise SourceDataError(
                "Jupiter machine-dependent conversion requires the selected machine (308B or 309)."
            )
        if self.selected_machine not in self.DEFAULT_MACHINE_CONSTANTS and self.selected_machine not in self.machine_constants:
            raise SourceDataError(
                f"No Jupiter machine constants are configured for {self.selected_machine}."
            )
        return self.selected_machine

    def _screw_diameter_mm(self, unit_no: int) -> Decimal:
        if self.selected_machine:
            return self._machine_decimal(f"U{unit_no}_SCREW_DIAMETER_MM")
        if unit_no == 1:
            return self._cfg_decimal("JUPITER_U1_SCREW_DIAMETER_MM", Decimal("70"))
        if unit_no == 2:
            return self._cfg_decimal("JUPITER_U2_SCREW_DIAMETER_MM", Decimal("50"))
        raise SourceDataError(f"Unsupported Jupiter injection unit: {unit_no}")

    def _volume_per_stroke(self, unit_no: int) -> Decimal:
        if self.selected_machine:
            volume = self._machine_decimal(f"U{unit_no}_SCREW_VOLUME_CM3")
            stroke = self._machine_decimal(f"U{unit_no}_SCREW_STROKE_MM")
            if stroke == 0:
                raise SourceDataError(f"Jupiter U{unit_no} screw stroke cannot be zero.")
            return volume / stroke
        diameter = self._screw_diameter_mm(unit_no)
        return self.PI * diameter * diameter / Decimal(4) / Decimal(1000)

    def _volume_to_mm(self, unit_no: int, value: Decimal) -> Decimal:
        return value / self._volume_per_stroke(unit_no)

    def _pressure_area_ratio(self, unit_no: int) -> Decimal:
        if self.selected_machine:
            count = self._machine_decimal(f"U{unit_no}_CYLINDER_COUNT")
            cylinder = self._machine_decimal(f"U{unit_no}_CYLINDER_DIAMETER_MM")
            rod = self._machine_decimal(f"U{unit_no}_PISTON_ROD_DIAMETER_MM")
            screw = self._machine_decimal(f"U{unit_no}_SCREW_DIAMETER_MM")
            if screw == 0:
                raise SourceDataError(f"Jupiter U{unit_no} screw diameter cannot be zero.")
            return count * (cylinder * cylinder - rod * rod) / (screw * screw)
        if unit_no == 1:
            return self._cfg_decimal(
                "JUPITER_U1_INJECTION_PRESSURE_DIVISOR", Decimal("2.510204081632653")
            )
        if unit_no == 2:
            return self._cfg_decimal(
                "JUPITER_U2_INJECTION_PRESSURE_DIVISOR", Decimal("3.24")
            )
        raise SourceDataError(f"Unsupported Jupiter injection unit: {unit_no}")

    def _injection_pressure_to_bar(self, unit_no: int, value: Decimal) -> Decimal:
        return value / self._pressure_area_ratio(unit_no)

    def _injection_speed_display(self, unit_no: int, value: Decimal) -> Decimal:
        linear_speed = value / self._volume_per_stroke(unit_no)
        if not self.selected_machine:
            return linear_speed
        transform = self._machine_text(f"U{unit_no}_INJECTION_SPEED_TRANSFORM")
        if "TrnsInjVolSpdRel" in transform:
            maximum = self._machine_decimal(f"U{unit_no}_HMI_MAX_SPEED_FWD")
            if maximum == 0:
                raise SourceDataError(f"Jupiter U{unit_no} HMI max forward speed cannot be zero.")
            return linear_speed / maximum * Decimal(100)
        if "TrnsInjVolSpdSpeed" in transform:
            return linear_speed
        raise SourceDataError(
            f"Unsupported Jupiter U{unit_no} injection-speed transform {transform!r} "
            f"for {self.selected_machine}."
        )

    def _decomp_speed_display(self, unit_no: int, value: Decimal) -> Decimal:
        if not self.selected_machine:
            return value
        transform = self._machine_text(f"U{unit_no}_INJECTION_SPEED_TRANSFORM")
        if "TrnsInjVolSpdRel" in transform:
            maximum = self._machine_decimal(f"U{unit_no}_HMI_MAX_SPEED_BWD")
            if maximum == 0:
                raise SourceDataError(f"Jupiter U{unit_no} HMI max backward speed cannot be zero.")
            return value / maximum * Decimal(100)
        if "TrnsInjVolSpdSpeed" in transform:
            return value
        raise SourceDataError(
            f"Unsupported Jupiter U{unit_no} decompression-speed transform {transform!r} "
            f"for {self.selected_machine}."
        )

    def _relative_speed(self, value: Decimal, max_key: str, *, legacy_divisor: str) -> Decimal:
        if self.selected_machine:
            maximum = self._machine_decimal(max_key)
            if maximum == 0:
                raise SourceDataError(f"Jupiter machine constant {max_key} cannot be zero.")
            return value / maximum * Decimal(100)
        legacy_defaults = {
            "JUPITER_CLOSE_VELOCITY_DIVISOR": Decimal("10.83"),
            "JUPITER_OPEN_VELOCITY_DIVISOR": Decimal("10.9"),
            "JUPITER_CORE_VELOCITY_DIVISOR": Decimal("2.632"),
        }
        divisor = self._cfg_decimal(legacy_divisor, legacy_defaults[legacy_divisor])
        return value / divisor

    def _close_velocity_percent(self, value: Decimal) -> Decimal:
        return self._relative_speed(
            value,
            "MOLD_CLOSE_MAX_SPEED_INTERNAL",
            legacy_divisor="JUPITER_CLOSE_VELOCITY_DIVISOR",
        )

    def _open_velocity_percent(self, value: Decimal) -> Decimal:
        return self._relative_speed(
            value,
            "MOLD_OPEN_MAX_SPEED_INTERNAL",
            legacy_divisor="JUPITER_OPEN_VELOCITY_DIVISOR",
        )

    def _core_velocity_percent(self, value: Decimal) -> Decimal:
        return self._relative_speed(
            value,
            "CORE_MAX_SPEED_INTERNAL",
            legacy_divisor="JUPITER_CORE_VELOCITY_DIVISOR",
        )

    def _rotation_display(self, unit_no: int, value: Decimal) -> Decimal:
        if value == 0:
            return Decimal(0)
        self._require_selected_machine()
        transform = self._machine_text(f"U{unit_no}_ROTATION_TRANSFORM")
        maximum_rotation = self._machine_decimal(f"U{unit_no}_MAX_ROTATION_PLAST")
        if maximum_rotation == 0:
            raise SourceDataError(f"Jupiter U{unit_no} max plasticizing rotation cannot be zero.")
        if "TrnsRotationRelMax" in transform:
            return value / maximum_rotation * Decimal(100)
        if "TrnsRotationRPM" in transform:
            maximum_rpm = self._machine_decimal(f"U{unit_no}_MAX_RPM")
            return value / maximum_rotation * maximum_rpm
        raise SourceDataError(
            f"Unsupported Jupiter U{unit_no} rotation transform {transform!r} "
            f"for {self.selected_machine}."
        )

    def _clamp_tons(self, set_pressure_bar: Decimal) -> Decimal:
        self._require_selected_machine()
        max_pressure = self._machine_decimal("MAX_CLAMP_PRESSURE_BAR")
        max_tons = self._machine_decimal("MAX_CLAMP_TONS")
        if max_pressure == 0:
            raise SourceDataError("Jupiter MAX_CLAMP_PRESSURE_BAR cannot be zero.")
        return set_pressure_bar / max_pressure * max_tons

    # ------------------------------------------------------------------
    # Clamp close / open
    # ------------------------------------------------------------------
    def _normalize_mold_close(self, result: dict[str, list[ParamRecord]]) -> None:
        use_intelligence = self._bool(
            "Mold1.sv_MoldCloseIntelligenceSet.bUseIntelligence", default=False
        )
        if use_intelligence:
            root = "Mold1.sv_MoldFwdProfIntelligenceVis"
            count = self._int(f"{root}.Profile.iNoOfPoints", default=0)
            normal_count = max(0, count - 1)
            indices = list(range(1, count + 1))
            protect_index = indices[-1] if indices else None
        else:
            root = "Mold1.sv_MoldFwdProfVisSrc"
            count = self._int(f"{root}.Profile.iNoOfPoints", default=0)
            # Standard Jupiter close profile is right-aligned in the 20-point
            # array.  The final two active points are Protect and high pressure.
            start = max(1, 20 - count)
            indices = list(range(start, start + count))
            normal_count = max(0, count - 2)
            protect_index = (
                indices[-2]
                if len(indices) >= 2
                else (indices[-1] if indices else None)
            )

        self.selected_profiles["mold_close"] = root
        self._check_limit("Cierre de prensa", normal_count, self.MAX_MOLD_CLOSE_STAGES)
        self._emit(
            result,
            "MoldCloseStages",
            normal_count,
            raw_source=f"{root}.Profile.iNoOfPoints",
        )

        for slot in range(1, self.MAX_MOLD_CLOSE_STAGES + 1):
            if slot <= normal_count and slot <= len(indices):
                point = indices[slot - 1]
                pressure = self._profile_value(root, point, "rPressure")
                velocity = self._close_velocity_percent(
                    self._profile_value(root, point, "rVelocity")
                )
                position = self._profile_endpoint(root, point)
                pressure_src = f"{root}.Profile.Points[{point}].rPressure"
                velocity_src = f"{root}.Profile.Points[{point}].rVelocity"
                position_src = f"{root}.Profile.Points[{point + 1}].rStartPos"
            else:
                pressure = velocity = position = Decimal(0)
                pressure_src = velocity_src = position_src = "inactive"
            self._emit(result, f"MoldCloseStage{slot}Pressure", pressure, unit="bar", raw_source=pressure_src)
            self._emit(result, f"MoldCloseStage{slot}Velocity", velocity, unit="%", raw_source=velocity_src)
            self._emit(result, f"MoldCloseStage{slot}Position", position, unit="mm", raw_source=position_src)

        if protect_index is not None:
            self._emit(
                result,
                "MoldProtectStagePressure",
                self._profile_value(root, protect_index, "rPressure"),
                unit="bar",
                raw_source=f"{root}.Profile.Points[{protect_index}].rPressure",
            )
            self._emit(
                result,
                "MoldProtectStageVelocity",
                self._close_velocity_percent(
                    self._profile_value(root, protect_index, "rVelocity")
                ),
                unit="%",
                raw_source=f"{root}.Profile.Points[{protect_index}].rVelocity",
            )
            self._emit(
                result,
                "MoldProtectStagePosition",
                self._profile_endpoint(root, protect_index),
                unit="mm",
                raw_source=f"{root}.Profile.Points[{protect_index + 1}].rStartPos",
            )
        else:
            for suffix, unit in (("Pressure", "bar"), ("Velocity", "%"), ("Position", "mm")):
                self._emit(result, f"MoldProtectStage{suffix}", Decimal(0), unit=unit, raw_source="inactive")

        if self.selected_machine:
            clamp_pressure_src = "Mold1.sv_rSetClampPres"
            self._emit(
                result,
                "MoldClampTons",
                self._clamp_tons(
                    self._decimal(clamp_pressure_src, default=Decimal(0))
                ),
                unit="ton",
                raw_source=clamp_pressure_src,
            )

        self._emit(
            result,
            "MoldHighPressureVelocity",
            self._decimal("MoldLock1.sv_rHiPressureVelocityVis", default=Decimal(0)),
            unit="%",
            raw_source="MoldLock1.sv_rHiPressureVelocityVis",
        )
        self._emit(
            result,
            "MoldProtectForce",
            self._decimal("Mold1.sv_rMoldProtectForce", default=Decimal(0)),
            unit="ton",
            raw_source="Mold1.sv_rMoldProtectForce",
        )
        self._emit(
            result,
            "MoldProtectionTime",
            self._seconds("Mold1.sv_dMoldProtectTimeSet", default=Decimal(0)),
            unit="s",
            raw_source="Mold1.sv_dMoldProtectTimeSet",
        )

    def _normalize_mold_open(self, result: dict[str, list[ParamRecord]]) -> None:
        use_intelligence = self._bool(
            "Mold1.sv_MoldOpenIntelligenceSet.bUseIntelligence", default=False
        )
        root = (
            "Mold1.sv_MoldBwdProfIntelligenceVis"
            if use_intelligence
            else "Mold1.sv_MoldBwdProfVis"
        )
        self.selected_profiles["mold_open"] = root
        count = self._int(f"{root}.Profile.iNoOfPoints", default=0)
        self._check_limit("Apertura de prensa", count, self.MAX_MOLD_OPEN_STAGES)
        self._emit(result, "MoldOpenStages", count, raw_source=f"{root}.Profile.iNoOfPoints")

        # Mould release is a special row, separate from the 1..4 + End profile.
        mould_pressure = "MoldTieBars1.sv_MoldLockBwdConstVis[5].Pressure.Output.rOutputValue"
        mould_velocity = "MoldTieBars1.sv_MoldLockBwdConstVis[5].Velocity.Output.rOutputValue"
        mould_position = "MoldTieBars1.sv_MoldLockBwdPosition"
        self._emit(result, "MoldOpenMouldPressure", self._decimal(mould_pressure, default=Decimal(0)), unit="bar", raw_source=mould_pressure)
        self._emit(result, "MoldOpenMouldVelocity", self._decimal(mould_velocity, default=Decimal(0)), unit="%", raw_source=mould_velocity)
        self._emit(result, "MoldOpenMouldPosition", self._decimal(mould_position, default=Decimal(0)), unit="mm", raw_source=mould_position)

        # ``count`` includes fixed End.  Therefore only points 1..count-1 are
        # numbered stages, and the destination/To comes from the next point.
        numbered_slots = self.MAX_MOLD_OPEN_STAGES - 1
        for slot in range(1, numbered_slots + 1):
            active = count > 0 and slot < count
            if active:
                pressure = self._profile_value(root, slot, "rPressure")
                velocity = self._open_velocity_percent(
                    self._profile_value(root, slot, "rVelocity")
                )
                position = self._profile_endpoint(root, slot)
                pressure_src = f"{root}.Profile.Points[{slot}].rPressure"
                velocity_src = f"{root}.Profile.Points[{slot}].rVelocity"
                position_src = f"{root}.Profile.Points[{slot + 1}].rStartPos"
            else:
                pressure = velocity = position = Decimal(0)
                pressure_src = velocity_src = position_src = "inactive"
            self._emit(result, f"MoldOpenStage{slot}Pressure", pressure, unit="bar", raw_source=pressure_src)
            self._emit(result, f"MoldOpenStage{slot}Velocity", velocity, unit="%", raw_source=velocity_src)
            self._emit(result, f"MoldOpenStage{slot}Position", position, unit="mm", raw_source=position_src)

        if count > 0:
            end_point = count
            self._emit(result, "MoldOpenEndPressure", self._profile_value(root, end_point, "rPressure"), unit="bar", raw_source=f"{root}.Profile.Points[{end_point}].rPressure")
            self._emit(result, "MoldOpenEndVelocity", self._open_velocity_percent(self._profile_value(root, end_point, "rVelocity")), unit="%", raw_source=f"{root}.Profile.Points[{end_point}].rVelocity")
            self._emit(result, "MoldOpenEndPosition", self._profile_endpoint(root, end_point), unit="mm", raw_source=f"{root}.Profile.Points[{end_point + 1}].rStartPos")
        else:
            self._emit(result, "MoldOpenEndPressure", Decimal(0), unit="bar", raw_source="inactive")
            self._emit(result, "MoldOpenEndVelocity", Decimal(0), unit="%", raw_source="inactive")
            self._emit(result, "MoldOpenEndPosition", Decimal(0), unit="mm", raw_source="inactive")

        if self.selected_machine:
            self._emit(
                result,
                "MoldOpenMaxReleasePressure",
                self._machine_decimal("MAX_MOLD_RELEASE_PRESSURE_BAR"),
                unit="bar",
                raw_source="machine_constant:MAX_MOLD_RELEASE_PRESSURE_BAR",
            )

        direct = {
            "MoldOpenUseFastOpen": ("Mold1.sv_UseMoldOpenFast", "", "bool"),
            "MoldOpenFastRelease": ("MoldLock1.sv_UseFastPresRelease", "", "bool"),
            "MoldOpenUseBufferRelease": ("MoldLock1.sv_bUseBufferRelease", "", "bool"),
        }
        for key, (src, unit, kind) in direct.items():
            value: Any = self._bool(src, default=False) if kind == "bool" else self._decimal(src, default=Decimal(0))
            self._emit(result, key, value, unit=unit, raw_source=src)

    # ------------------------------------------------------------------
    # Injection / hold / plasticizing
    # ------------------------------------------------------------------
    def _normalize_injection(self, result: dict[str, list[ParamRecord]], unit_no: int) -> None:
        root = f"Injection{unit_no}.sv_InjectProfVis"
        self.selected_profiles[f"injection{unit_no}"] = root
        count = self._int(f"{root}.Profile.iNoOfPoints", default=0)
        self._check_limit(f"Inyeccion {unit_no}", count, self.MAX_INJECTION_STAGES)
        self._emit(result, f"Injection{unit_no}Stages", count, raw_source=f"{root}.Profile.iNoOfPoints")

        numbered_slots = self.MAX_INJECTION_STAGES - 1
        for slot in range(1, numbered_slots + 1):
            active = count > 0 and slot < count
            if active:
                pressure = self._injection_pressure_to_bar(
                    unit_no, self._profile_value(root, slot, "rPressure")
                )
                velocity = self._injection_speed_display(
                    unit_no, self._profile_value(root, slot, "rVelocity")
                )
                position = self._volume_to_mm(
                    unit_no, self._profile_endpoint(root, slot)
                )
                pressure_src = f"{root}.Profile.Points[{slot}].rPressure"
                velocity_src = f"{root}.Profile.Points[{slot}].rVelocity"
                position_src = f"{root}.Profile.Points[{slot + 1}].rStartPos"
            else:
                pressure = velocity = position = Decimal(0)
                pressure_src = velocity_src = position_src = "inactive"
            self._emit(result, f"Injection{unit_no}Stage{slot}Pressure", pressure, unit="bar", raw_source=pressure_src)
            self._emit(result, f"Injection{unit_no}Stage{slot}Velocity", velocity, unit="mm/s", raw_source=velocity_src)
            self._emit(result, f"Injection{unit_no}Stage{slot}Position", position, unit="mm", raw_source=position_src)

        if count > 0:
            end_point = count
            self._emit(result, f"Injection{unit_no}EndPressure", self._injection_pressure_to_bar(unit_no, self._profile_value(root, end_point, "rPressure")), unit="bar", raw_source=f"{root}.Profile.Points[{end_point}].rPressure")
            self._emit(result, f"Injection{unit_no}EndVelocity", self._injection_speed_display(unit_no, self._profile_value(root, end_point, "rVelocity")), unit="mm/s", raw_source=f"{root}.Profile.Points[{end_point}].rVelocity")
        else:
            self._emit(result, f"Injection{unit_no}EndPressure", Decimal(0), unit="bar", raw_source="inactive")
            self._emit(result, f"Injection{unit_no}EndVelocity", Decimal(0), unit="mm/s", raw_source="inactive")

        base = f"Injection{unit_no}"
        cutoff = f"{base}.sv_CutOffParams"
        # Transfer conditions are independent switches. Controller exports can
        # retain stale threshold values while a condition is disabled, so emit
        # the switches explicitly and let the plan blank inactive thresholds.
        self._emit(result, f"Injection{unit_no}UsePosition", self._bool(f"{cutoff}.bUsePosition", default=False), raw_source=f"{cutoff}.bUsePosition")
        self._emit(result, f"Injection{unit_no}UseTimer", self._bool(f"{cutoff}.bUseTimer", default=False), raw_source=f"{cutoff}.bUseTimer")
        self._emit(result, f"Injection{unit_no}UsePressure", self._bool(f"{cutoff}.bUseInjectPressure", default=False), raw_source=f"{cutoff}.bUseInjectPressure")
        position_src = f"{cutoff}.rPositionThreshold"
        self._emit(result, f"Injection{unit_no}ScrewPosition", self._volume_to_mm(unit_no, self._decimal(position_src, default=Decimal(0))), unit="mm", raw_source=position_src)
        self._emit(result, f"Injection{unit_no}TimeSet", self._seconds(f"{cutoff}.dTimeThreshold", default=Decimal(0)), unit="s", raw_source=f"{cutoff}.dTimeThreshold")
        self._emit(result, f"Injection{unit_no}PressureSet", self._injection_pressure_to_bar(unit_no, self._decimal(f"{cutoff}.rInjectPressureThreshold", default=Decimal(0))), unit="bar", raw_source=f"{cutoff}.rInjectPressureThreshold")
        self._emit(result, f"Injection{unit_no}MaxTime", self._seconds(f"{base}.sv_InjectTimesSet.dMaxMoveTime", default=Decimal(0)), unit="s", raw_source=f"{base}.sv_InjectTimesSet.dMaxMoveTime")

    def _normalize_hold(self, result: dict[str, list[ParamRecord]], unit_no: int) -> None:
        root = f"Injection{unit_no}.sv_HoldProfVis"
        self.selected_profiles[f"hold{unit_no}"] = root
        count = self._int(f"{root}.Profile.iNoOfPoints", default=0)
        self._check_limit(f"Sostenimiento {unit_no}", count, self.MAX_HOLD_STAGES)
        self._emit(result, f"Holding{unit_no}Stages", count, raw_source=f"{root}.Profile.iNoOfPoints")

        numbered_slots = self.MAX_HOLD_STAGES - 1
        for slot in range(1, numbered_slots + 1):
            active = count > 0 and slot < count
            if active:
                pressure = self._injection_pressure_to_bar(unit_no, self._profile_value(root, slot, "rPressure"))
                velocity = self._injection_speed_display(unit_no, self._profile_value(root, slot, "rVelocity"))
                stage_time = self._profile_endpoint(root, slot)
                psrc = f"{root}.Profile.Points[{slot}].rPressure"
                vsrc = f"{root}.Profile.Points[{slot}].rVelocity"
                tsrc = f"{root}.Profile.Points[{slot + 1}].rStartPos"
            else:
                pressure = velocity = stage_time = Decimal(0)
                psrc = vsrc = tsrc = "inactive"
            self._emit(result, f"Hold{unit_no}Stage{slot}Pressure", pressure, unit="bar", raw_source=psrc)
            self._emit(result, f"Hold{unit_no}Stage{slot}Velocity", velocity, unit="mm/s", raw_source=vsrc)
            self._emit(result, f"Hold{unit_no}Stage{slot}Time", stage_time, unit="s", raw_source=tsrc)

        if count > 0:
            end_point = count
            self._emit(result, f"Hold{unit_no}EndPressure", self._injection_pressure_to_bar(unit_no, self._profile_value(root, end_point, "rPressure")), unit="bar", raw_source=f"{root}.Profile.Points[{end_point}].rPressure")
            self._emit(result, f"Hold{unit_no}EndVelocity", self._injection_speed_display(unit_no, self._profile_value(root, end_point, "rVelocity")), unit="mm/s", raw_source=f"{root}.Profile.Points[{end_point}].rVelocity")
            self._emit(result, f"Hold{unit_no}EndTime", self._profile_endpoint(root, end_point), unit="s", raw_source=f"{root}.Profile.Points[{end_point + 1}].rStartPos")
        else:
            self._emit(result, f"Hold{unit_no}EndPressure", Decimal(0), unit="bar", raw_source="inactive")
            self._emit(result, f"Hold{unit_no}EndVelocity", Decimal(0), unit="mm/s", raw_source="inactive")
            self._emit(result, f"Hold{unit_no}EndTime", Decimal(0), unit="s", raw_source="inactive")

    def _normalize_charge(self, result: dict[str, list[ParamRecord]], unit_no: int) -> None:
        base = f"Injection{unit_no}"
        root = f"{base}.sv_PlastProfVis"
        self.selected_profiles[f"charge{unit_no}"] = root
        count = self._int(f"{root}.Profile.iNoOfPoints", default=0)
        self._check_limit(f"Carga {unit_no}", count, self.MAX_CHARGE_STAGES)
        first = 1 if count > 0 else 0
        end_point = count + 1 if count > 0 else 1

        def pv(field: str) -> Decimal:
            return self._profile_value(root, first, field) if first else Decimal(0)

        rotation = pv("rRotation")
        self._emit(result, f"Charge{unit_no}EndBackPressure", pv("rBackPressure"), unit="bar", raw_source=f"{root}.Profile.Points[{first}].rBackPressure" if first else "inactive")
        self._emit(result, f"Charge{unit_no}EndRPM", self._rotation_display(unit_no, rotation), unit="rpm", raw_source=f"{root}.Profile.Points[{first}].rRotation" if first else "inactive")
        self._emit(result, f"Charge{unit_no}EndPosition", self._volume_to_mm(unit_no, self._profile_value(root, end_point, "rStartPos")) if first else Decimal(0), unit="mm", raw_source=f"{root}.Profile.Points[{end_point}].rStartPos" if first else "inactive")
        self._emit(result, f"Charge{unit_no}Pressure", pv("rPressure"), unit="bar", raw_source=f"{root}.Profile.Points[{first}].rPressure" if first else "inactive")
        self._emit(result, f"Charge{unit_no}Delay", self._seconds(f"{base}.sv_PlastTimesSet.dSetDelayTime", default=Decimal(0)), unit="s", raw_source=f"{base}.sv_PlastTimesSet.dSetDelayTime")
        self._emit(result, f"Charge{unit_no}MaxPlasticizeTime", self._seconds(f"{base}.sv_PlastTimesSet.dMaxMoveTime", default=Decimal(0)), unit="s", raw_source=f"{base}.sv_PlastTimesSet.dMaxMoveTime")

        before = f"{base}.sv_DecompBefPlastSettings"
        after = f"{base}.sv_DecompAftPlastSettings"
        before_mode = self._int(f"{before}.Mode", default=0)
        after_mode = self._int(f"{after}.Mode", default=0)
        self._emit(result, f"Decomp{unit_no}BeforeMode", before_mode, raw_source=f"{before}.Mode")
        self._emit(result, f"Decomp{unit_no}AfterMode", after_mode, raw_source=f"{after}.Mode")
        self._emit(result, f"Decomp{unit_no}AfterActive", after_mode != 0, raw_source=f"{after}.Mode")
        selected = after if after_mode != 0 else before
        self._emit(result, f"Decomp{unit_no}Pressure", self._decimal(f"{selected}.ConstOutput.Pressure.Output.rOutputValue", default=Decimal(0)), unit="bar", raw_source=f"{selected}.ConstOutput.Pressure.Output.rOutputValue")
        decomp_velocity_src = f"{selected}.ConstOutput.Velocity.Output.rOutputValue"
        self._emit(
            result,
            f"Decomp{unit_no}Velocity",
            self._decomp_speed_display(
                unit_no, self._decimal(decomp_velocity_src, default=Decimal(0))
            ),
            unit="%",
            raw_source=decomp_velocity_src,
        )
        self._emit(result, f"Decomp{unit_no}Position", self._volume_to_mm(unit_no, self._decimal(f"{selected}.rDecompPos", default=Decimal(0))), unit="mm", raw_source=f"{selected}.rDecompPos")
        self._emit(result, f"Decomp{unit_no}Time", self._seconds(f"{selected}.dDecompTime", default=Decimal(0)), unit="s", raw_source=f"{selected}.dDecompTime")

        cooling = f"CoolingTime{unit_no}.sv_dCoolingTime"
        self._emit(result, f"CoolingTime{unit_no}", self._seconds(cooling, default=Decimal(0)), unit="s", raw_source=cooling)

    # ------------------------------------------------------------------
    # Heating
    # ------------------------------------------------------------------
    def _normalize_hrs(self, result: dict[str, list[ParamRecord]]) -> None:
        active_all: list[int] = []
        for name, value in self.raw_values.items():
            match = self._HRS_USED_RE.match(name)
            if match and self._parse_bool_text(value, name):
                active_all.append(int(match.group("zone")))
        active_all = sorted(set(active_all))
        out_of_layout = [z for z in active_all if z > self.MAX_HRS_ZONES]
        if out_of_layout:
            message = (
                "Colada caliente Jupiter: hay zonas activas fuera del limite de la plantilla "
                f"1..{self.MAX_HRS_ZONES}: {out_of_layout}"
            )
            if self.strict_template_limits:
                raise SourceDataError(message)
            self._warn_once(message)
        self.active_hrs_zones = tuple(z for z in active_all if z <= self.MAX_HRS_ZONES)

        for zone in range(1, self.MAX_HRS_ZONES + 1):
            used_key = f"HeatingMold1.sv_ZoneRetain{zone}.bUsed"
            temp_key = f"HeatingMold1.sv_ZoneRetain{zone}.rSetValVis"
            used = self._bool(used_key, default=False)
            temp = self._decimal(temp_key, default=Decimal(0))
            self._emit(result, f"HRSZone{zone}Mode", used, raw_source=used_key)
            self._emit(result, f"HRSZone{zone}Temp", temp, unit="°C", raw_source=temp_key)
        self._emit(result, "HRSTotalZonesText", f"TOTAL: {len(self.active_hrs_zones)} ZONAS", raw_source="derived:bUsed")

    def _normalize_barrel(self, result: dict[str, list[ParamRecord]], unit_no: int) -> None:
        prefix = f"HeatingNozzle{unit_no}.sv_ZoneRetain"
        for zone in range(1, self.MAX_BARREL_ZONES + 1):
            root = f"{prefix}{zone}"
            temp_src = f"{root}.rSetValVis"
            self._emit(result, f"Barrel{unit_no}Zone{zone}Temp", self._decimal(temp_src, default=Decimal(0)), unit="°C", raw_source=temp_src)
            # Both supplied machines use the first five physical barrel zones.
            # ModeVis is not used to infer the physical zone count.
            self._emit(result, f"Barrel{unit_no}Zone{zone}Mode", True, raw_source="fixed:first-five-zones")
        # Barrel tolerances and Cool Prevent Time are template-owned fixed data;
        # intentionally emit no dynamic keys for them.

    # ------------------------------------------------------------------
    # Rotary / cores
    # ------------------------------------------------------------------
    def _normalize_rotary(self, result: dict[str, list[ParamRecord]]) -> None:
        if self.selected_machine:
            self._emit(
                result,
                "RotaryFastPressure",
                self._machine_decimal("ROTARY_FAST_PRESSURE_MAX_BAR"),
                unit="bar",
                raw_source="machine_constant:ROTARY_FAST_PRESSURE_MAX_BAR",
            )
        # Rotary Fast Velocity remains intentionally un-emitted: the real
        # 308B/309 sheets differ and no unique validated recipe source exists.
        direct = {
            "RotaryLockPinInPressure": ("RotaryTable1.sv_ConstPinIn.Pressure.Output.rOutputValue", "bar"),
            "RotaryLockPinInVelocity": ("RotaryTable1.sv_ConstPinIn.Velocity.Output.rOutputValue", "%"),
            "RotaryLockPinIn2Pressure": ("RotaryTable1.sv_ConstPinIn2.Pressure.Output.rOutputValue", "bar"),
            "RotaryLockPinIn2Velocity": ("RotaryTable1.sv_ConstPinIn2.Velocity.Output.rOutputValue", "%"),
            "RotaryLockPinOutPressure": ("RotaryTable1.sv_ConstPinOut.Pressure.Output.rOutputValue", "bar"),
            "RotaryLockPinOutVelocity": ("RotaryTable1.sv_ConstPinOut.Velocity.Output.rOutputValue", "%"),
            "RotaryClampVelocity": ("RotatePlaten1.sv_ConstClamp.Velocity.Output.rOutputValue", "%"),
            "RotaryHoldVelocity": ("RotatePlaten1.sv_ConstHold.Velocity.Output.rOutputValue", "%"),
        }
        for key, (src, target_unit) in direct.items():
            self._emit(result, key, self._decimal(src, default=Decimal(0)), unit=target_unit, raw_source=src)
        for key, src in {
            "RotaryClampTime": "RotatePlaten1.sv_dRotClampTime",
            "RotaryHoldTime": "RotatePlaten1.sv_dRotHoldTime",
        }.items():
            self._emit(result, key, self._seconds(src, default=Decimal(0)), unit="s", raw_source=src)
        src = "RotaryTable1.sv_nRotaryTableMode"
        # Do not manufacture controller state 0 when the field is absent.  The
        # validated HMI map currently defines code 2 -> After Exp.; an absent
        # mode is a missing parameter, not an alternate Rotary state.
        if self._raw(src) is not None:
            self._emit(result, "RotaryTableMode", self._int(src), raw_source=src)

    def _normalize_cores(self, result: dict[str, list[ParamRecord]]) -> None:
        active: list[str] = []
        for letter, core_no in (("A", 1), ("B", 2)):
            root = f"Core{core_no}"
            core_type = self._int(f"{root}.sv_CoreMode.CoreType", default=0)
            is_active = core_type != 0
            if is_active:
                active.append(letter)
            self._emit(result, f"Core{letter}Mode", is_active, raw_source=f"{root}.sv_CoreMode.CoreType")

            # State maps intentionally contain only controller states that have
            # been validated against the Jupiter HMI.  Inactive cores commonly
            # retain zero/default controller codes, but those zeros do not mean
            # a real TYPE/MODE selection.  Do not manufacture a translated state
            # for an inactive physical slot; PlanBuilder clears that slot from
            # Core{X}Mode and the resolver may report the unused fields as absent.
            # Conversely, an active core must expose all four state variables;
            # silently replacing a missing field with zero could turn a missing
            # setting into a real HMI state.
            if is_active:
                control_in_src = f"{root}.sv_CoreMode.CoreControlIn"
                control_out_src = f"{root}.sv_CoreMode.CoreControlOut"
                control_in = self._int(control_in_src)
                control_out = self._int(control_out_src)
                self._emit(result, f"Core{letter}InType", control_in, raw_source=control_in_src)
                self._emit(result, f"Core{letter}OutType", control_out, raw_source=control_out_src)

                in_mode_src = f"CentralCoordination1.sv_CoreData[{core_no}].InMode"
                out_mode_src = f"CentralCoordination1.sv_CoreData[{core_no}].OutMode"
                self._emit(result, f"Core{letter}InMode", self._int(in_mode_src), raw_source=in_mode_src)
                self._emit(result, f"Core{letter}OutMode", self._int(out_mode_src), raw_source=out_mode_src)

            in_pressure_src = f"{root}.sv_CoreOutput.NormalIn.Pressure.Output.rOutputValue"
            in_velocity_src = f"{root}.sv_CoreOutput.NormalIn.Velocity.Output.rOutputValue"
            out_pressure_src = f"{root}.sv_CoreOutput.NormalOut.Pressure.Output.rOutputValue"
            out_velocity_src = f"{root}.sv_CoreOutput.NormalOut.Velocity.Output.rOutputValue"
            self._emit(result, f"Core{letter}InPressure", self._decimal(in_pressure_src, default=Decimal(0)), unit="bar", raw_source=in_pressure_src)
            self._emit(result, f"Core{letter}InVelocity", self._core_velocity_percent(self._decimal(in_velocity_src, default=Decimal(0))), unit="%", raw_source=in_velocity_src)
            self._emit(result, f"Core{letter}OutPressure", self._decimal(out_pressure_src, default=Decimal(0)), unit="bar", raw_source=out_pressure_src)
            self._emit(result, f"Core{letter}OutVelocity", self._core_velocity_percent(self._decimal(out_velocity_src, default=Decimal(0))), unit="%", raw_source=out_velocity_src)

            times = {
                "InDelay": f"{root}.sv_CoreSetTimes.MoveIn.dSetDelayTime",
                "InTime": f"{root}.sv_CoreSetTimes.MoveIn.dSetMoveTime",
                "OutDelay": f"{root}.sv_CoreSetTimes.MoveOut.dSetDelayTime",
                "OutTime": f"{root}.sv_CoreSetTimes.MoveOut.dSetMoveTime",
            }
            for suffix, src in times.items():
                self._emit(result, f"Core{letter}{suffix}", self._seconds(src, default=Decimal(0)), unit="s", raw_source=src)
        self.active_cores = tuple(active)

    # ------------------------------------------------------------------
    # Valve gates / sequencer
    # ------------------------------------------------------------------
    def _normalize_valve_gates(self, result: dict[str, list[ParamRecord]]) -> None:
        active: list[int] = []
        for gate in range(1, self.MAX_VALVE_GATE_RAW + 1):
            root = f"ValveGate1.sv_ValveGateData.ValveGateDataArray[{gate}]"
            used = self._bool(f"{root}.bUsed", default=False)
            if used:
                active.append(gate)

            injection_raw = self._int(f"{root}.injection", default=0)
            open_mode = self._int(f"{root}.OpenMode", default=0)
            close_mode = self._int(f"{root}.CloseMode", default=0)
            if used and injection_raw not in (0, 1):
                raise SourceDataError(
                    f"Jupiter Valve Gate {gate}: unsupported injection code {injection_raw}; expected 0 or 1."
                )
            if used and open_mode not in (0, 1):
                raise SourceDataError(
                    f"Jupiter Valve Gate {gate}: unsupported OpenMode {open_mode}; expected POSITION(0) or TIME(1)."
                )
            if used and close_mode not in (0, 1):
                raise SourceDataError(
                    f"Jupiter Valve Gate {gate}: unsupported CloseMode {close_mode}; expected POSITION(0) or TIME(1)."
                )

            unit_no = 2 if injection_raw == 1 else 1
            pos_suffix = "_Inj2" if injection_raw == 1 else ""
            start_src = f"{root}.rStartPos{pos_suffix}"
            stop_src = f"{root}.rStopPos{pos_suffix}"
            start_raw = self._decimal(start_src, default=self._decimal(f"{root}.rStartPos", default=Decimal(0)))
            stop_raw = self._decimal(stop_src, default=self._decimal(f"{root}.rStopPos", default=Decimal(0)))

            self._emit(result, f"ValveGate{gate}State", used, raw_source=f"{root}.bUsed")
            self._emit(result, f"ValveGate{gate}StartUse", used, raw_source=f"{root}.bUsed")
            self._emit(result, f"ValveGate{gate}StartCon", open_mode, raw_source=f"{root}.OpenMode")
            self._emit(result, f"ValveGate{gate}OnStroke", self._volume_to_mm(unit_no, start_raw), unit="mm", raw_source=start_src)
            self._emit(result, f"ValveGate{gate}StartDelay", self._seconds(f"{root}.dStartDelay", default=Decimal(0)), unit="s", raw_source=f"{root}.dStartDelay")
            self._emit(result, f"ValveGate{gate}StopCon", close_mode, raw_source=f"{root}.CloseMode")
            self._emit(result, f"ValveGate{gate}OffInjectionStroke", self._volume_to_mm(unit_no, stop_raw), unit="mm", raw_source=stop_src)
            self._emit(result, f"ValveGate{gate}StopDelay", self._seconds(f"{root}.dStopDelay", default=Decimal(0)), unit="s", raw_source=f"{root}.dStopDelay")
            hold = self._bool(f"{root}.bActivOnHold", default=False)
            self._emit(result, f"ValveGate{gate}OnWhenHoldingState", hold, raw_source=f"{root}.bActivOnHold")
            self._emit(result, f"ValveGate{gate}OnWhenHoldingDelay", self._seconds(f"{root}.dHoldDelay", default=Decimal(0)), unit="s", raw_source=f"{root}.dHoldDelay")
            self._emit(result, f"ValveGate{gate}OnWhenHoldingTime", self._seconds(f"{root}.dHoldActTime", default=Decimal(0)), unit="s", raw_source=f"{root}.dHoldActTime")
            # Keep controller code 0/1 so Data.xlsx StateMap translates it to
            # Inyection 1 / Inyection 2.
            self._emit(result, f"ValveGate{gate}InjectionNo", injection_raw, raw_source=f"{root}.injection")

        self.active_valve_gates = tuple(active)
        self._check_limit("Secuenciador / Valve Gates", len(active), self.MAX_VALVE_GATE_ACTIVE)

    @staticmethod
    def _parse_bool_text(raw: Any, source_name: str) -> bool:
        text = str(raw).strip().lower()
        if text in {"true", "1", "on", "yes"}:
            return True
        if text in {"false", "0", "off", "no", ""}:
            return False
        raise SourceDataError(f"Invalid boolean value {raw!r} for {source_name}")
