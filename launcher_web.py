from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _prepare_windowed_stdio() -> None:
    """Evita errores cuando PyInstaller ejecuta sin consola en Windows."""

    if not getattr(sys, "frozen", False):
        return

    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


_prepare_windowed_stdio()

from loading_screen import BootstrapInfo, LoadingScreen, bootstrap_v2
from preview_renderer import run_preview_worker
from web_api import APP_NAME, APP_VERSION, InjectFlowAPI


WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 820
WINDOW_MIN_SIZE = (720, 520)
WINDOW_BACKGROUND = "#eef2f7"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="InjectFlow v3.0 - Launcher PyWebView",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Activa las herramientas de depuración de PyWebView.",
    )
    parser.add_argument(
        "--bridge-test",
        action="store_true",
        help="Muestra una confirmación visual cuando el puente bidireccional queda listo.",
    )
    parser.add_argument(
        "--selectors-test",
        action="store_true",
        help="Muestra una confirmación visual cuando los selectores manuales quedan cargados.",
    )
    parser.add_argument(
        "--files-test",
        action="store_true",
        help="Activa la validación guiada del Paso 8 para selección y Drag & Drop.",
    )
    parser.add_argument(
        "--generation-test",
        action="store_true",
        help="Activa la validación guiada del Paso 9 para generación real de Excel.",
    )
    parser.add_argument(
        "--history-test",
        action="store_true",
        help="Activa la validación guiada del Paso 10 para historial de generación.",
    )
    parser.add_argument(
        "--preview-test",
        action="store_true",
        help="Activa la validación guiada del Paso 11 para Vista Previa real.",
    )
    parser.add_argument(
        "--gen-v-test",
        action="store_true",
        help="Activa la validación guiada del Paso 12 para Haitian Zeres Gen V.",
    )
    parser.add_argument(
        "--gen-iii-test",
        action="store_true",
        help="Activa la validación guiada del Paso 13 para Haitian Zeres Gen III.",
    )
    parser.add_argument("--preview-worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--preview-output", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--preview-metadata", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--preview-excel-pid", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args()


def _bootstrap_web(status) -> BootstrapInfo:
    """Reutiliza el bootstrap del Paso 4 y verifica los archivos del Home."""

    info = bootstrap_v2(status)

    status("Verificando interfaz web de InjectFlow…")
    required = (
        info.root_dir / "web" / "index.html",
        info.root_dir / "web" / "js" / "main.js",
        info.root_dir / "web" / "css" / "styles.css",
    )

    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Faltan archivos necesarios de la interfaz web:\n- "
            + "\n- ".join(missing)
        )

    status("Preparando puente JavaScript ↔ Python…")
    return info


def _show_startup_error(exc: BaseException) -> None:
    """Fallback nativo si la interfaz web todavía no puede arrancar."""

    message = f"InjectFlow no pudo iniciar.\n\n{exc}"
    print(message, file=sys.stderr)

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("InjectFlow", message, parent=root)
        root.destroy()
    except Exception:
        # Si incluso Tkinter falla, el mensaje de stderr sigue disponible.
        pass


def _python_signal(api: InjectFlowAPI) -> dict[str, object]:
    status = api.get_status()
    bridge = status.get("bridge", {})
    files = status.get("files", {})
    return {
        "source": "python",
        "event": "page-loaded",
        "renderer": bridge.get("renderer", ""),
        "apiVersion": bridge.get("apiVersion", ""),
        "testMode": bridge.get("testMode", False),
        "selectorsTest": bridge.get("selectorsTest", False),
        "filesTest": bridge.get("filesTest", False),
        "generationTest": bridge.get("generationTest", False),
        "historyTest": bridge.get("historyTest", False),
        "previewTest": bridge.get("previewTest", False),
        "genVTest": bridge.get("genVTest", False),
        "genIIITest": bridge.get("genIIITest", False),
        "dragDropBound": files.get("dragDropBound", False),
        "dragDropError": files.get("dragDropError", ""),
    }


def _send_bridge_payload(window: Any, method: str, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        separators=(",", ":"),
    )

    window.run_js(
        "window.InjectFlowBridge && "
        f"window.InjectFlowBridge.{method}({encoded});"
    )


def _drop_files(event: Any) -> list[Mapping[str, Any]]:
    """Extrae archivos del evento DOM de PyWebView de forma defensiva."""

    if not isinstance(event, Mapping):
        return []

    transfer = event.get("dataTransfer")
    if not isinstance(transfer, Mapping):
        # Algunas páginas de documentación histórica usan domTransfer.
        transfer = event.get("domTransfer")

    if not isinstance(transfer, Mapping):
        return []

    files = transfer.get("files", [])
    if not isinstance(files, (list, tuple)):
        return []

    return [item for item in files if isinstance(item, Mapping)]


def _bind_file_drop_handlers(window: Any, api: InjectFlowAPI) -> None:
    """Conecta Drag & Drop nativo de PyWebView a las dos zonas del Home.

    PyWebView incorpora ``pywebviewFullPath`` al evento ``drop`` capturado en
    Python. Ese valor permite conservar una ruta absoluta real para el Paso 9.
    """

    from webview.dom import DOMEventHandler

    zones = {
        "param": "#param-drop-zone",
        "resul": "#resul-drop-zone",
    }

    def on_drag(_event: Any) -> None:
        # La parte visual (.drag-over) se controla en main.js.
        return None

    for kind, selector in zones.items():
        element = window.dom.get_element(selector)
        if element is None:
            raise RuntimeError(
                f"No se encontró la zona Drag & Drop requerida: {selector}"
            )

        def on_drop(event: Any, *, file_kind: str = kind) -> None:
            files = _drop_files(event)

            if not files:
                result = api._accept_dropped_file(
                    file_kind,
                    None,
                    dropped_count=0,
                )
            else:
                first = files[0]
                full_path = first.get("pywebviewFullPath")
                result = api._accept_dropped_file(
                    file_kind,
                    full_path,
                    dropped_count=len(files),
                )

            _send_bridge_payload(
                window,
                "receiveFileSelection",
                result,
            )

        element.events.dragenter += DOMEventHandler(
            on_drag,
            prevent_default=True,
            stop_propagation=False,
        )
        element.events.dragover += DOMEventHandler(
            on_drag,
            prevent_default=True,
            stop_propagation=False,
            debounce=80,
        )
        element.events.drop += DOMEventHandler(
            on_drop,
            prevent_default=True,
            stop_propagation=False,
        )

    api._set_drag_drop_state(True)


def main() -> int:
    args = _parse_args()

    if args.preview_worker is not None:
        if (
            args.preview_output is None
            or args.preview_metadata is None
            or args.preview_excel_pid is None
        ):
            return 2
        return run_preview_worker(
            workbook_path=args.preview_worker,
            pdf_path=args.preview_output,
            metadata_path=args.preview_metadata,
            excel_pid_path=args.preview_excel_pid,
        )

    try:
        info = LoadingScreen[BootstrapInfo](version=APP_VERSION).run(
            _bootstrap_web,
            min_visible_ms=700,
        )
    except Exception as exc:
        _show_startup_error(exc)
        return 1

    try:
        import webview

        api = InjectFlowAPI(
            project_root=info.root_dir,
            mapping_path=info.root_dir / "data" / "Mapeo.xlsx",
            bridge_test=args.bridge_test,
            selectors_test=args.selectors_test,
            files_test=args.files_test,
            generation_test=args.generation_test,
            history_test=args.history_test,
            preview_test=args.preview_test,
            gen_v_test=args.gen_v_test,
            gen_iii_test=args.gen_iii_test,
        )
        index_path = info.root_dir / "web" / "index.html"

        window = webview.create_window(
            APP_NAME,
            url=str(index_path),
            js_api=api,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=WINDOW_MIN_SIZE,
            resizable=True,
            background_color=WINDOW_BACKGROUND,
            text_select=True,
            zoomable=False,
        )
        api._attach_window(window)

        def on_initialized(renderer) -> None:
            api._set_renderer(renderer)

        def on_loaded(window) -> None:
            api._set_page_loaded(True)

            try:
                _bind_file_drop_handlers(window, api)
            except Exception as exc:
                api._set_drag_drop_state(False, str(exc))
                print(f"[InjectFlow] Drag & Drop no disponible: {exc}", file=sys.stderr)

            _send_bridge_payload(
                window,
                "receivePythonSignal",
                _python_signal(api),
            )

        window.events.initialized += on_initialized
        window.events.loaded += on_loaded

        # Servimos los archivos locales con el servidor HTTP interno de PyWebView.
        # Esto mantiene index.html, CSS, JS e imágenes como archivos separados.
        webview.start(
            debug=args.debug,
            http_server=True,
            private_mode=True,
        )
        return 0

    except Exception as exc:
        _show_startup_error(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
