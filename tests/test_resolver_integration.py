import zlib
from decimal import Decimal
from pathlib import Path

from app.catalogs import DataCatalog
from app.parsers import ParamDatParser, ResulCsvParser
from app.resolver import DataResolver


def _pick_state_raw(data: DataCatalog, state_map: str):
    mapping = data.state_maps[state_map]
    # Prefer zero if present, otherwise first key.
    return 0 if 0 in mapping else next(iter(mapping))


def test_all_param_rules_resolve_with_synthetic_dat(tmp_path: Path):
    fixtures = Path(__file__).parent / "fixtures"
    data = DataCatalog(fixtures / "Data_schema_fixture.xlsx")
    lines = []
    seen = set()
    for rule in data.param_rules:
        if not rule.active or rule.source.upper() != "PARAM.DAT" or not rule.source_name:
            continue
        if rule.source_name in seen:
            continue
        seen.add(rule.source_name)
        if rule.calc_type == "STATE":
            raw = _pick_state_raw(data, rule.state_map)
        elif rule.validity_rule:
            raw = 10000
        else:
            raw = 10000
        lines.append(f"{rule.source_name},{raw},,{1},{3},255,\r\n".encode("gb18030"))
    body = b"".join(lines)
    crc = zlib.crc32(body) & 0xFFFFFFFF
    raw_file = b"VE\x00\r\nMOLD INFO\r\n[VERSION: 2]\r\n[CRC: 16#%08X]\r\n" % crc + body
    path = tmp_path / "Param.dat"
    path.write_bytes(raw_file)
    records = ParamDatParser().parse(path)
    values = DataResolver(data).resolve_param(records)
    assert len(values) >= 289
    assert "S0MoldClose" in values


def test_all_resul_rules_resolve_from_fixed_blocks(tmp_path: Path):
    fixtures = Path(__file__).parent / "fixtures"
    data = DataCatalog(fixtures / "Data_schema_fixture.xlsx")
    direct = [r for r in data.resul_rules if r.source.upper() == "RESUL.CSV"]
    headers = ["Record"] + [r.source_name for r in direct] + ["Time", "Mold Number"]
    rows = [",".join(headers)]
    for i in range(1, 26):
        values = [str(i)] + [str(10 + j + i / 100) for j in range(len(direct))] + ["31.08.26-08:00:00", str(1000 + i)]
        rows.append(",".join(values))
    blocks = []
    for row in rows:
        payload = (row + "\r").encode("ascii")
        assert len(payload) <= 300
        blocks.append(payload + b"\x00" * (300 - len(payload)))
    path = tmp_path / "Resul.csv"
    path.write_bytes(b"".join(blocks))
    _, parsed = ResulCsvParser().parse(path)
    values = DataResolver(data).resolve_resul(parsed)
    assert set(r.key for r in data.resul_rules).issubset(values)
    assert values["ChargeSafetyTime"] > values["ChargeTime"]
