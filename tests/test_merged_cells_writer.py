from app.excel_writer import ExcelComWriter


class FakeInterior:
    Pattern = 1
    Color = 123
    PatternColor = 0
    TintAndShade = 0
    PatternTintAndShade = 0


class FakeCells:
    def __init__(self, anchor):
        self.anchor = anchor

    def __call__(self, row, col):
        assert row == 1 and col == 1
        return self.anchor


class FakeCell:
    def __init__(self, address, *, merged=False, anchor=None):
        self._address = address
        self.MergeCells = merged
        self.Interior = FakeInterior()
        self.Value = None
        if merged:
            if anchor is None:
                anchor = self
            self.MergeArea = FakeArea(anchor)
        else:
            self.MergeArea = self

    def Address(self, row_abs=False, col_abs=False):
        return self._address

    def ClearContents(self):
        self.Value = None


class FakeArea:
    def __init__(self, anchor):
        self.anchor = anchor
        self.Cells = FakeCells(anchor)
        self.Interior = FakeInterior()
        self.cleared = False

    def ClearContents(self):
        self.cleared = True
        self.anchor.Value = None


def test_anchor_cell_for_merged_child():
    anchor = FakeCell("K78")
    child = FakeCell("L78", merged=True, anchor=anchor)
    assert ExcelComWriter._anchor_cell(child) is anchor
    assert ExcelComWriter._relative_address(ExcelComWriter._anchor_cell(child)) == "K78"


def test_merge_area_clear_is_used_for_merged_cells():
    anchor = FakeCell("K78")
    anchor.Value = 123
    child = FakeCell("L78", merged=True, anchor=anchor)
    area = ExcelComWriter._merge_area(child)
    area.ClearContents()
    assert anchor.Value is None
    assert area.cleared is True


def test_normal_cell_stays_itself():
    cell = FakeCell("AG69")
    assert ExcelComWriter._anchor_cell(cell) is cell
    assert ExcelComWriter._merge_area(cell) is cell
