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

    fills = {(op.cell, op.ref_cell) for op in ops if op.kind == "COPY_FILL"}
    # SLOT1/SLOT2 are active and must keep the normal transparent fill.
    assert ("AW71", "AL18") in fills
    assert ("AW72", "AL18") in fills
    # SLOT3/SLOT4 are unused and must be shaded gray.
    assert ("AW73", "N18") in fills
    assert ("AW74", "N18") in fills
    assert ("CY73", "N18") in fills
    assert ("CY74", "N18") in fills


@pytest.mark.parametrize(
    ("group", "layout_id", "first_cell", "last_cell", "inactive_ref", "expected_fill_count"),
    [
        ("HAITIAN_ZE_V", "NAVE1_V1", "AW71", "CY74", "N18", 44),
        ("HAITIAN_ZE_III", "ZERES_GENIII_V1", "AR70", "CS73", "M16", 48),
    ],
)
def test_no_active_valve_gates_shades_all_four_slots(
    group: str,
    layout_id: str,
    first_cell: str,
    last_cell: str,
    inactive_ref: str,
    expected_fill_count: int,
):
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    values = _selector_values()

    ops, active = PlanBuilder(mapping)._build_valve_gate_ops(
        group, layout_id, values
    )

    assert active == []
    fills = {op.cell: op.ref_cell for op in ops if op.kind == "COPY_FILL"}
    assert fills[first_cell] == inactive_ref
    assert fills[last_cell] == inactive_ref
    # Every physical sequencer cell must receive the inactive fill.
    # Gen III now has 12 fields per row after adding Tiem. Ret. Off.
    assert sum(1 for ref in fills.values() if ref == inactive_ref) == expected_fill_count
    assert not any(op.kind == "WRITE" for op in ops)


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


def test_holding_delay_and_time_are_blank_and_gray_when_second_pressure_is_off():
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    values = _selector_values(1)
    _active_gate_fields(values, 1)
    values["ValveGate1OnWhenHoldingState"] = "OFF"
    # Residual controller values must not be printed while the function is OFF.
    values["ValveGate1OnWhenHoldingDelay"] = Decimal("9.99")
    values["ValveGate1OnWhenHoldingTime"] = Decimal("8.88")

    ops, active = PlanBuilder(mapping)._build_valve_gate_ops(
        "HAITIAN_ZE_V", "NAVE1_V1", values
    )

    assert active == [1]
    writes = {(op.cell, op.value) for op in ops if op.kind == "WRITE"}
    assert ("CM71", "OFF") in writes
    assert not any(cell == "CT71" for cell, _value in writes)
    assert not any(cell == "CY71" for cell, _value in writes)

    # Only the two dependent fields are re-shaded inactive; the Valve Gate row
    # itself stays active.
    assert any(
        op.kind == "COPY_FILL" and op.cell == "CT71" and op.ref_cell == "N18"
        for op in ops
    )
    assert any(
        op.kind == "COPY_FILL" and op.cell == "CY71" and op.ref_cell == "N18"
        for op in ops
    )
    assert any(
        op.kind == "COPY_FILL" and op.cell == "CM71" and op.ref_cell == "AL18"
        for op in ops
    )


def test_310b_gate21_second_pressure_on_writes_zero_delay_and_15_second_time():
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    values = {
        "ValveGate21State": "ON",
        "ValveGate21StartCon": "INICIO INY.",
        "ValveGate21StartDelay": Decimal("0"),
        "ValveGate21OnStroke": Decimal("185"),
        "ValveGate21StopCon": "DESP. 2A PR.",
        "ValveGate21OffInjectionStroke": Decimal("0"),
        "ValveGateFlow": Decimal("50"),
        "ValveGatePressure": Decimal("10"),
        "ValveGate21OnWhenHoldingState": "ON",
        "ValveGate21OnWhenHoldingDelay": Decimal("0"),
        "ValveGate21OnWhenHoldingTime": Decimal("15"),
    }

    ops, active = PlanBuilder(mapping)._build_valve_gate_ops(
        "HAITIAN_ZE_III", "ZERES_GENIII_1080_V1", values
    )

    assert active == [20]
    writes = {(op.cell, op.value) for op in ops if op.kind == "WRITE"}
    assert ("CG65", "ON") in writes
    assert ("CN65", Decimal("0")) in writes
    assert ("CS65", Decimal("15")) in writes

    # ON leaves both dependent cells with the normal active fill established by
    # the row reset; they must not be re-shaded with the inactive reference.
    assert not any(
        op.kind == "COPY_FILL" and op.cell in {"CN65", "CS65"} and op.ref_cell == "M15"
        for op in ops
    )


def test_gen3_1080_delay_off_maps_global_five_seconds_to_active_slot():
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    values = {
        "ValveGate21State": "ON",
        "ValveGate21StartCon": "INICIO INY.",
        "ValveGate21StartDelay": Decimal("0"),
        "ValveGate21OnStroke": Decimal("185"),
        "ValveGate21StopCon": "DESP. 2A PR.",
        "ValveGate21OffInjectionStroke": Decimal("0"),
        "ValveGateFlow": Decimal("50"),
        "ValveGatePressure": Decimal("10"),
        "ValveGateDelayOffTime": Decimal("5"),
        "ValveGate21OnWhenHoldingState": "ON",
        "ValveGate21OnWhenHoldingDelay": Decimal("0"),
        "ValveGate21OnWhenHoldingTime": Decimal("15"),
    }

    ops, active = PlanBuilder(mapping)._build_valve_gate_ops(
        "HAITIAN_ZE_III", "ZERES_GENIII_1080_V1", values
    )

    assert active == [20]
    writes = {(op.cell, op.value) for op in ops if op.kind == "WRITE"}
    assert ("BQ65", Decimal("5")) in writes
    assert ("BU65", Decimal("0")) in writes
    assert ("BY65", Decimal("50")) in writes
    assert ("CC65", Decimal("10")) in writes
    assert ("CN65", Decimal("0")) in writes
    assert ("CS65", Decimal("15")) in writes


def test_gen3_800_layout_is_prepared_with_twelve_delay_off_slots():
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    rows = mapping.valve_gate_layout("HAITIAN_ZE_III", "ZERES_GENIII_800_V1")
    delay_cells = sorted(
        str(row.get("CELL"))
        for row in rows
        if str(row.get("FIELD") or "").upper() == "DELAY_OFF"
    )
    assert delay_cells == [f"BQ{row}" for row in range(65, 77)]


def test_controller_gate9_is_always_ignored_even_if_selector_is_on():
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    values = _selector_values()
    values["ValveGate9State"] = "ON"

    ops, active = PlanBuilder(mapping)._build_valve_gate_ops(
        "HAITIAN_ZE_III", "ZERES_GENIII_V1", values
    )

    assert active == []
    assert not any(op.kind == "WRITE" for op in ops)


def test_controller_gate10_is_displayed_as_hmi_gate9_but_uses_gate10_data():
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    values = _selector_values(10)
    _active_gate_fields(values, 10)

    ops, active = PlanBuilder(mapping)._build_valve_gate_ops(
        "HAITIAN_ZE_V", "NAVE1_V1", values
    )

    assert active == [9]
    writes = {(op.cell, op.value) for op in ops if op.kind == "WRITE"}
    assert ("AW71", 9) in writes
    # OnStroke must still come from raw controller Gate 10 (10 * gate = 100).
    assert ("BK71", Decimal("100")) in writes


def test_controller_gate21_is_displayed_as_hmi_gate20():
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    values = {
        "ValveGate21State": "ON",
        "ValveGate21StartCon": "INICIO INY.",
        "ValveGate21StartDelay": Decimal("0"),
        "ValveGate21OnStroke": Decimal("185"),
        "ValveGate21StopCon": "DESP. 2A PR.",
        "ValveGate21OffInjectionStroke": Decimal("0"),
        "ValveGateFlow": Decimal("50"),
        "ValveGatePressure": Decimal("10"),
        "ValveGateDelayOffTime": Decimal("5"),
        "ValveGate21OnWhenHoldingState": "ON",
        "ValveGate21OnWhenHoldingDelay": Decimal("0"),
        "ValveGate21OnWhenHoldingTime": Decimal("15"),
    }

    ops, active = PlanBuilder(mapping)._build_valve_gate_ops(
        "HAITIAN_ZE_III", "ZERES_GENIII_1080_V1", values
    )

    assert active == [20]
    writes = {(op.cell, op.value) for op in ops if op.kind == "WRITE"}
    assert ("AR65", 20) in writes
    assert ("BQ65", Decimal("5")) in writes
    assert ("CN65", Decimal("0")) in writes
    assert ("CS65", Decimal("15")) in writes
