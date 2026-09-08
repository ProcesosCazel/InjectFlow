from app.excel_writer import ExcelComWriter
from app.plan import PlanBuilder


def test_on_off_is_not_globally_blank():
    assert PlanBuilder._display_value("ON") == "ON"
    assert PlanBuilder._display_value("OFF") == "OFF"
    assert PlanBuilder._checkbox_value("ON") == "\u221a"
    assert PlanBuilder._checkbox_value("OFF") is None


def test_excel_value_comparison():
    assert ExcelComWriter._values_equal(10.0, 10)
    assert ExcelComWriter._values_equal(None, None)
    assert ExcelComWriter._values_equal("", None)
    assert ExcelComWriter._values_equal("ON", "ON")
    assert ExcelComWriter._values_equal(125.0, "125")
    assert ExcelComWriter._values_equal("125", 125.0)
    assert not ExcelComWriter._values_equal(125.0, "00125")
    assert not ExcelComWriter._values_equal(None, "ON")
