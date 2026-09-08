from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from .catalogs import DataCatalog, ParamRule, ResulRule
from .errors import ConfigurationError, MissingParameterError, SourceDataError
from .parsers import ParamRecord
from .utils import as_decimal, normalize_control_value, round_decimal


class DataResolver:
    """Resolve logical Data.xlsx keys from machine exports.

    Missing Param.dat keys are handled in best-effort mode: the unresolved
    logical parameter is omitted from the returned dictionary and a warning is
    collected in ``parameter_warnings``. Malformed data, conflicting duplicate
    values, unknown states and invalid Data.xlsx configuration remain blocking
    errors because continuing in those cases could write an incorrect value.
    """

    def __init__(self, data: DataCatalog):
        self.data = data
        self.parameter_warnings: list[str] = []

    def resolve_param(
        self,
        records: dict[str, list[ParamRecord]],
        required_keys: set[str] | None = None,
    ) -> dict[str, Any]:
        self.parameter_warnings = []
        direct_by_key: dict[str, list[ParamRule]] = defaultdict(list)
        derived: list[ParamRule] = []
        expanded_required = self._expand_required(required_keys) if required_keys is not None else None
        for rule in self.data.param_rules:
            if not rule.active:
                continue
            if expanded_required is not None and rule.key not in expanded_required:
                continue
            if rule.source.upper() == "PARAM.DAT":
                direct_by_key[rule.key].append(rule)
            else:
                derived.append(rule)

        values: dict[str, Any] = {}
        unavailable: set[str] = set()
        for key, rules in direct_by_key.items():
            try:
                values[key] = self._resolve_param_key(key, rules, records)
            except MissingParameterError as exc:
                unavailable.add(key)
                self._add_parameter_warning(str(exc))

        pending = list(derived)
        for _ in range(len(pending) + 2):
            if not pending:
                break
            next_pending: list[ParamRule] = []
            progressed = False
            for rule in pending:
                if not all(dep in values for dep in rule.dependency):
                    next_pending.append(rule)
                    continue
                values[rule.key] = self._resolve_derived_param(rule, values)
                progressed = True
            pending = next_pending
            if not progressed:
                break

        # A derived parameter whose dependency is unavailable is also unavailable,
        # not a configuration failure. Propagate that condition through chains of
        # derived rules. True dependency cycles / bad configuration still block.
        while pending:
            explained: list[ParamRule] = []
            still_pending: list[ParamRule] = []
            for rule in pending:
                missing_deps = [dep for dep in rule.dependency if dep not in values]
                if missing_deps and any(dep in unavailable for dep in missing_deps):
                    unavailable.add(rule.key)
                    self._add_parameter_warning(
                        f"{rule.key} ({rule.rule_id}): no se pudo calcular porque falta "
                        + ", ".join(missing_deps)
                    )
                    explained.append(rule)
                else:
                    still_pending.append(rule)
            if not explained:
                details = [f"{r.key} <- {r.dependency}" for r in still_pending]
                raise ConfigurationError(f"Unresolved ParamCalc dependencies: {details}")
            pending = still_pending

        return values

    def _add_parameter_warning(self, message: str) -> None:
        text = str(message).strip()
        if text and text not in self.parameter_warnings:
            self.parameter_warnings.append(text)

    def _resolve_param_key(
        self,
        key: str,
        rules: list[ParamRule],
        records: dict[str, list[ParamRecord]],
    ) -> Any:
        ordered = sorted(
            rules,
            key=lambda r: (r.priority if r.priority is not None else 10**9, r.rule_id),
        )
        errors: list[str] = []
        for rule in ordered:
            if not rule.source_name:
                # This is a catalog/configuration defect, not a missing value in
                # this particular machine export.
                raise ConfigurationError(
                    f"{rule.rule_id} / {key}: missing MACHINE PARAMETER NAME"
                )
            found = records.get(rule.source_name, [])
            if not found:
                errors.append(f"{rule.rule_id}: source key not found: {rule.source_name}")
                continue
            rec = self._select_duplicate(rule.source_name, found)
            if not self._valid(rule, rec.raw_value):
                errors.append(f"{rule.rule_id}: validity failed ({rule.validity_rule})")
                continue
            return self._apply_param_rule(rule, rec.raw_value)

        raise MissingParameterError(key, "; ".join(errors) or "no valid source was found")

    @staticmethod
    def _select_duplicate(source_name: str, records: list[ParamRecord]) -> ParamRecord:
        if len(records) == 1:
            return records[0]
        signature = {(r.raw_value, r.unit) for r in records}
        if len(signature) == 1:
            return records[0]
        raise SourceDataError(f"Param.dat contains conflicting duplicate values for {source_name}")

    @staticmethod
    def _valid(rule: ParamRule, raw: Any) -> bool:
        if not rule.validity_rule:
            return True
        text = rule.validity_rule.replace(" ", "").upper()
        if text == "RAW_DATA>0":
            return as_decimal(raw, field=rule.key) > 0
        raise ConfigurationError(f"Unsupported VALIDITY RULE: {rule.validity_rule}")

    def _apply_param_rule(self, rule: ParamRule, raw: Any) -> Any:
        calc = rule.calc_type
        if calc == "STATE":
            if not rule.state_map or rule.state_map not in self.data.state_maps:
                raise ConfigurationError(f"Missing StateMap {rule.state_map!r} for {rule.key}")
            raw_key = normalize_control_value(raw)
            mapping = self.data.state_maps[rule.state_map]
            normalized_map = {normalize_control_value(k): v for k, v in mapping.items()}
            if raw_key not in normalized_map:
                raise SourceDataError(f"Unknown state {raw!r} for {rule.key} using {rule.state_map}")
            return normalized_map[raw_key]
        if calc in {"SCALE", "FIRST_VALID"}:
            value = as_decimal(raw, field=rule.key)
            factor = rule.factor if rule.factor is not None else Decimal(1)
            result = value * factor + rule.offset
            return round_decimal(result, rule.decimals, "NEAREST")
        if calc == "RAW":
            if isinstance(raw, Decimal):
                return round_decimal(raw + rule.offset, rule.decimals, "NEAREST")
            return raw
        raise ConfigurationError(f"Unsupported Param CALC TYPE {calc!r} for {rule.key}")

    def _resolve_derived_param(self, rule: ParamRule, values: dict[str, Any]) -> Any:
        calc = rule.calc_type
        if calc == "ADD":
            result = sum(
                (as_decimal(values[d], field=d) for d in rule.dependency),
                Decimal(0),
            ) + rule.offset
            return round_decimal(result, rule.decimals, "NEAREST")
        if calc == "COPY":
            if len(rule.dependency) != 1:
                raise ConfigurationError(f"COPY expects one dependency for {rule.key}")
            value = values[rule.dependency[0]]
            if isinstance(value, Decimal):
                return round_decimal(value + rule.offset, rule.decimals, "NEAREST")
            return value
        raise ConfigurationError(f"Unsupported derived Param CALC TYPE {calc!r} for {rule.key}")

    def _expand_required(self, required_keys: set[str]) -> set[str]:
        expanded = set(required_keys)
        changed = True
        while changed:
            changed = False
            for rule in (*self.data.param_rules, *self.data.resul_rules):
                if rule.key in expanded:
                    for dep in rule.dependency:
                        if dep not in expanded:
                            expanded.add(dep)
                            changed = True
        return expanded

    def resolve_resul(
        self,
        rows: list[dict[str, str]],
        required_keys: set[str] | None = None,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        expanded_required = self._expand_required(required_keys) if required_keys is not None else None
        direct: list[ResulRule] = []
        derived: list[ResulRule] = []
        for rule in self.data.resul_rules:
            if not rule.active:
                continue
            if expanded_required is not None and rule.key not in expanded_required:
                continue
            if rule.source.upper() == "RESUL.CSV":
                direct.append(rule)
            else:
                derived.append(rule)

        for rule in direct:
            if rule.calc_type != "AVERAGE":
                raise ConfigurationError(f"Unsupported Resul CALC TYPE {rule.calc_type!r} for {rule.key}")
            if not rule.source_name:
                raise ConfigurationError(f"Missing MACHINE RESULTANT NAME for {rule.key}")
            window = rule.window or int(self.data.cfg("RESUL_DEFAULT_WINDOW", 20))
            if len(rows) < window:
                raise SourceDataError(
                    f"Resul.csv has {len(rows)} data rows; {window} are required for {rule.key}"
                )
            vals: list[Decimal] = []
            for i, row in enumerate(rows[:window], start=1):
                if rule.source_name not in row:
                    raise SourceDataError(f"Resul.csv column not found: {rule.source_name}")
                raw = row[rule.source_name]
                if raw is None or str(raw).strip() == "":
                    raise SourceDataError(
                        f"Empty value in {rule.source_name}, recent record {i}/{window}"
                    )
                vals.append(as_decimal(raw, field=rule.source_name))
            avg = sum(vals, Decimal(0)) / Decimal(window)
            avg += rule.offset
            values[rule.key] = round_decimal(avg, rule.decimals, rule.round_mode)

        pending = list(derived)
        for _ in range(len(pending) + 2):
            if not pending:
                break
            next_pending: list[ResulRule] = []
            progressed = False
            for rule in pending:
                if not all(dep in values for dep in rule.dependency):
                    next_pending.append(rule)
                    continue
                if rule.calc_type == "ADD":
                    result = sum(
                        (as_decimal(values[d], field=d) for d in rule.dependency),
                        Decimal(0),
                    ) + rule.offset
                    values[rule.key] = round_decimal(result, rule.decimals, rule.round_mode)
                elif rule.calc_type == "COPY":
                    if len(rule.dependency) != 1:
                        raise ConfigurationError(f"COPY expects one dependency for {rule.key}")
                    value = as_decimal(
                        values[rule.dependency[0]], field=rule.dependency[0]
                    ) + rule.offset
                    values[rule.key] = round_decimal(value, rule.decimals, rule.round_mode)
                else:
                    raise ConfigurationError(
                        f"Unsupported ResulCalc type {rule.calc_type!r} for {rule.key}"
                    )
                progressed = True
            pending = next_pending
            if not progressed:
                break
        if pending:
            raise ConfigurationError(
                f"Unresolved ResulCalc dependencies: {[r.key for r in pending]}"
            )
        return values
