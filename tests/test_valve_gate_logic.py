from decimal import Decimal
from pathlib import Path

import pytest

from app.catalogs import DataCatalog, MappingCatalog
from app.errors import ProcessWarning
from app.parsers import ParamRecord
from app.plan import PlanBuilder
from app.resolver import DataResolver


ROOT = Path(__file__).resolve().parents[1]


def _selector_values(*active: int) -> dict[str, object]:
    values: dict[str, object] = {}
    # Gate 9 intentionally has no validated selector and is marked REVIEW.
    for gate in [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13]:
        values[f"ValveGate{gate}State"] = "ON" if gate in active else "OFF"
    return values


def _active_gate_fields(values: dict[str, object], gate: int) -> None:
    values.update(
        {
            f"ValveGate{gate}StartCon": "INICIO INY.",
            f"ValveGate{gate}StartDelay": Decimal("0.25"),
            f"ValveGate{gate}OnStroke": Decimal(str(10 * gate)),
            f"ValveGate{gate}StopCon": "PRES. MANT.",
            f"ValveGate{gate}OffInjectionStroke": Decimal(str(5 * gate)),
            f"ValveGate{gate}OnWhenHoldingState": "ON",
            f"ValveGate{gate}OnWhenHoldingDelay": Decimal("0.50"),
            f"ValveGate{gate}OnWhenHoldingTime": Decimal("1.50"),
            "ValveGateFlow": Decimal("40"),
            "ValveGatePressure": Decimal("15"),
        }
    )


def test_non_consecutive_active_gates_pack_into_first_slots():
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    values = _selector_values(2, 5)
    _active_gate_fields(values, 2)
    _active_gate_fields(values, 5)

    ops, active = PlanBuilder(mapping)._build_valve_gate_ops(
        "HAITIAN_ZE_V", "NAVE1_V1", values
    )
    assert active == [2, 5]

    writes = {(op.cell, op.value) for op in ops if op.kind == "WRITE"}
    assert ("AW71", 2) in writes
    assert ("AW72", 5) in writes
    assert ("BK71", Decimal("20")) in writes
    assert ("BK72", Decimal("50")) in writes
    assert ("CB71", Decimal("40")) in writes
    assert ("CB72", Decimal("40")) in writes


def test_more_than_four_active_gates_raises_user_warning():
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    values = _selector_values(1, 2, 3, 4, 5)
    with pytest.raises(ProcessWarning, match="solo admite 4 Valve Gates"):
        PlanBuilder(mapping)._build_valve_gate_ops(
            "HAITIAN_ZE_V", "NAVE1_V1", values
        )


def test_gen3_more_than_one_core_raises_user_warning():
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    values = {
        "CoreAMode": "ON",
        "CoreBMode": "ON",
        "CoreCMode": "OFF",
        "CoreDMode": "OFF",
    }
    with pytest.raises(ProcessWarning, match="maximo 1"):
        PlanBuilder(mapping)._build_core_ops(
            "HAITIAN_ZE_III",
            "ZERES_GENIII_V1",
            values,
            "H16",
            "M16",
        )


def test_onstroke_prefers_mold_stroke_when_positive():
    data = DataCatalog(ROOT / "data" / "Data.xlsx")
    resolver = DataResolver(data)
    records = {
        "Valvegate1.sOnMoldStroke": [
            ParamRecord(
                "Valvegate1.sOnMoldStroke",
                Decimal("250000"),
                "1/10um",
                "1",
                "3",
                "255",
            )
        ],
        "Valvegate1.sOnInjectionStroke": [
            ParamRecord(
                "Valvegate1.sOnInjectionStroke",
                Decimal("850000"),
                "1/10um",
                "1",
                "3",
                "255",
            )
        ],
    }
    values = resolver.resolve_param(records, required_keys={"ValveGate1OnStroke"})
    assert values["ValveGate1OnStroke"] == Decimal("25.00")


def test_onstroke_falls_back_to_injection_when_mold_is_zero():
    data = DataCatalog(ROOT / "data" / "Data.xlsx")
    resolver = DataResolver(data)
    records = {
        "Valvegate1.sOnMoldStroke": [
            ParamRecord(
                "Valvegate1.sOnMoldStroke",
                Decimal("0"),
                "1/10um",
                "1",
                "3",
                "255",
            )
        ],
        "Valvegate1.sOnInjectionStroke": [
            ParamRecord(
                "Valvegate1.sOnInjectionStroke",
                Decimal("850000"),
                "1/10um",
                "1",
                "3",
                "255",
            )
        ],
    }
    values = resolver.resolve_param(records, required_keys={"ValveGate1OnStroke"})
    assert values["ValveGate1OnStroke"] == Decimal("85.00")
