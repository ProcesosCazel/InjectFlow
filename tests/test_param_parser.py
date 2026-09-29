import zlib
from pathlib import Path
from app.parsers import ParamDatParser


def test_param_crc_and_record(tmp_path: Path):
    body = b"Test.Key,1000,ms,{1},{3},255,\r\n"
    crc = zlib.crc32(body) & 0xFFFFFFFF
    raw = b"VE\x00\r\nMOLD INFO\r\n[VERSION: 2]\r\n[CRC: 16#%08X]\r\n" % crc + body
    path = tmp_path / "Param.dat"
    path.write_bytes(raw)
    records = ParamDatParser().parse(path)
    assert records["Test.Key"][0].raw_value == 1000


def test_param_parser_allows_trailing_non_csv_lines(tmp_path):
    import zlib
    from app.parsers import ParamDatParser

    body = (
        b'Key1,100,ms,{a},{b},255,\r\n'
        b'Key2,200,ms,{a},{b},255,\r\n'
        b'TRAILER ONE\r\n'
        b'TRAILER TWO\r\n'
    )
    crc = zlib.crc32(body) & 0xFFFFFFFF
    raw = b'VE\x00\r\nMOLD INFO\r\n[VERSION: 2]\r\n[CRC: 16#%08X]\r\n' % crc + body
    path = tmp_path / 'Param.dat'
    path.write_bytes(raw)

    parser = ParamDatParser(validate_crc=True)
    result = parser.parse(path)
    assert set(result) == {'Key1', 'Key2'}
    assert parser.ignored_trailer_lines == [7, 8]


def test_param_parser_rejects_malformed_line_inside_records(tmp_path):
    import zlib
    import pytest
    from app.parsers import ParamDatParser
    from app.errors import SourceDataError

    body = (
        b'Key1,100,ms,{a},{b},255,\r\n'
        b'BROKEN\r\n'
        b'Key2,200,ms,{a},{b},255,\r\n'
    )
    crc = zlib.crc32(body) & 0xFFFFFFFF
    raw = b'VE\x00\r\nMOLD INFO\r\n[VERSION: 2]\r\n[CRC: 16#%08X]\r\n' % crc + body
    path = tmp_path / 'Param.dat'
    path.write_bytes(raw)

    with pytest.raises(SourceDataError, match='malformed records'):
        ParamDatParser(validate_crc=True).parse(path)


def _write_param_dat(tmp_path: Path, lines: list[bytes], name: str = "Param.dat") -> Path:
    body = b"".join(lines)
    crc = zlib.crc32(body) & 0xFFFFFFFF
    raw = b"VE\x00\r\nMOLD INFO\r\n[VERSION: 2]\r\n[CRC: 16#%08X]\r\n" % crc + body
    path = tmp_path / name
    path.write_bytes(raw)
    return path


def _param_line(key: str, value: int, unit: str = "") -> bytes:
    return f"{key},{value},{unit},{{1}},{{3}},255,\r\n".encode("gb18030")


def test_hrs_falls_back_to_ccp_when_primary_is_off(tmp_path: Path):
    path = _write_param_dat(
        tmp_path,
        [
            _param_line("MoldHeating1.sHeatingSet", 0, "DegreeCelsius"),
            _param_line("MoldHeating1.sHeatingMode", 0),
            _param_line("MoldHeating1.sHeatingZoneSwitch", 0),
            _param_line("MoldHeating2.sHeatingSet", 0, "DegreeCelsius"),
            _param_line("MoldHeating2.sHeatingMode", 0),
            _param_line("MoldHeating2.sHeatingZoneSwitch", 0),
            _param_line("MoldHeating1_ccp.sHeatingSet", 2300, "DegreeCelsius"),
            _param_line("MoldHeating1_ccp.sHeatingMode", 1),
            _param_line("MoldHeating1_ccp.sHeatingZoneSwitch", 1),
            _param_line("MoldHeating2_ccp.sHeatingSet", 2300, "DegreeCelsius"),
            _param_line("MoldHeating2_ccp.sHeatingMode", 1),
            _param_line("MoldHeating2_ccp.sHeatingZoneSwitch", 1),
        ],
    )

    parser = ParamDatParser()
    records = parser.parse(path)

    assert parser.hrs_source == "MoldHeating_ccp"
    assert parser.hrs_primary_active_zones == ()
    assert parser.hrs_ccp_active_zones == (1, 2)
    assert records["MoldHeating1.sHeatingSet"][0].raw_value == 2300
    assert records["MoldHeating2.sHeatingSet"][0].raw_value == 2300
    assert records["MoldHeating1.sHeatingMode"][0].raw_value == 1
    assert records["MoldHeating2.sHeatingMode"][0].raw_value == 1
    assert parser.process_warnings == []


def test_hrs_zone_switch_overrides_stale_heating_mode(tmp_path: Path):
    path = _write_param_dat(
        tmp_path,
        [
            _param_line("MoldHeating1.sHeatingSet", 2100, "DegreeCelsius"),
            _param_line("MoldHeating1.sHeatingMode", 1),
            _param_line("MoldHeating1.sHeatingZoneSwitch", 0),
            _param_line("MoldHeating1_ccp.sHeatingSet", 0, "DegreeCelsius"),
            _param_line("MoldHeating1_ccp.sHeatingMode", 1),
            _param_line("MoldHeating1_ccp.sHeatingZoneSwitch", 0),
        ],
    )

    parser = ParamDatParser()
    records = parser.parse(path)

    assert parser.hrs_source == "MoldHeating"
    assert records["MoldHeating1.sHeatingMode"][0].raw_value == 0


def test_hrs_primary_has_priority_and_warns_when_both_sources_are_active(tmp_path: Path):
    path = _write_param_dat(
        tmp_path,
        [
            _param_line("MoldHeating1.sHeatingSet", 2000, "DegreeCelsius"),
            _param_line("MoldHeating1.sHeatingMode", 1),
            _param_line("MoldHeating1.sHeatingZoneSwitch", 1),
            _param_line("MoldHeating2.sHeatingSet", 0, "DegreeCelsius"),
            _param_line("MoldHeating2.sHeatingMode", 0),
            _param_line("MoldHeating2.sHeatingZoneSwitch", 0),
            _param_line("MoldHeating1_ccp.sHeatingSet", 2300, "DegreeCelsius"),
            _param_line("MoldHeating1_ccp.sHeatingMode", 1),
            _param_line("MoldHeating1_ccp.sHeatingZoneSwitch", 1),
            _param_line("MoldHeating2_ccp.sHeatingSet", 2250, "DegreeCelsius"),
            _param_line("MoldHeating2_ccp.sHeatingMode", 1),
            _param_line("MoldHeating2_ccp.sHeatingZoneSwitch", 1),
        ],
    )

    parser = ParamDatParser()
    records = parser.parse(path)

    assert parser.hrs_source == "MoldHeating"
    assert parser.hrs_primary_active_zones == (1,)
    assert parser.hrs_ccp_active_zones == (1, 2)
    assert records["MoldHeating1.sHeatingSet"][0].raw_value == 2000
    assert records["MoldHeating2.sHeatingMode"][0].raw_value == 0
    assert len(parser.process_warnings) == 1
    assert "MoldHeating (1)" in parser.process_warnings[0]
    assert "MoldHeating_ccp (1, 2)" in parser.process_warnings[0]
    assert "prioridad" in parser.process_warnings[0]


def test_hrs_legacy_export_without_zone_switch_is_unchanged(tmp_path: Path):
    path = _write_param_dat(
        tmp_path,
        [
            _param_line("MoldHeating1.sHeatingSet", 2050, "DegreeCelsius"),
            _param_line("MoldHeating1.sHeatingMode", 1),
        ],
    )

    parser = ParamDatParser()
    records = parser.parse(path)

    assert parser.hrs_source is None
    assert records["MoldHeating1.sHeatingSet"][0].raw_value == 2050
    assert records["MoldHeating1.sHeatingMode"][0].raw_value == 1
    assert parser.process_warnings == []


def test_barrel_factory_default_profile_overrides_stale_heating_mode(tmp_path: Path):
    path = _write_param_dat(
        tmp_path,
        [
            _param_line("HeatingZoneControl7.sHeatingSet", 1600, "DegreeCelsius"),
            _param_line("HeatingZoneControl7.sHeatingMax", 100, "DegreeCelsius"),
            _param_line("HeatingZoneControl7.sHeatingMin", 100, "DegreeCelsius"),
            _param_line("HeatingZoneControl7.sHeatingMode", 1),
            _param_line("HeatingZoneControl7.sHeatingStandby", 1500, "DegreeCelsius"),
            _param_line("HeatingZoneControl7.sHeatingRate", 1000, "1/10Percent"),
        ],
    )

    parser = ParamDatParser()
    records = parser.parse(path)

    assert records["HeatingZoneControl7.sHeatingMode"][0].raw_value == 0
    assert records["HeatingZoneControl7.sHeatingSet"][0].raw_value == 1600
    assert parser.barrel_default_inactive_zones == (7,)


def test_barrel_near_default_profile_is_not_forced_off(tmp_path: Path):
    path = _write_param_dat(
        tmp_path,
        [
            _param_line("HeatingZoneControl7.sHeatingSet", 1600, "DegreeCelsius"),
            _param_line("HeatingZoneControl7.sHeatingMax", 200, "DegreeCelsius"),
            _param_line("HeatingZoneControl7.sHeatingMin", 100, "DegreeCelsius"),
            _param_line("HeatingZoneControl7.sHeatingMode", 1),
            _param_line("HeatingZoneControl7.sHeatingStandby", 1500, "DegreeCelsius"),
        ],
    )

    parser = ParamDatParser()
    records = parser.parse(path)

    assert records["HeatingZoneControl7.sHeatingMode"][0].raw_value == 1
    assert parser.barrel_default_inactive_zones == ()


def test_all_hot_running_legacy_namespace_is_machine_scoped(tmp_path: Path):
    path = _write_param_dat(
        tmp_path,
        [
            _param_line(r"AllHotRunning1\HotRunnerParameter1.sSetValue", 2500, "DegreeCelsius"),
            _param_line(r"AllHotRunning1\HotRunnerParameter1.sswitch", 1),
            _param_line(r"AllHotRunning1\HotRunnerParameter2.sSetValue", 0, "DegreeCelsius"),
            _param_line(r"AllHotRunning1\HotRunnerParameter2.sswitch", 0),
            # Stale legacy MoldHeating mode values exist but do not carry the
            # physical HRS switch/setpoint on these controllers.
            _param_line("MoldHeating1.sHeatingMode", 1),
            _param_line("MoldHeating2.sHeatingMode", 1),
        ],
    )

    legacy = ParamDatParser(machine="112C")
    records = legacy.parse(path)
    assert legacy.hrs_source == "AllHotRunning1"
    assert legacy.hrs_all_hot_running_active_zones == (1,)
    assert records["MoldHeating1.sHeatingSet"][0].raw_value == 2500
    assert records["MoldHeating1.sHeatingZoneSwitch"][0].raw_value == 1
    assert records["MoldHeating1.sHeatingMode"][0].raw_value == 1
    assert records["MoldHeating2.sHeatingSet"][0].raw_value == 0
    assert records["MoldHeating2.sHeatingZoneSwitch"][0].raw_value == 0
    # The stale sHeatingMode=1 is replaced by the real physical switch OFF.
    assert records["MoldHeating2.sHeatingMode"][0].raw_value == 0

    normal = ParamDatParser(machine="125A")
    normal_records = normal.parse(path)
    assert normal.hrs_source is None
    assert normal.hrs_all_hot_running_active_zones == ()
    assert "MoldHeating1.sHeatingSet" not in normal_records
    assert "MoldHeating1.sHeatingZoneSwitch" not in normal_records
    assert normal_records["MoldHeating2.sHeatingMode"][0].raw_value == 1


def test_all_hot_running_legacy_namespace_applies_to_all_four_known_machines(tmp_path: Path):
    path = _write_param_dat(
        tmp_path,
        [
            _param_line(r"AllHotRunning1\HotRunnerParameter1.sSetValue", 2600, "DegreeCelsius"),
            _param_line(r"AllHotRunning1\HotRunnerParameter1.sswitch", 1),
        ],
    )

    for machine in ("112C", "114B", "114C", "124A"):
        parser = ParamDatParser(machine=machine)
        records = parser.parse(path)
        assert parser.hrs_source == "AllHotRunning1"
        assert parser.hrs_all_hot_running_active_zones == (1,)
        assert records["MoldHeating1.sHeatingSet"][0].raw_value == 2600
        assert records["MoldHeating1.sHeatingMode"][0].raw_value == 1
