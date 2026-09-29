from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PREVIEW_TIMEOUT_SECONDS = 15.0
DEFAULT_PREVIEW_MAX_ATTEMPTS = 3
DEFAULT_PREVIEW_RETRY_DELAY_SECONDS = 0.35


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

    Cada intento se ejecuta en un proceso auxiliar separado. Si Excel/COM o el
    subsistema de impresion se bloquea durante ExportAsFixedFormat, el proceso
    principal conserva el control, cancela ese intento y vuelve a probar.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_PREVIEW_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_PREVIEW_MAX_ATTEMPTS,
        retry_delay_seconds: float = DEFAULT_PREVIEW_RETRY_DELAY_SECONDS,
    ) -> None:
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))

    def render(self, workbook_path: Path) -> PreviewDocument:
        workbook_path = Path(workbook_path).resolve()
        if not workbook_path.is_file():
            raise FileNotFoundError(f"No se encontro la hoja de parametros: {workbook_path}")
        if workbook_path.suffix.lower() != ".xlsx":
            raise ValueError("La vista previa solo admite archivos .xlsx")
        if sys.platform != "win32":
            raise RuntimeError(
                "La vista previa oficial requiere Windows + Microsoft Excel + pywin32"
            )

        last_error: BaseException | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._render_isolated(workbook_path)
            except Exception as exc:
                last_error = exc
                if attempt < self.max_attempts and self.retry_delay_seconds:
                    time.sleep(self.retry_delay_seconds)

        raise RuntimeError(
            f"No fue posible generar la vista previa despues de {self.max_attempts} intentos."
        ) from last_error

    def _render_isolated(self, workbook_path: Path) -> PreviewDocument:
        with tempfile.TemporaryDirectory(prefix="InjectFlowPreview_") as temp_dir:
            temp_root = Path(temp_dir)
            pdf_path = temp_root / "preview.pdf"
            metadata_path = temp_root / "preview.json"
            excel_pid_path = temp_root / "excel.pid"

            command = _preview_worker_command(
                workbook_path=workbook_path,
                pdf_path=pdf_path,
                metadata_path=metadata_path,
                excel_pid_path=excel_pid_path,
            )

            creationflags = 0
            if sys.platform == "win32":
                creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )

            try:
                return_code = process.wait(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                _stop_process(process)
                _terminate_excel_from_pid_file(excel_pid_path)
                raise TimeoutError(
                    f"La vista previa excedio {self.timeout_seconds:.0f} segundos."
                ) from exc

            if return_code != 0:
                _terminate_excel_from_pid_file(excel_pid_path)
                detail = _worker_error(metadata_path)
                raise RuntimeError(detail or "Excel no pudo exportar la vista previa.")

            if not pdf_path.is_file():
                raise RuntimeError("Microsoft Excel no produjo el PDF temporal de vista previa")

            content = pdf_path.read_bytes()
            if not content or not content.startswith(b"%PDF-"):
                raise RuntimeError("El archivo temporal generado no es un PDF valido")

            sheet_name = ""
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                sheet_name = str(metadata.get("sheet", ""))
            except Exception:
                pass

            return PreviewDocument(content=content, sheet_name=sheet_name)


def _preview_worker_command(
    *,
    workbook_path: Path,
    pdf_path: Path,
    metadata_path: Path,
    excel_pid_path: Path,
) -> list[str]:
    args = [
        "--preview-worker",
        str(workbook_path),
        "--preview-output",
        str(pdf_path),
        "--preview-metadata",
        str(metadata_path),
        "--preview-excel-pid",
        str(excel_pid_path),
    ]

    if getattr(sys, "frozen", False):
        return [sys.executable, *args]

    launcher = Path(__file__).resolve().with_name("launcher_web.py")
    return [sys.executable, str(launcher), *args]


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        process.kill()
        process.wait(timeout=2.0)
    except Exception:
        pass


def _worker_error(metadata_path: Path) -> str:
    if not metadata_path.is_file():
        return ""
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        return str(payload.get("error", "")).strip()
    except Exception:
        return ""


def _terminate_excel_from_pid_file(pid_path: Path) -> None:
    """Termina solo el Excel creado por el worker que acaba de fallar."""

    if sys.platform != "win32" or not pid_path.is_file():
        return

    try:
        pid = int(pid_path.read_text(encoding="ascii").strip())
    except Exception:
        return

    if pid <= 0:
        return

    creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if not _pid_is_excel(pid, creationflags=creationflags):
        return

    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5.0,
            check=False,
            creationflags=creationflags,
        )
    except Exception:
        pass


def _pid_is_excel(pid: int, *, creationflags: int = 0) -> bool:
    """Evita terminar un PID reutilizado que ya no pertenezca a Excel."""

    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3.0,
            check=False,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        first_line = (result.stdout or "").splitlines()[0].upper()
        return "EXCEL.EXE" in first_line
    except Exception:
        return False


def _write_excel_pid(excel: object, pid_path: Path) -> None:
    """Registra el PID de la instancia DispatchEx para poder limpiarla al timeout."""

    try:
        hwnd = int(getattr(excel, "Hwnd"))
        process_id = ctypes.c_ulong(0)
        ctypes.windll.user32.GetWindowThreadProcessId(  # type: ignore[attr-defined]
            hwnd,
            ctypes.byref(process_id),
        )
        if process_id.value:
            pid_path.write_text(str(process_id.value), encoding="ascii")
    except Exception:
        pass


def run_preview_worker(
    *,
    workbook_path: Path,
    pdf_path: Path,
    metadata_path: Path,
    excel_pid_path: Path,
) -> int:
    """Worker interno usado por el proceso principal para aislar Excel COM."""

    workbook_path = Path(workbook_path).resolve()
    pdf_path = Path(pdf_path).resolve()
    metadata_path = Path(metadata_path).resolve()
    excel_pid_path = Path(excel_pid_path).resolve()

    excel = None
    book = None
    pythoncom = None

    try:
        if sys.platform != "win32":
            raise RuntimeError("El worker de vista previa requiere Windows.")
        if not workbook_path.is_file() or workbook_path.suffix.lower() != ".xlsx":
            raise FileNotFoundError(str(workbook_path))

        import pythoncom as _pythoncom  # type: ignore
        import win32com.client  # type: ignore

        pythoncom = _pythoncom
        pythoncom.CoInitialize()

        excel = win32com.client.DispatchEx("Excel.Application")
        _write_excel_pid(excel, excel_pid_path)

        excel.Visible = False
        excel.DisplayAlerts = False
        excel.ScreenUpdating = False
        try:
            excel.EnableEvents = False
        except Exception:
            pass
        try:
            excel.AskToUpdateLinks = False
        except Exception:
            pass
        try:
            excel.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
        except Exception:
            pass

        book = excel.Workbooks.Open(
            str(workbook_path),
            UpdateLinks=0,
            ReadOnly=True,
            IgnoreReadOnlyRecommended=True,
            Notify=False,
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

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.ExportAsFixedFormat(
            Type=0,
            Filename=str(pdf_path),
            Quality=0,
            IncludeDocProperties=True,
            IgnorePrintAreas=False,
            OpenAfterPublish=False,
        )

        if not pdf_path.is_file():
            raise RuntimeError("Microsoft Excel no produjo el PDF temporal de vista previa")

        metadata_path.write_text(
            json.dumps({"ok": True, "sheet": sheet_name}, ensure_ascii=False),
            encoding="utf-8",
        )
        return 0
    except Exception as exc:
        try:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(
                json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
        return 2
    finally:
        if book is not None:
            try:
                book.Close(SaveChanges=False)
            except Exception:
                pass
        if excel is not None:
            try:
                excel.ScreenUpdating = True
            except Exception:
                pass
            try:
                excel.Quit()
            except Exception:
                pass
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
