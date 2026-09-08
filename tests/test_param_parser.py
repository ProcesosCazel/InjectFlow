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
