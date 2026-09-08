from __future__ import annotations

import math
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .errors import WriterError
from .plan import Operation
from .utils import scalar_for_excel


@dataclass(frozen=True)
class WriteVerification:
    write_cells: int
    clear_cells: int
    checked_cells: int
    mismatches: tuple[str, ...] = ()
    merged_cells_normalized: int = 0


@dataclass(frozen=True)
class _ResolvedOperation:
    seq: int
    operation: Operation
    original_cell: str
    anchor_cell: str
    is_merged: bool


class ExcelComWriter:
    """Production writer using Microsoft Excel to preserve the official template.

    Excel does not allow writing/clearing an arbitrary child cell inside a merged
    range. Every target is therefore normalized to the upper-left cell of its
    MergeArea before WRITE/CLEAR/verification. COPY_FILL is applied to the full
    MergeArea so the official visual formatting is preserved.
    """

    def __init__(self, *, visible: bool = False):
        self.visible = visible

    def write(
        self,
        template_path: Path,
        output_path: Path,
        operations: Iterable[Operation],
        *,
        rename_sheet: bool = True,
    ) -> WriteVerification:
        if sys.platform != "win32":
            raise WriterError("Official generation requires Windows + Microsoft Excel + pywin32")
        try:
            import win32com.client  # type: ignore
        except ImportError as exc:
            raise WriterError("pywin32 is not installed. Run: pip install pywin32") from exc

        template_path = Path(template_path).resolve()
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_path, output_path)

        excel = None
        book = None
        success = False
        verification: WriteVerification | None = None
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = self.visible
            excel.DisplayAlerts = False
            excel.ScreenUpdating = False
            book = excel.Workbooks.Open(str(output_path), UpdateLinks=0, ReadOnly=False)

            visible_sheets = [
                book.Worksheets(i)
                for i in range(1, book.Worksheets.Count + 1)
                if book.Worksheets(i).Visible == -1
            ]
            if len(visible_sheets) != 1:
                raise WriterError(f"Expected one visible worksheet; found {len(visible_sheets)}")
            ws = visible_sheets[0]

            if rename_sheet:
                target_name = datetime.now().strftime("%d%m%Y")
                if ws.Name != target_name:
                    ws.Name = target_name

            operations = tuple(operations)
            resolved_ops = self._resolve_operations(ws, operations)
            normalized_count = sum(1 for item in resolved_ops if item.is_merged and item.original_cell != item.anchor_cell)

            # Freeze all fill references before changing any template cell.
            fill_snapshots: dict[str, dict[str, object]] = {}
            for item in resolved_ops:
                op = item.operation
                if op.kind != "COPY_FILL":
                    continue
                if not op.ref_cell:
                    raise WriterError(f"COPY_FILL without ref cell for {op.cell} ({op.note or 'no note'})")
                if op.ref_cell not in fill_snapshots:
                    ref = ws.Range(op.ref_cell)
                    fill_snapshots[op.ref_cell] = self._capture_fill(ref)

            # Keep only the final expected content for each physical merged anchor.
            final_expected: dict[str, tuple[str, object]] = {}

            for item in resolved_ops:
                op = item.operation
                try:
                    raw_cell = ws.Range(item.original_cell)
                    anchor = self._anchor_cell(raw_cell)
                    area = self._merge_area(raw_cell)

                    if op.kind == "WRITE":
                        value = scalar_for_excel(op.value)
                        anchor.Value = value
                        final_expected[item.anchor_cell] = ("WRITE", value)
                    elif op.kind == "CLEAR":
                        # Clear the complete merged region. ClearContents on a child
                        # cell of a merged range throws Excel error 1004.
                        area.ClearContents()
                        final_expected[item.anchor_cell] = ("CLEAR", None)
                    elif op.kind == "COPY_FILL":
                        if not op.ref_cell:
                            raise WriterError(f"COPY_FILL without ref cell for {op.cell}")
                        self._apply_fill(area, fill_snapshots[op.ref_cell])
                    else:
                        raise WriterError(f"Unsupported operation: {op.kind}")
                except WriterError:
                    raise
                except Exception as exc:
                    raise WriterError(
                        "Excel operation failed: "
                        f"seq={item.seq}, kind={op.kind}, original={item.original_cell}, "
                        f"anchor={item.anchor_cell}, merged={item.is_merged}, "
                        f"ref={op.ref_cell or '-'}, note={op.note or '-'}; {exc}"
                    ) from exc

            try:
                excel.CalculateFullRebuild()
            except Exception:
                excel.Calculate()

            mismatches: list[str] = []
            write_cells = 0
            clear_cells = 0
            for address, (kind, expected) in final_expected.items():
                try:
                    actual = self._anchor_cell(ws.Range(address)).Value
                except Exception as exc:
                    raise WriterError(f"Could not verify Excel cell {address}: {exc}") from exc
                if kind == "WRITE":
                    write_cells += 1
                else:
                    clear_cells += 1
                if not self._values_equal(actual, expected):
                    mismatches.append(
                        f"{address}: expected {expected!r} after {kind}, got {actual!r}"
                    )

            verification = WriteVerification(
                write_cells=write_cells,
                clear_cells=clear_cells,
                checked_cells=len(final_expected),
                mismatches=tuple(mismatches),
                merged_cells_normalized=normalized_count,
            )
            if mismatches:
                sample = "; ".join(mismatches[:12])
                raise WriterError(
                    f"Post-write Excel verification failed in {len(mismatches)} cells. {sample}"
                )

            book.Save()
            success = True
        except WriterError:
            raise
        except Exception as exc:
            raise WriterError(f"Excel generation failed: {exc}") from exc
        finally:
            if book is not None:
                try:
                    book.Close(SaveChanges=success)
                except Exception:
                    pass
            if excel is not None:
                try:
                    excel.ScreenUpdating = True
                    excel.Quit()
                except Exception:
                    pass
            if not success:
                try:
                    output_path.unlink(missing_ok=True)
                except Exception:
                    pass

        if verification is None:
            raise WriterError("Excel generation ended without verification")
        return verification

    def _resolve_operations(self, ws, operations: tuple[Operation, ...]) -> tuple[_ResolvedOperation, ...]:
        resolved: list[_ResolvedOperation] = []
        for seq, op in enumerate(operations, start=1):
            try:
                raw = ws.Range(op.cell)
                anchor = self._anchor_cell(raw)
                anchor_address = self._relative_address(anchor)
                is_merged = self._is_merged(raw)
            except Exception as exc:
                raise WriterError(
                    f"Could not resolve operation target: seq={seq}, kind={op.kind}, "
                    f"cell={op.cell}, note={op.note or '-'}; {exc}"
                ) from exc
            resolved.append(
                _ResolvedOperation(
                    seq=seq,
                    operation=op,
                    original_cell=op.cell,
                    anchor_cell=anchor_address,
                    is_merged=is_merged,
                )
            )
        return tuple(resolved)

    @staticmethod
    def _is_merged(cell) -> bool:
        try:
            return bool(cell.MergeCells)
        except Exception:
            return False

    @classmethod
    def _merge_area(cls, cell):
        return cell.MergeArea if cls._is_merged(cell) else cell

    @classmethod
    def _anchor_cell(cls, cell):
        if cls._is_merged(cell):
            return cell.MergeArea.Cells(1, 1)
        return cell

    @staticmethod
    def _relative_address(cell) -> str:
        try:
            # Excel constants are avoided intentionally to keep this helper easy
            # to fake in tests. Address(False, False) returns e.g. "K78".
            return str(cell.Address(False, False))
        except Exception:
            try:
                return str(cell.Address).replace("$", "")
            except Exception:
                return "?"

    @staticmethod
    def _values_equal(actual, expected) -> bool:
        if expected is None:
            return actual is None or actual == ""

        # Excel COM can return a date-only cell as a timezone-aware
        # pywintypes.datetime. Depending on the Windows/Excel time-zone bridge,
        # midnight written by Python may come back with an hour offset (for
        # example 00:00 -> 06:00) even though the Excel calendar date is
        # unchanged. GenerationDate is intentionally a date-only value, so
        # compare calendar dates instead of exact timestamps in that case.
        if isinstance(expected, datetime):
            expected_is_date_only = (
                expected.hour == 0
                and expected.minute == 0
                and expected.second == 0
                and expected.microsecond == 0
            )
            if expected_is_date_only and isinstance(actual, (datetime, date)):
                actual_date = actual.date() if isinstance(actual, datetime) else actual
                return actual_date == expected.date()
        elif isinstance(expected, date) and isinstance(actual, (datetime, date)):
            actual_date = actual.date() if isinstance(actual, datetime) else actual
            return actual_date == expected

        if isinstance(expected, bool):
            return bool(actual) == expected
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            return math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-9)

        # Excel commonly coerces text that looks numeric (for example a manually
        # entered machine number "125") to a numeric cell value such as 125.0.
        # Treat those as equivalent only when the text has no significant leading
        # zeros. Identifiers such as "00125" must remain distinct from 125.
        if isinstance(expected, str) and isinstance(actual, (int, float)):
            text = expected.strip()
            if text and ExcelComWriter._is_safe_numeric_text(text):
                try:
                    return math.isclose(float(actual), float(text), rel_tol=1e-9, abs_tol=1e-9)
                except ValueError:
                    pass

        if isinstance(actual, str) and isinstance(expected, (int, float)):
            text = actual.strip()
            if text and ExcelComWriter._is_safe_numeric_text(text):
                try:
                    return math.isclose(float(text), float(expected), rel_tol=1e-9, abs_tol=1e-9)
                except ValueError:
                    pass

        return str(actual) == str(expected)

    @staticmethod
    def _is_safe_numeric_text(text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            return False
        unsigned = normalized[1:] if normalized[:1] in {"+", "-"} else normalized
        if not unsigned:
            return False
        integer_part = unsigned.split(".", 1)[0]
        # Preserve identifiers with significant leading zeros. "0", "0.5",
        # and "-0.5" are safe numeric representations.
        if len(integer_part) > 1 and integer_part.startswith("0"):
            return False
        try:
            float(normalized)
        except ValueError:
            return False
        return True

    @classmethod
    def _capture_fill(cls, source) -> dict[str, object]:
        attrs = ["Pattern", "Color", "PatternColor", "TintAndShade", "PatternTintAndShade"]
        captured: dict[str, object] = {}
        area = cls._merge_area(source)
        for attr in attrs:
            try:
                captured[attr] = getattr(area.Interior, attr)
            except Exception:
                pass
        return captured

    @staticmethod
    def _apply_fill(dest_area, fill: dict[str, object]) -> None:
        for attr, value in fill.items():
            try:
                setattr(dest_area.Interior, attr, value)
            except Exception:
                pass
