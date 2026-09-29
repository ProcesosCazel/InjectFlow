from pathlib import Path

from app.catalogs import MappingCatalog
from app.main import _hrs_total_zones_text


ROOT = Path(__file__).resolve().parents[1]


def test_hrs_total_zones_text_counts_only_logical_on_modes():
    values = {
        "HRSZone1Mode": "ON",
        "HRSZone2Mode": "OFF",
        "HRSZone3Mode": "ON",
        "HRSZone4Mode": "ON",
        "HRSZone5Temp": 260,
        "BarrelZone1Mode": "ON",
    }
    assert _hrs_total_zones_text(values) == "TOTAL: 3 ZONAS"


def test_hrs_total_zones_text_preserves_colon_for_zero_zones():
    assert _hrs_total_zones_text({"HRSZone1Mode": "OFF"}) == "TOTAL: 0 ZONAS"


def test_hrs_total_zones_mapping_is_present_in_all_four_layouts():
    mapping = MappingCatalog(ROOT / "data" / "Mapeo.xlsx")
    expected = {
        ("HAITIAN_ZE_V", "NAVE1_V1"): "BX47",
        ("HAITIAN_ZE_III", "ZERES_GENIII_V1"): "BX48",
        ("HAITIAN_ZE_III", "ZERES_GENIII_800_V1"): "CI46",
        ("HAITIAN_ZE_III", "ZERES_GENIII_1080_V1"): "CI46",
    }
    for (group, layout), cell in expected.items():
        rows = [
            row
            for row in mapping.rows_for(group, layout)
            if row.key == "HRSTotalZonesText"
        ]
        assert len(rows) == 1
        row = rows[0]
        assert row.source.upper() == "PARAM"
        assert row.cell == cell
        assert row.format_rule == "STATIC"
        assert row.map_status == "MAPPED"
        assert row.template_default == "TOTAL:  ZONAS"
