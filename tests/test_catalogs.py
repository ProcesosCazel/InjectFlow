from pathlib import Path
from app.catalogs import DataCatalog, MappingCatalog


def test_known_catalog_schemas_load():
    fixtures = Path(__file__).parent / "fixtures"
    data = DataCatalog(fixtures / "Data_schema_fixture.xlsx")
    mapping = MappingCatalog(fixtures / "Mapeo_schema_fixture.xlsx")
    assert len(data.param_rules) >= 280
    assert "112C" in mapping.machines
    group, template = mapping.resolve_machine("112C")
    assert group == "NAVE_1"
    assert template.layout_id == "NAVE1_V1"
