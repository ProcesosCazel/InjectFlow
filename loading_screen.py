from __future__ import annotations

import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, TypeVar
import tkinter as tk
from tkinter import ttk


APP_TITLE = "InjectFlow"
APP_VERSION = "v3.0"

# Misma línea visual de la pantalla de carga validada en v1.3.
NAVY = "#0F172A"
ACCENT = "#2563EB"
PROGRESS_BG = "#1E293B"
PROGRESS_FG = "#60A5FA"
TITLE_FG = "#FFFFFF"
SUBTITLE_FG = "#94A3B8"
STATUS_FG = "#E2E8F0"
VERSION_FG = "#64748B"

T = TypeVar("T")
StatusCallback = Callable[[str], None]
BootstrapTask = Callable[[StatusCallback], T]


@dataclass(frozen=True)
class BootstrapInfo:
    """Información mínima obtenida durante el arranque de InjectFlow."""

    root_dir: Path
    machine_count: int
    pywebview_available: bool


class LoadingScreen(Generic[T]):
    """Splash de Python que se ejecuta antes de abrir la interfaz PyWebView.

    La ventana vive en el hilo principal de Tkinter. El trabajo pesado se ejecuta
    en un hilo secundario y se comunica mediante una Queue, evitando actualizar
    widgets directamente desde el worker.
    """

    _DONE = object()
    _ERROR = object()

    def __init__(self, *, version: str = APP_VERSION) -> None:
        self.version = version
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg=NAVY)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        self._events: queue.Queue[object] = queue.Queue()
        self._result: T | None = None
        self._error: BaseException | None = None
        self._started_at = 0.0
        self._min_visible_ms = 0

        self._build_ui()
        self._center_window(600, 340)

    def _center_window(self, width: int, height: int) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=NAVY, padx=44, pady=36)
        outer.pack(fill="both", expand=True)

        brand = tk.Frame(outer, bg=NAVY)
        brand.pack(anchor="w")

        tk.Label(
            brand,
            text="IF",
            bg=ACCENT,
            fg="white",
            font=("Segoe UI Semibold", 16),
            width=3,
            height=1,
        ).pack(side="left", padx=(0, 14))

        title_box = tk.Frame(brand, bg=NAVY)
        title_box.pack(side="left")

        tk.Label(
            title_box,
            text=APP_TITLE,
            bg=NAVY,
            fg=TITLE_FG,
            font=("Segoe UI Semibold", 18),
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text="Automatización de hojas de parámetros de proceso",
            bg=NAVY,
            fg=SUBTITLE_FG,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))

        tk.Label(
            outer,
            text="Preparando la aplicación",
            bg=NAVY,
            fg=STATUS_FG,
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", pady=(48, 6))

        self.status_label = tk.Label(
            outer,
            text="Inicializando componentes…",
            bg=NAVY,
            fg=SUBTITLE_FG,
            font=("Segoe UI", 9),
        )
        self.status_label.pack(anchor="w", pady=(0, 12))

        style = ttk.Style(self.root)
        style.configure(
            "V2Splash.Horizontal.TProgressbar",
            troughcolor=PROGRESS_BG,
            background=PROGRESS_FG,
            bordercolor=PROGRESS_BG,
            lightcolor=PROGRESS_FG,
            darkcolor=PROGRESS_FG,
        )
        self.progress = ttk.Progressbar(
            outer,
            mode="indeterminate",
            style="V2Splash.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x")

        tk.Label(
            outer,
            text=self.version,
            bg=NAVY,
            fg=VERSION_FG,
            font=("Segoe UI", 8),
        ).pack(anchor="e", pady=(22, 0))

        self.root.update_idletasks()

    def _publish_status(self, text: str) -> None:
        self._events.put(str(text))

    def _worker(self, task: BootstrapTask[T]) -> None:
        try:
            self._result = task(self._publish_status)
        except BaseException as exc:  # Se vuelve a lanzar en el hilo principal.
            self._error = exc
            self._events.put(self._ERROR)
        else:
            self._events.put(self._DONE)

    def _poll_events(self) -> None:
        should_finish = False

        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break

            if event is self._DONE:
                self.status_label.configure(text="Listo. Abriendo aplicación…")
                should_finish = True
            elif event is self._ERROR:
                self.status_label.configure(text="No se pudo completar el arranque.")
                should_finish = True
            else:
                self.status_label.configure(text=str(event))

        if should_finish:
            elapsed_ms = int((time.monotonic() - self._started_at) * 1000)
            remaining_ms = max(0, self._min_visible_ms - elapsed_ms)
            self.root.after(remaining_ms, self._close)
            return

        self.root.after(50, self._poll_events)

    def _close(self) -> None:
        try:
            self.progress.stop()
            self.root.attributes("-topmost", False)
        finally:
            self.root.destroy()

    def run(self, task: BootstrapTask[T], *, min_visible_ms: int = 0) -> T:
        """Muestra el splash mientras ``task`` se ejecuta en segundo plano."""

        self._min_visible_ms = max(0, int(min_visible_ms))
        self._started_at = time.monotonic()
        self.progress.start(10)

        worker = threading.Thread(target=self._worker, args=(task,), daemon=True)
        self.root.after(100, worker.start)
        self.root.after(50, self._poll_events)
        self.root.mainloop()

        if self._error is not None:
            raise self._error
        return self._result  # type: ignore[return-value]


def runtime_root() -> Path:
    """Raíz editable del proyecto tanto en desarrollo como en PyInstaller."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bootstrap_v2(status: StatusCallback) -> BootstrapInfo:
    """Bootstrap mínimo del Paso 4, sin abrir todavía ninguna ventana WebView."""

    root_dir = runtime_root()

    status("Verificando PyWebView…")
    import webview  # noqa: F401  # PyWebView instalado en el Paso 3.

    status("Cargando catálogo de máquinas y configuración…")
    from app.catalogs import MappingCatalog

    mapping_path = root_dir / "data" / "Mapeo.xlsx"
    if not mapping_path.is_file():
        raise FileNotFoundError(f"No se encontró Mapeo.xlsx: {mapping_path}")

    molds_path = root_dir / "data" / "Moldes.xlsx"
    if not molds_path.is_file():
        raise FileNotFoundError(f"No se encontró Moldes.xlsx: {molds_path}")

    mapping = MappingCatalog(mapping_path)

    from app.mold_catalog import MoldCatalog

    MoldCatalog(molds_path)

    status("Preparando interfaz v3.0…")
    return BootstrapInfo(
        root_dir=root_dir,
        machine_count=len(mapping.machines),
        pywebview_available=True,
    )


def main() -> int:
    """Prueba aislada del Paso 4.

    En el Paso 5 este mismo módulo será reutilizado por el launcher que abrirá
    el Home HTML/CSS/JS mediante PyWebView.
    """

    try:
        info = LoadingScreen[BootstrapInfo]().run(bootstrap_v2, min_visible_ms=900)
    except Exception as exc:
        print(f"ERROR PASO 4: {exc}", file=sys.stderr)
        return 1

    print("PASO 4 OK")
    print(f"PyWebView disponible: {'SI' if info.pywebview_available else 'NO'}")
    print(f"Maquinas detectadas: {info.machine_count}")
    print(f"Proyecto: {info.root_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
