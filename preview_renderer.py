from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PreviewDocument:
    """PDF temporal producido a partir de la hoja visible del libro."""

    content: bytes
    sheet_name: str

    @property
    def size_bytes(self) -> int:
        return len(self.content)


class ExcelPdfPreviewRenderer:
    """Genera una vista previa PDF fiel usando Microsoft Excel en segundo plano.

    El libro se abre como solo lectura y nunca se modifica. La exportación respeta
    el área de impresión y la configuración de página ya definida en la plantilla.
    """

    def render(self, workbook_path: Path) -> PreviewDocument:
        workbook_path = Path(workbook_path).resolve()
        if not workbook_path.is_file():
            raise FileNotFoundError(f"No se encontró la hoja de parámetros: {workbook_path}")
        if workbook_path.suffix.lower() != ".xlsx":
            raise ValueError("La vista previa solo admite archivos .xlsx")
        if sys.platform != "win32":
            raise RuntimeError(
                "La vista previa oficial requiere Windows + Microsoft Excel + pywin32"
            )

        try:
            import pythoncom  # type: ignore
            import win32com.client  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "pywin32 no está instalado. Ejecuta INSTALAR_DEPENDENCIAS.bat"
            ) from exc

        excel = None
        book = None
        pythoncom.CoInitialize()
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            excel.ScreenUpdating = False
            try:
                excel.EnableEvents = False
            except Exception:
                pass

            book = excel.Workbooks.Open(
                str(workbook_path),
                UpdateLinks=0,
                ReadOnly=True,
                AddToMru=False,
            )

            visible_sheets = [
                book.Worksheets(index)
                for index in range(1, book.Worksheets.Count + 1)
                if book.Worksheets(index).Visible == -1
            ]
            if len(visible_sheets) != 1:
                raise RuntimeError(
                    f"Se esperaba una hoja visible; se encontraron {len(visible_sheets)}"
                )

            sheet = visible_sheets[0]
            sheet_name = str(sheet.Name)

            with tempfile.TemporaryDirectory(prefix="InjectFlowPreview_") as temp_dir:
                pdf_path = Path(temp_dir) / "preview.pdf"
                sheet.ExportAsFixedFormat(
                    Type=0,  # xlTypePDF
                    Filename=str(pdf_path),
                    Quality=0,  # xlQualityStandard
                    IncludeDocProperties=True,
                    IgnorePrintAreas=False,
                    OpenAfterPublish=False,
                )

                if not pdf_path.is_file():
                    raise RuntimeError("Microsoft Excel no produjo el PDF temporal de vista previa")

                content = pdf_path.read_bytes()

            if not content.startswith(b"%PDF-"):
                raise RuntimeError("El archivo temporal generado no es un PDF válido")
            if not content:
                raise RuntimeError("La vista previa PDF quedó vacía")

            return PreviewDocument(content=content, sheet_name=sheet_name)
        finally:
            if book is not None:
                try:
                    book.Close(SaveChanges=False)
                except Exception:
                    pass
            if excel is not None:
                try:
                    excel.ScreenUpdating = True
                    excel.Quit()
                except Exception:
                    pass
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
