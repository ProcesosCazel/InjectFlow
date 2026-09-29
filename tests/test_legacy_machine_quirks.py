from app.main import _filter_required_keys_for_machine_quirks


def test_second_valve_gate9_missing_fields_are_not_required_on_legacy_machines():
    required = {
        "ValveGate9OnWhenHoldingTime",
        "ValveGate9OnWhenHoldingDelay",
        "ValveGate8OnWhenHoldingTime",
        "HRSZone1Temp",
    }

    for machine in ("112C", "114B", "114C", "124A"):
        filtered = _filter_required_keys_for_machine_quirks(required, machine)
        assert "ValveGate9OnWhenHoldingTime" not in filtered
        assert "ValveGate9OnWhenHoldingDelay" not in filtered
        assert "ValveGate8OnWhenHoldingTime" in filtered
        assert "HRSZone1Temp" in filtered


def test_second_valve_gate9_requirements_are_unchanged_for_other_machines():
    required = {
        "ValveGate9OnWhenHoldingTime",
        "ValveGate9OnWhenHoldingDelay",
        "HRSZone1Temp",
    }
    assert _filter_required_keys_for_machine_quirks(required, "125A") == required
