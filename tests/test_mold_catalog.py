from __future__ import annotations

from pathlib import Path

from app.catalogs import MappingCatalog
from app.mold_catalog import MoldCatalog


ROOT = Path(__file__).resolve().parents[1]
MOLDS = ROOT / "data" / "Moldes.xlsx"
MAPPING = ROOT / "data" / "Mapeo.xlsx"


def test_mold_catalog_expected_known_examples() -> None:
    catalog = MoldCatalog(MOLDS)

    i1004 = catalog.resolve("I-1004")
    assert i1004 is not None
    assert i1004.internal_code == "VOL10R003 / VOL10R004"
    assert i1004.customer_part_number == "1C0809961G / 1C0809962J"
    assert i1004.description == "ARMAZON PASARRUEDA"
    assert i1004.qad_cycle_time == 57
    assert i1004.cavities == "1+1"

    i1027 = catalog.resolve("I-1027")
    assert i1027 is not None
    assert i1027.internal_code == "ENS/63820 / ENS/63821"
    assert i1027.customer_part_number == ""
    assert i1027.description == "SEAL FRNT DOOR RH / LH"
    assert i1027.qad_cycle_time == 30
    assert i1027.cavities == "2+2"


def test_mold_catalog_uses_maximum_qad_cycle_time() -> None:
    catalog = MoldCatalog(MOLDS)

    assert catalog.resolve("I-1137").qad_cycle_time == 28  # type: ignore[union-attr]
    assert catalog.resolve("I-1163").qad_cycle_time == 129  # type: ignore[union-attr]
    assert catalog.resolve("I-1599").qad_cycle_time == 138  # type: ignore[union-attr]


def test_mold_catalog_preserves_multiple_customers_without_guessing() -> None:
    catalog = MoldCatalog(MOLDS)
    result = catalog.resolve("I-1270")

    assert result is not None
    assert result.customer == "FAURECIA / ADIENT / VOLKSWAGEN"


def test_mold_catalog_cavities_are_optional_and_normalized() -> None:
    catalog = MoldCatalog(MOLDS)

    # CAVS contiene dos registros equivalentes: "1+1" y "1 + 1".
    assert catalog.resolve("I-1654").cavities == "1+1"  # type: ignore[union-attr]

    # El molde existe en la tabla principal, pero no existe en CAVS.
    assert catalog.resolve("I-1139").cavities == ""  # type: ignore[union-attr]


def test_mold_catalog_rejects_invalid_or_unknown_mold_number() -> None:
    catalog = MoldCatalog(MOLDS)

    assert catalog.resolve("I-9999") is None
    assert catalog.resolve("1004") is None
    assert catalog.resolve("I-100") is None
    assert catalog.resolve("I-1004A") is None


def test_mold_mapping_is_present_in_all_four_layouts_and_qad_is_separate() -> None:
    mapping = MappingCatalog(MAPPING)
    expected = {
        ("HAITIAN_ZE_V", "NAVE1_V1"): {
            "MoldDescription": "M3",
            "MoldInternalCode": "Q5",
            "MoldCustomerPartNumber": "BY5",
            "MoldQADCycleTime": "AP70",
            "MoldCustomer": "O4",
            "MoldCavities": "CF8",
        },
        ("HAITIAN_ZE_III", "ZERES_GENIII_V1"): {
            "MoldDescription": "M3",
            "MoldInternalCode": "N5",
            "MoldCustomerPartNumber": "BR5",
            "MoldQADCycleTime": "AK69",
            "MoldCustomer": "L4",
            "MoldCavities": "BY8",
        },
        ("HAITIAN_ZE_III", "ZERES_GENIII_800_V1"): {
            "MoldDescription": "M3",
            "MoldInternalCode": "N5",
            "MoldCustomerPartNumber": "BR5",
            "MoldQADCycleTime": "AK64",
            "MoldCustomer": "L4",
            "MoldCavities": "BY8",
        },
        ("HAITIAN_ZE_III", "ZERES_GENIII_1080_V1"): {
            "MoldDescription": "M3",
            "MoldInternalCode": "N5",
            "MoldCustomerPartNumber": "BR5",
            "MoldQADCycleTime": "AK64",
            "MoldCustomer": "L4",
            "MoldCavities": "BY8",
        },
    }

    for (group, layout), cells in expected.items():
        rows = {
            row.key: row
            for row in mapping.rows_for(group, layout)
            if row.source.strip().upper() == "MOLD"
        }
        assert set(rows) == set(cells)
        for key, cell in cells.items():
            assert rows[key].cell == cell
            assert rows[key].map_status == "MAPPED"
            assert rows[key].format_rule == "STATIC"

        real_cycle_cells = {
            row.cell
            for row in mapping.rows_for(group, layout)
            if row.key == "CycleTime" and row.map_status == "MAPPED"
        }
        assert cells["MoldQADCycleTime"] not in real_cycle_cells
