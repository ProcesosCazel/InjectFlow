from pathlib import Path

import pytest

from app.catalogs import MappingCatalog


PROJECT_ROOT = Path(__file__).resolve().parents[1]


RENAMED_MACHINES = {
    "101B": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "102B": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "103A": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "104B": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "105A": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "106B": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "107C": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "108C": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "115B": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "116C": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "117B": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "123B": ("HAITIAN_ZE_III", "ZERES_GENIII_V1"),
    "124A": ("HAITIAN_ZE_V", "NAVE1_V1"),
    "125A": ("HAITIAN_ZE_V", "NAVE1_V1"),
    "126A": ("HAITIAN_ZE_V", "NAVE1_V1"),
    "215B": ("HAITIAN_ZE_III", "ZERES_GENIII_800_V1"),
    "216A": ("HAITIAN_ZE_III", "ZERES_GENIII_800_V1"),
}

OLD_INCOMPLETE_NAMES = {
    "101", "102", "103", "104", "105", "106", "107", "108",
    "115", "116", "117", "123", "124", "125", "126", "215", "216",
}


def test_corrected_machine_names_keep_their_original_layouts() -> None:
    mapping = MappingCatalog(PROJECT_ROOT / "data" / "Mapeo.xlsx")

    for machine, expected in RENAMED_MACHINES.items():
        group, template = mapping.resolve_machine(machine)
        assert (group, template.layout_id) == expected


def test_incomplete_machine_names_are_no_longer_exposed() -> None:
    mapping = MappingCatalog(PROJECT_ROOT / "data" / "Mapeo.xlsx")

    assert OLD_INCOMPLETE_NAMES.isdisjoint(set(mapping.machines))
    assert set(RENAMED_MACHINES).issubset(set(mapping.machines))
