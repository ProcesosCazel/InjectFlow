from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from app.catalogs import MappingCatalog
from app.mold_catalog import MoldCatalog


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "data" / "Mapeo.xlsx"


def _build_test_molds_xlsx(tmp_path: Path) -> Path:
    """Create a stable Moldes.xlsx fixture independent of production master data."""

    path = tmp_path / "Moldes.xlsx"
    wb = Workbook()

    ws = wb.active
    ws.title = "Moldes"
    ws.append(
        [
            "Molde",
            "Numero articulo",
            "Descripción",
            "Art Cliente",
            "Tiempo Ciclo",
            "Cliente",
        ]
    )

    # I-9000 validates aggregation while preserving file order.
    ws.append(["I-9000", "ART001", "PIEZA 1", "PN-001", 50, "FAURECIA"])
    ws.append(["I-9000", "ART002", "PIEZA 2", "PN-002", 55, "ADIENT"])
    ws.append(["I-9000", "ART003", "PIEZA 3", "PN-003", 52, "VOLKSWAGEN"])
    ws.append(["I-9000", "ART004", "PIEZA 4", "PN-004", 55, "LEAR"])

    # Duplicate exact row must not be repeated in the resolved output.
    ws.append(["I-9000", "ART004", "PIEZA 4", "PN-004", 55, "LEAR"])

    # I-9001 validates description abbreviation and empty customer part numbers.
    ws.append(["I-9001", "ENS/001", "SEAL FRNT DOOR RH", "", 30, "CUSTOMER A"])
    ws.append(["I-9001", "ENS/002", "SEAL FRNT DOOR LH", "", 28, "CUSTOMER A"])

    # I-9002 exists in the main table but intentionally has no CAVS row.
    ws.append(["I-9002", "ART010", "NO CAVITY DATA", "PN-010", 40, "CUSTOMER B"])

    # Invalid mold numbers must be ignored by the catalog loader.
    ws.append(["9003", "BAD001", "INVALID MOLD", "BAD-PN", 99, "SHOULD NOT LOAD"])

    cavs = wb.create_sheet("CAVS")
    cavs.append(["Molde", "CAVS"])
    cavs.append(["I-9000", "1 + 1"])
    cavs.append(["I-9000", "1+1"])
    cavs.append(["I-9001", "2+2"])

    wb.save(path)
    wb.close()
    return path


def test_mold_catalog_expected_known_examples(tmp_path: Path) -> None:
    catalog = MoldCatalog(_build_test_molds_xlsx(tmp_path))

    mold = catalog.resolve("I-9001")
    assert mold is not None
    assert mold.internal_code == "ENS/001 / ENS/002"
    assert mold.customer_part_number == ""
    assert mold.description == "SEAL FRNT DOOR RH / LH"
    assert mold.qad_cycle_time == 30
    assert mold.customer == "CUSTOMER A"
    assert mold.cavities == "2+2"


def test_mold_catalog_uses_maximum_qad_cycle_time(tmp_path: Path) -> None:
    catalog = MoldCatalog(_build_test_molds_xlsx(tmp_path))

    result = catalog.resolve("I-9000")
    assert result is not None
    assert result.qad_cycle_time == 55


def test_mold_catalog_preserves_multiple_customers_without_guessing(
    tmp_path: Path,
) -> None:
    catalog = MoldCatalog(_build_test_molds_xlsx(tmp_path))
    result = catalog.resolve("I-9000")

    assert result is not None
    assert result.customer == "FAURECIA / ADIENT / VOLKSWAGEN / LEAR"


def test_mold_catalog_preserves_unique_values_and_ignores_exact_duplicates(
    tmp_path: Path,
) -> None:
    catalog = MoldCatalog(_build_test_molds_xlsx(tmp_path))
    result = catalog.resolve("I-9000")

    assert result is not None
    assert result.internal_code == "ART001 / ART002 / ART003 / ART004"
    assert result.customer_part_number == "PN-001 / PN-002 / PN-003 / PN-004"
    assert result.description == "PIEZA 1 / 2 / 3 / 4"


def test_mold_catalog_cavities_are_optional_and_normalized(tmp_path: Path) -> None:
    catalog = MoldCatalog(_build_test_molds_xlsx(tmp_path))

    # Equivalent CAVS values are normalized and consolidated.
    result_with_cavs = catalog.resolve("I-9000")
    assert result_with_cavs is not None
    assert result_with_cavs.cavities == "1+1"

    # Mold exists in the main table but not in CAVS.
    result_without_cavs = catalog.resolve("I-9002")
    assert result_without_cavs is not None
    assert result_without_cavs.cavities == ""


def test_mold_catalog_rejects_invalid_or_unknown_mold_number(tmp_path: Path) -> None:
    catalog = MoldCatalog(_build_test_molds_xlsx(tmp_path))

    assert catalog.resolve("I-9999") is None
    assert catalog.resolve("9000") is None
    assert catalog.resolve("I-900") is None
    assert catalog.resolve("I-9000A") is None
    assert catalog.resolve("9003") is None


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
