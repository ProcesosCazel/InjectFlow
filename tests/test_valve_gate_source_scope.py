"""Family isolation and optional DAT banks; no mutable Moldes.xlsx fixtures."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.catalogs import DataCatalog, MappingCatalog
from app.errors import SourceDataError
from app.input_policy import JUPITER_GROUP
from app.main import _filter_required_keys_for_available_valve_gates
from app.parsers import ParamRecord
from app.plan import PlanBuilder
from app.resolver import DataResolver

ROOT = Path(__file__).resolve().parents[1]
ZERES = "HAITIAN_ZE_III"


@pytest.fixture(scope="module")
def data() -> DataCatalog:
    return DataCatalog(ROOT / "data" / "Data.xlsx")


@pytest.fixture(scope="module")
def mapping() -> MappingCatalog:
    return MappingCatalog(ROOT / "data" / "Mapeo.xlsx")


def _records(values: dict[str, int | str]) -> dict[str, list[ParamRecord]]:
    return {
        key: [ParamRecord(key, Decimal(str(value)), "", "1", "3", "255")]
        for key, value in values.items()
    }


def _base_bank() -> dict[str, list[ParamRecord]]:
    return _records({f"Valvegate{gate}.sFunction": 0 for gate in range(1, 9)})


def _complete_gate(gate: int, *, active: bool = False) -> dict[str, list[ParamRecord]]:
    return _records({
        f"Valvegate{gate}.sFunction": int(active),
        f"Valvegate{gate}.sStartCondtion": 0,
        f"Valvegate{gate}.sStopCondition": 0,
        f"Valvegate{gate}.sOnMoldStroke": 0,
        f"Valvegate{gate}.sOnInjectionStroke": 0,
        f"Valvegate{gate}.sOffInjectionStroke": 0,
        f"Valvegate{gate}.sStartDelayTime": 0,
        f"SecondValveGate{gate}.sFunc": 0,
        f"SecondValveGate{gate}.sSetTime": 0,
        f"SecondValveGate{gate}.sSetDelayTime": 0,
    })


@pytest.mark.parametrize("group", ["HAITIAN_ZE_III", "HAITIAN_ZE_V"])
def test_zeres_never_uses_jupiter_fallback(data, group):
    resolver = DataResolver(data)
    values = resolver.resolve_param(
        _records({"Jupiter.ValveGate10State": 1}),
        {"ValveGate10State"}, template_group=group,
    )
    assert "ValveGate10State" not in values
    assert len(resolver.parameter_warnings) == 1
    assert "Valvegate10.sFunction" in resolver.parameter_warnings[0]
    assert "Jupiter." not in resolver.parameter_warnings[0]
    assert "J0413" not in resolver.parameter_warnings[0]


def test_jupiter_never_uses_dat_fallback(data):
    resolver = DataResolver(data)
    values = resolver.resolve_param(
        _records({"Valvegate10.sFunction": 1}),
        {"ValveGate10State"}, template_group=JUPITER_GROUP,
    )
    assert "ValveGate10State" not in values
    assert len(resolver.parameter_warnings) == 1
    assert "Jupiter.ValveGate10State" in resolver.parameter_warnings[0]
    assert "Valvegate10.sFunction" not in resolver.parameter_warnings[0]
    assert "P382" not in resolver.parameter_warnings[0]


@pytest.mark.parametrize("group, expected", [(ZERES, "OFF"), (JUPITER_GROUP, "ON")])
def test_selected_family_wins_over_rule_priority(data, group, expected):
    resolver = DataResolver(data)
    records = _records({"Valvegate10.sFunction": 0, "Jupiter.ValveGate10State": 1})
    result = resolver.resolve_param(records, {"ValveGate10State"}, template_group=group)
    assert result["ValveGate10State"] == expected
    assert resolver.parameter_warnings == []


def test_wrong_family_only_key_is_reported_not_silently_discarded(data):
    rule = next(r for r in data.param_rules if r.rule_id == "J0413")
    catalog = SimpleNamespace(param_rules=(rule,), resul_rules=(), state_maps=data.state_maps)
    resolver = DataResolver(catalog)
    result = resolver.resolve_param({}, {"ValveGate10State"}, template_group=ZERES)
    assert "ValveGate10State" not in result
    assert resolver.parameter_warnings == [
        "ValveGate10State: no applicable Param rule for family HAITIAN_ZE_III"
    ]


def test_dependency_expansion_uses_applicable_source_rules(data):
    source = next(r for r in data.param_rules if r.rule_id == "P382")
    jupiter = next(r for r in data.param_rules if r.rule_id == "J0413")
    # A source rule from the other family must not pull its dependencies into DAT.
    jupiter = replace(jupiter, dependency=("OnlyOtherFamily",))
    other = replace(jupiter, rule_id="SYNTHETIC", key="OnlyOtherFamily",
                    source_name="Jupiter.OnlyOtherFamily", dependency=())
    catalog = SimpleNamespace(param_rules=(source, jupiter, other),
                              resul_rules=(), state_maps=data.state_maps)
    resolver = DataResolver(catalog)
    result = resolver.resolve_param(_records({"Valvegate10.sFunction": 0}),
                                    {"ValveGate10State"}, template_group=ZERES)
    assert result == {"ValveGate10State": "OFF"}
    assert resolver.parameter_warnings == []


@pytest.mark.parametrize("group", ["HAITIAN_ZE_III", "HAITIAN_ZE_V"])
def test_complete_base_bank_omits_only_absent_extension_blocks(group):
    original = {f"ValveGate{n}State" for n in range(1, 14)} | {
        "ValveGate10StartCon", "ValveGate13OnWhenHoldingTime",
        "ValveGatePressure", "HRSZone1Mode", "CoreAMode",
    }
    result = _filter_required_keys_for_available_valve_gates(original, _base_bank(), group)
    assert result == {f"ValveGate{n}State" for n in range(1, 10)} | {
        "ValveGatePressure", "HRSZone1Mode", "CoreAMode",
    }
    assert "ValveGate13State" in original  # Input collection is not mutated.


@pytest.mark.parametrize("missing_gate", [1, 8])
def test_incomplete_base_bank_keeps_warnings_possible(missing_gate):
    records = _base_bank()
    records.pop(f"Valvegate{missing_gate}.sFunction")
    required = {"ValveGate10State", "ValveGate13StartCon"}
    assert _filter_required_keys_for_available_valve_gates(required, records, ZERES) == required


def test_empty_export_is_not_treated_as_a_valid_eight_gate_controller():
    required = {"ValveGate1State", "ValveGate10State"}
    assert _filter_required_keys_for_available_valve_gates(required, {}, ZERES) == required


@pytest.mark.parametrize("source", [
    "Valvegate10.sFunction", "Valvegate10.sStartDelayTime", "SecondValveGate10.sFunc",
])
def test_any_partial_extension_block_is_retained(source):
    records = _base_bank()
    records.update(_records({source: 0}))
    required = {"ValveGate10State", "ValveGate10StartCon", "ValveGate10OnWhenHoldingTime"}
    assert _filter_required_keys_for_available_valve_gates(required, records, ZERES) == required


def test_missing_selector_in_existing_extension_is_still_a_warning(data):
    records = _base_bank()
    records.update(_records({"SecondValveGate10.sFunc": 0}))
    required = _filter_required_keys_for_available_valve_gates({"ValveGate10State"}, records, ZERES)
    resolver = DataResolver(data)
    result = resolver.resolve_param(records, required, template_group=ZERES)
    assert "ValveGate10State" not in result
    assert len(resolver.parameter_warnings) == 1
    assert "Valvegate10.sFunction" in resolver.parameter_warnings[0]
    assert "Jupiter." not in resolver.parameter_warnings[0]


def test_missing_parameter_of_active_gate_is_still_a_warning(data):
    records = _base_bank()
    records.update(_records({"Valvegate10.sFunction": 1}))
    required = _filter_required_keys_for_available_valve_gates(
        {"ValveGate10State", "ValveGate10StartCon"}, records, ZERES)
    resolver = DataResolver(data)
    result = resolver.resolve_param(records, required, template_group=ZERES)
    assert result["ValveGate10State"] == "ON"
    assert "ValveGate10StartCon" not in result
    assert len(resolver.parameter_warnings) == 1
    assert "Valvegate10.sStartCondtion" in resolver.parameter_warnings[0]


def test_unknown_state_is_not_silenced(data):
    resolver = DataResolver(data)
    with pytest.raises(SourceDataError, match="Unknown state"):
        resolver.resolve_param(_records({"Valvegate1.sFunction": 999}),
                               {"ValveGate1State"}, template_group=ZERES)


def test_conflicting_duplicates_are_not_silenced(data):
    records = _records({"Valvegate1.sFunction": 0})
    records["Valvegate1.sFunction"] += _records({"Valvegate1.sFunction": 1})["Valvegate1.sFunction"]
    resolver = DataResolver(data)
    with pytest.raises(SourceDataError, match="conflicting duplicate"):
        resolver.resolve_param(records, {"ValveGate1State"}, template_group=ZERES)


@pytest.mark.parametrize("gate", [10, 21, 37])
def test_present_higher_gates_are_not_limited_to_eight(gate):
    records = _base_bank()
    records.update(_records({f"Valvegate{gate}.sFunction": 1}))
    required = {f"ValveGate{gate}State", f"ValveGate{gate}OnStroke"}
    assert _filter_required_keys_for_available_valve_gates(required, records, ZERES) == required


def test_jupiter_uses_full_direct_numbering_without_dat_bank_filter():
    required = {f"ValveGate{gate}State" for gate in range(1, 49)}
    assert _filter_required_keys_for_available_valve_gates(required, {}, JUPITER_GROUP) == required
    assert _filter_required_keys_for_available_valve_gates(required, _base_bank(), JUPITER_GROUP) == required


def test_zero_values_remain_valid_when_gate_is_present(data):
    records = _base_bank()
    records.update(_complete_gate(10, active=True))
    required = {"ValveGate10State", "ValveGate10OnStroke", "ValveGate10StartDelay"}
    resolver = DataResolver(data)
    result = resolver.resolve_param(records, required, template_group=ZERES)
    assert result == {"ValveGate10State": "ON", "ValveGate10OnStroke": Decimal(0),
                      "ValveGate10StartDelay": Decimal(0)}
    assert resolver.parameter_warnings == []


def test_eight_off_gates_keep_all_template_slots_blank_and_gray(data, mapping):
    records = {}
    for gate in range(1, 10):
        records.update(_complete_gate(gate))
    # Raw 9 keeps residual parameters but no selector in this controller layout.
    records.pop("Valvegate9.sFunction")
    records.pop("SecondValveGate9.sFunc")
    required = {
        str(r['DATA KEY']) for r in mapping.valve_gate_fields(ZERES, 'ZERES_GENIII_V1')
        if r.get('STATUS') in {'MAPPED', 'CONTROL'}
        and str(r.get('DATA KEY', '')).startswith('ValveGate')
        and str(r.get('DATA KEY', ''))[9:10].isdigit()
    }
    resolver = DataResolver(data)
    filtered = _filter_required_keys_for_available_valve_gates(required, records, ZERES)
    values = resolver.resolve_param(records, filtered, template_group=ZERES)
    assert resolver.parameter_warnings == []
    assert not any(key.startswith('ValveGate10') for key in values)
    operations, active = PlanBuilder(mapping, data)._build_valve_gate_ops(
        ZERES, 'ZERES_GENIII_V1', values)
    assert active == []
    assert not any(op.kind == 'WRITE' for op in operations)
    fills = [op for op in operations if op.kind == 'COPY_FILL']
    assert len(fills) == 48
    assert all(op.ref_cell == 'M16' for op in fills)


def test_legacy_unscoped_resolver_api_remains_compatible(data):
    resolver = DataResolver(data)
    result = resolver.resolve_param(_records({'Jupiter.ValveGate13State': 1}),
                                    {'ValveGate13State'})
    assert result == {'ValveGate13State': 'ON'}
    assert resolver.parameter_warnings == []
