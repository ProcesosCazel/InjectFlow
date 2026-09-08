from pathlib import Path
from app.parsers import ResulCsvParser


def test_normal_csv_is_supported(tmp_path: Path):
    path = tmp_path / "Resul.csv"
    path.write_text(
        ",Cycle Time,Charge Time,Time,Mold Number\n"
        "1,41.1,5.6,bad,999\n"
        "2,41.2,5.7,bad,998\n",
        encoding="ascii",
    )
    header, rows = ResulCsvParser().parse(path)
    assert "Cycle Time" in header
    assert header[0] == "Record"
    assert len(rows) == 2
