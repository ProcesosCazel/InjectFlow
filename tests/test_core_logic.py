from pathlib import Path
from app.catalogs import MappingCatalog
from app.plan import PlanBuilder


def test_core_assignment_with_two_cores():
    fixtures = Path(__file__).parent / "fixtures"
    mapping = MappingCatalog(fixtures / "Mapeo_schema_fixture.xlsx")
    values = {r.key: 1 for r in mapping.mapping_rows}
    values.update({
        "MoldCloseZones": 6,
        "MoldOpenZones": 6,
        "InjectionZones": 6,
        "HoldingZones": 4,
        "ChargeZones": 3,
        "EjectorZonesFWD": 3,
        "EjectorZonesBWD": 3,
    })
    for n in range(1, 41):
        values[f"HRSZone{n}Mode"] = "ON"
    for n in range(1, 9):
        values[f"BarrelZone{n}Mode"] = "ON"
    values.update({"CoreAMode": "ON", "CoreBMode": "OFF", "CoreCMode": "ON", "CoreDMode": "OFF"})
    for row in mapping.core_field_rows:
        key = row.get("DATA KEY")
        if key:
            values.setdefault(str(key), 1)
    plan = PlanBuilder(mapping).build("NAVE_1", "NAVE1_V1", values, {"MoldNumber": "TEST", "MachineNumber": "112C"})
    assert plan.active_cores == ("A", "C")
    assert any(op.kind == "WRITE" and op.cell == "M52" and op.value == "A" for op in plan.operations)
    assert any(op.kind == "WRITE" and op.cell == "AB52" and op.value == "C" for op in plan.operations)
    assert any(op.kind == "WRITE" and op.cell == "J54" and op.value == "√" for op in plan.operations)
    assert any(op.kind == "WRITE" and op.cell == "AF54" and op.value == "√" for op in plan.operations)
