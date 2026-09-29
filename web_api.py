from __future__ import annotations

import argparse
import base64
import csv
import contextlib
import io
import json
import os
import platform
import re
import sys
import threading
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.catalogs import MappingCatalog
from app.input_policy import InputPolicy, policy_for_group
from preview_renderer import ExcelPdfPreviewRenderer


APP_NAME = "InjectFlow"
APP_VERSION = "v3.0"
APP_YEAR = "2026"
BRIDGE_API_VERSION = "1.11"
MAX_PREVIEW_PDF_BYTES = 20 * 1024 * 1024


CAPABILITIES: dict[str, bool] = {
    # Paso 7
    "manual_selectors": True,
    # Paso 8
    "file_dialogs": True,
    "drag_drop": True,
    # Paso 9
    "generation": True,
    "open_output_folder": True,
    "open_generated_output": True,
    # Paso 10
    "history": True,
    # Paso 11
    "preview": True,
}


INJECTION_CONTROL_OPTIONS: tuple[dict[str, Any], ...] = (
    {
        "value": "Modo velocidad",
        "label": "Modo velocidad",
        "code": 0,
    },
    {
        "value": "Modo presión",
        "label": "Modo presión",
        "code": 1,
    },
)


INPUT_FILE_RULES: dict[str, dict[str, str]] = {
    "param": {
        "display": "Param.dat",
        "extension": ".dat",
        "dialog_filter": "Archivo DAT (*.dat)",
    },
    "resul": {
        "display": "Resul.csv",
        "extension": ".csv",
        "dialog_filter": "Archivo CSV (*.csv)",
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InjectFlowAPI:
    """API thread-safe expuesta a JavaScript mediante PyWebView.

    Paso 6 estableció el puente JavaScript <-> Python.
    Paso 7 añadió los selectores manuales.
    Paso 8 añadió selección nativa de archivos y estado de archivos de entrada.
    Paso 9 conectó la generación real reutilizando app.main.run().
    Paso 10 migra Historial.csv a la interfaz web sin crear una segunda fuente.
    Ajustes previos al Paso 11 añaden apertura de la hoja de la sesión actual
    y borrado explícito del historial desde la interfaz.
    Paso 11 añade Vista Previa real de la hoja generada en la sesión actual.

    El Drag & Drop real se captura desde ``launcher_web.py`` mediante los eventos
    DOM de PyWebView, porque es allí donde PyWebView expone la ruta absoluta del
    archivo soltado. La validación se centraliza en esta clase para que tanto el
    diálogo nativo como Drag & Drop utilicen exactamente las mismas reglas.
    """

    def __init__(
        self,
        *,
        project_root: Path,
        mapping_path: Path,
        bridge_test: bool = False,
        selectors_test: bool = False,
        files_test: bool = False,
        generation_test: bool = False,
        history_test: bool = False,
        preview_test: bool = False,
        gen_v_test: bool = False,
        gen_iii_test: bool = False,
    ) -> None:
        self._lock = threading.RLock()
        self._session_id = uuid.uuid4().hex
        self._started_at = _utc_now()
        self._renderer = ""
        self._page_loaded = False
        self._ui_ready = False
        self._client: dict[str, Any] = {}
        self._bridge_test = bool(bridge_test)
        self._selectors_test = bool(selectors_test)
        self._files_test = bool(files_test)
        self._generation_test = bool(generation_test)
        self._history_test = bool(history_test)
        self._preview_test = bool(preview_test)
        self._gen_v_test = bool(gen_v_test)
        self._gen_iii_test = bool(gen_iii_test)
        self._ping_count = 0
        self._project_root = Path(project_root).resolve()
        self._mapping_path = Path(mapping_path)
        self._history_path = self._project_root / "data" / "Historial.csv"
        self._history_startup_warning = ""
        self._history_last_count = 0
        self._selector_cache: dict[str, Any] | None = None
        self._selected_machine = ""
        self._input_policy = InputPolicy()
        self._window: Any = None
        self._drag_drop_bound = False
        self._drag_drop_error = ""
        self._generation_running = False
        self._preview_running = False
        self._last_generation: dict[str, Any] | None = None
        self._preview_cache: dict[str, Any] | None = None
        self._input_files: dict[str, dict[str, Any] | None] = {
            "param": None,
            "resul": None,
        }

        # Conserva la política de v1.3: depurar registros >90 días al arrancar.
        self._history_startup_warning = self._cleanup_history_safely()

    # ------------------------------------------------------------------
    # Métodos públicos: se exponen automáticamente como pywebview.api.*
    # ------------------------------------------------------------------

    def bootstrap(self, client: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Handshake inicial solicitado por JavaScript."""

        normalized_client = dict(client) if isinstance(client, Mapping) else {}

        with self._lock:
            self._client = normalized_client
            renderer = self._renderer
            page_loaded = self._page_loaded
            drag_drop_bound = self._drag_drop_bound

        return {
            "ok": True,
            "bridge": {
                "apiVersion": BRIDGE_API_VERSION,
                "sessionId": self._session_id,
                "renderer": renderer,
                "pageLoaded": page_loaded,
                "testMode": self._bridge_test,
                "selectorsTest": self._selectors_test,
                "filesTest": self._files_test,
                "generationTest": self._generation_test,
                "historyTest": self._history_test,
                "previewTest": self._preview_test,
                "genVTest": self._gen_v_test,
                "genIIITest": self._gen_iii_test,
                "dragDropBound": drag_drop_bound,
            },
            "app": {
                "name": APP_NAME,
                "version": APP_VERSION,
                "year": APP_YEAR,
            },
            "capabilities": dict(CAPABILITIES),
        }

    def ping(self, payload: Any = None) -> dict[str, Any]:
        """Prueba simple JavaScript -> Python -> JavaScript."""

        with self._lock:
            self._ping_count += 1
            ping_count = self._ping_count

        return {
            "ok": True,
            "reply": "pong",
            "payload": payload,
            "count": ping_count,
            "timestamp": _utc_now(),
        }

    def notify_ui_ready(
        self,
        client: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Registra que la capa visual terminó de inicializarse."""

        normalized_client = dict(client) if isinstance(client, Mapping) else {}

        with self._lock:
            self._ui_ready = True
            if normalized_client:
                self._client.update(normalized_client)

        return {
            "ok": True,
            "uiReady": True,
            "timestamp": _utc_now(),
        }

    def get_manual_selectors(self) -> dict[str, Any]:
        """Devuelve los catálogos de los selectores manuales del Home."""

        with self._lock:
            if self._selector_cache is not None:
                return self._copy_selector_payload(self._selector_cache)

        if not self._mapping_path.is_file():
            raise FileNotFoundError(
                f"No se encontró Mapeo.xlsx: {self._mapping_path}"
            )

        mapping = MappingCatalog(self._mapping_path)

        machine_options: list[dict[str, str]] = []
        for machine in sorted(mapping.machines):
            group, template = mapping.resolve_machine(machine)
            machine_options.append(
                {
                    "value": machine,
                    "label": machine,
                    "templateGroup": group,
                    "layoutId": template.layout_id,
                    **policy_for_group(group).as_dict(),
                }
            )

        payload: dict[str, Any] = {
            "ok": True,
            "machines": machine_options,
            "injectionControls": [dict(item) for item in INJECTION_CONTROL_OPTIONS],
            "counts": {
                "machines": len(machine_options),
                "injectionControls": len(INJECTION_CONTROL_OPTIONS),
            },
            "source": {
                "machines": "data/Mapeo.xlsx",
                "sheet": "Machines",
            },
        }

        with self._lock:
            self._selector_cache = payload

        return self._copy_selector_payload(payload)

    def set_machine(self, machine: str = "") -> dict[str, Any]:
        """Synchronize the selected family and invalidate incompatible inputs.

        Changing families clears the registered paths only, never the physical
        files. Inactive machines remain inaccessible from the public bridge.
        """
        normalized = str(machine or "").strip().upper()
        with self._lock:
            if self._generation_running:
                return {"ok": False, "error": {"code": "generation_busy",
                        "message": "No se puede cambiar de maquina durante una generacion."}}
            try:
                group = MappingCatalog(self._mapping_path).resolve_machine(normalized)[0] if normalized else ""
                policy = policy_for_group(group)
            except Exception as exc:
                return {"ok": False, "error": {"code": "invalid_machine", "message": str(exc)}}
            self._selected_machine = normalized
            self._input_policy = policy
            cleared: list[str] = []
            param = self._input_files["param"]
            if param and Path(str(param["path"])).suffix.lower() != policy.param_extension:
                self._input_files["param"] = None
                cleared.append("param")
            if not policy.supports_resultants and self._input_files["resul"]:
                self._input_files["resul"] = None
                cleared.append("resul")
            return {
                "ok": True, "machine": normalized, "policy": policy.as_dict(),
                "clearedInputs": cleared,
                "files": {kind: self._copy_file_info(info) for kind, info in self._input_files.items()},
            }

    def _input_rule(self, kind: str) -> dict[str, str]:
        with self._lock:
            policy = self._input_policy
        if kind == "param":
            return {
                "display": policy.param_display,
                "extension": policy.param_extension,
                "dialog_filter": f"Archivo {policy.param_extension[1:].upper()} (*{policy.param_extension})",
            }
        return INPUT_FILE_RULES[kind]

    def _input_unavailable(self, kind: str) -> dict[str, Any] | None:
        with self._lock:
            if self._generation_running:
                return self._file_error_payload(kind, code="generation_busy",
                    title="Generacion en proceso", message="Espera a que termine la generacion antes de cambiar archivos.")
            if kind == "resul" and not self._input_policy.supports_resultants:
                return self._file_error_payload(kind, code="resultants_not_supported",
                    title="Solo parametros XML", message="Jupiter 308B/309 no utiliza archivos CSV de resultantes.")
        return None

    def select_input_file(self, kind: str) -> dict[str, Any]:
        """Abre el diálogo nativo para seleccionar Param.dat o Resul.csv."""

        normalized_kind = self._normalize_file_kind(kind)
        # Snapshot the rule and machine atomically; a family switch must not
        # associate a rule from the previous machine with the new selection.
        with self._lock:
            unavailable = self._input_unavailable(normalized_kind)
            if unavailable:
                return unavailable
            rule = self._input_rule(normalized_kind)
            selected_machine = self._selected_machine

        with self._lock:
            window = self._window

        if window is None:
            return self._file_error_payload(
                normalized_kind,
                code="window_unavailable",
                title="Ventana no disponible",
                message="InjectFlow todavía no puede abrir el selector de archivos.",
            )

        try:
            import webview

            dialog_enum = getattr(webview, "FileDialog", None)
            dialog_type = None
            if dialog_enum is not None:
                dialog_type = getattr(dialog_enum, "OPEN", None)
                if dialog_type is None:
                    # Compatibilidad defensiva con builds de PyWebView 6.x que
                    # hayan publicado el nombre LOAD para el diálogo de apertura.
                    dialog_type = getattr(dialog_enum, "LOAD", None)

            file_types = (
                rule["dialog_filter"],
                "Todos los archivos (*.*)",
            )

            kwargs = {
                "allow_multiple": False,
                "file_types": file_types,
            }
            if dialog_type is not None:
                kwargs["dialog_type"] = dialog_type

            selected = window.create_file_dialog(**kwargs)
        except Exception as exc:
            return self._file_error_payload(
                normalized_kind,
                code="dialog_error",
                title="No se pudo abrir el selector",
                message=f"No fue posible seleccionar {rule['display']}.",
                technical=str(exc),
            )

        if not selected:
            return {
                "ok": True,
                "kind": normalized_kind,
                "cancelled": True,
                "file": self._copy_file_info(self._get_input_file(normalized_kind)),
            }

        with self._lock:
            if selected_machine != self._selected_machine:
                return self._file_error_payload(normalized_kind, code="machine_changed",
                    title="Cambio de maquina", message="La maquina cambio mientras el selector estaba abierto. Selecciona de nuevo el archivo.")
        return self._accept_input_path(
            normalized_kind,
            selected[0],
            source="dialog",
        )

    def clear_input_file(self, kind: str) -> dict[str, Any]:
        """Quita el archivo seleccionado sin borrar el archivo físico."""

        normalized_kind = self._normalize_file_kind(kind)

        with self._lock:
            if self._generation_running:
                return self._file_error_payload(normalized_kind, code="generation_busy",
                    title="Generacion en proceso", message="Espera a que termine la generacion antes de quitar archivos.")
            self._input_files[normalized_kind] = None

        return {
            "ok": True,
            "kind": normalized_kind,
            "cleared": True,
            "file": None,
        }

    def get_input_files(self) -> dict[str, Any]:
        """Devuelve el estado actual de Param.dat y Resul.csv."""

        with self._lock:
            param = self._copy_file_info(self._input_files["param"])
            resul = self._copy_file_info(self._input_files["resul"])

        return {
            "ok": True,
            "files": {
                "param": param,
                "resul": resul,
            },
            "machine": self._selected_machine,
            "policy": self._input_policy.as_dict(),
        }

    def generate_sheet(
        self,
        request: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Genera HojaDeParametros.xlsx usando el motor v1.3 sin duplicar reglas.

        Zeres conserva sus resultantes opcionales. Jupiter es XML_ONLY aun
        si existe un CSV residual o el cliente solicita otro modo.
        """

        payload = dict(request) if isinstance(request, Mapping) else {}

        with self._lock:
            if self._generation_running:
                return self._generation_error_payload(
                    code="generation_busy",
                    title="Generación en proceso",
                    message="InjectFlow ya está generando una hoja de parámetros.",
                )
            self._generation_running = True

        pythoncom = None
        stdout = io.StringIO()
        stderr = io.StringIO()

        try:
            self._emit_generation_progress(5, "Validando información del proceso…")

            machine = str(payload.get("machine", "") or "").strip().upper()
            mold = str(payload.get("mold", "") or "").strip()
            injection_raw = payload.get("injectionControl", "")

            with self._lock:
                param_info = self._copy_file_info(self._input_files["param"])
                resul_info = self._copy_file_info(self._input_files["resul"])

            # Resolve policy from the requested machine on every generation;
            # never trust client mode flags or the presence of a cached CSV.
            missing: list[str] = []
            if not machine:
                missing.append("Máquina")
            if not mold:
                missing.append("Molde")
            mapping = MappingCatalog(self._mapping_path)
            policy = InputPolicy()
            if machine:
                template_group, template_def = mapping.resolve_machine(machine)
                policy = policy_for_group(template_group)
            if not param_info:
                missing.append(policy.param_display)
            if policy.requires_injection_control:
                injection_label, injection_code = self._resolve_injection_control(injection_raw)
                if injection_code is None:
                    missing.append("Control de inyección")
            else:
                injection_label, injection_code = "Segun XML (U1/U2)", None

            if missing:
                return self._generation_error_payload(
                    code="missing_inputs",
                    title="Faltan datos para generar",
                    message="Completa la información obligatoria antes de generar la hoja.",
                    missing_parameters=missing,
                )

            param_path = Path(str(param_info["path"])).resolve()
            policy.validate_param_path(param_path)
            if not param_path.is_file():
                return self._generation_error_payload(
                    code="param_not_found",
                    title=f"{policy.param_display} no encontrado",
                    message=f"El archivo seleccionado ya no existe: {param_path}",
                )

            resul_path: Path | None = None
            if resul_info and policy.supports_resultants:
                resul_path = Path(str(resul_info["path"])).resolve()
                if not resul_path.is_file():
                    return self._generation_error_payload(
                        code="resul_not_found",
                        title="Resul.csv no encontrado",
                        message=f"El archivo seleccionado ya no existe: {resul_path}",
                    )

            param_only = not policy.supports_resultants or resul_path is None
            execution_mode = policy.execution_mode(not param_only)
            display_mode = policy.display_mode(not param_only)

            self._emit_generation_progress(16, f"Modo: {display_mode}")

            root = self._project_root
            output_dir = root / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            from app.history import build_dynamic_output_path

            output_path = build_dynamic_output_path(
                output_dir,
                mold=mold,
                machine=machine,
            )

            args = argparse.Namespace(
                machine=machine,
                mold=mold,
                injection_control_mode=injection_code,
                data=root / "data" / "Data.xlsx",
                mapping=root / "data" / "Mapeo.xlsx",
                molds=root / "data" / "Moldes.xlsx",
                param=param_path,
                resul=resul_path if not param_only else None,
                # Regla explícita que reemplaza semánticamente la checkbox v1.3.
                param_only=param_only,
                templates_dir=root / "plantillas",
                output=output_path,
                history=root / "data" / "Historial.csv",
                report=output_dir / "Reporte_Validacion.txt",
                plan_csv=output_dir / "Plan_Escritura.csv",
                plan_only=False,
                allow_template_mismatch=False,
            )

            self._emit_generation_progress(28, "Preparando motor de generación…")

            if sys.platform == "win32":
                import pythoncom as _pythoncom  # type: ignore

                pythoncom = _pythoncom
                pythoncom.CoInitialize()

            from app.errors import ProcessWarning
            from app.main import run

            self._emit_generation_progress(
                42,
                "Generando y verificando la hoja de parámetros…",
                indeterminate=True,
            )

            try:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    result = run(args)
            except ProcessWarning as exc:
                detail = str(exc)
                self._emit_generation_progress(100, "Generación detenida por advertencia.")
                return self._generation_error_payload(
                    code="process_warning",
                    title="Revisar configuración de máquina",
                    message=detail,
                    status="warning",
                    technical=stderr.getvalue().strip(),
                    mode=display_mode,
                    param_only=param_only,
                )

            if result != 0:
                raise RuntimeError(
                    stderr.getvalue().strip()
                    or stdout.getvalue().strip()
                    or "El motor terminó con un código de error."
                )

            log = stdout.getvalue().strip()
            process_warnings = [
                line.removeprefix("ADVERTENCIA PROCESO:").strip()
                for line in log.splitlines()
                if line.startswith("ADVERTENCIA PROCESO:")
            ]
            parameter_warnings = [
                line.removeprefix("ADVERTENCIA PARAMETRO:").strip()
                for line in log.splitlines()
                if line.startswith("ADVERTENCIA PARAMETRO:")
            ]
            history_warning = next(
                (
                    line.removeprefix("ADVERTENCIA HISTORIAL:").strip()
                    for line in log.splitlines()
                    if line.startswith("ADVERTENCIA HISTORIAL:")
                ),
                "",
            )

            if not output_path.is_file():
                raise RuntimeError(
                    "El motor terminó sin error, pero el archivo de salida no fue encontrado."
                )

            checked_cells = self._extract_int_from_log(
                log,
                r"Verificacion Excel OK:\s*(\d+)\s+celdas",
            )
            operation_count = self._extract_int_from_log(
                log,
                r"Operaciones planeadas:\s*(\d+)",
            )

            status = (
                "warning"
                if process_warnings or parameter_warnings or history_warning
                else "success"
            )

            result_payload: dict[str, Any] = {
                "ok": True,
                "generated": True,
                "status": status,
                "mode": display_mode,
                "engineMode": execution_mode,
                "paramOnly": param_only,
                "machine": machine,
                "mold": mold,
                "injectionControl": {
                    "label": injection_label,
                    "code": injection_code,
                },
                "template": {
                    "group": template_group,
                    "layoutId": template_def.layout_id,
                    "file": template_def.template_file,
                },
                "output": {
                    "name": output_path.name,
                    "path": str(output_path),
                    "exists": True,
                },
                "report": {
                    "path": str(args.report),
                },
                "plan": {
                    "path": str(args.plan_csv),
                    "operations": operation_count,
                },
                "history": {
                    "path": str(args.history),
                    "warning": history_warning,
                },
                "verification": {
                    "checkedCells": checked_cells,
                },
                "processWarnings": process_warnings,
                "parameterWarnings": parameter_warnings,
                "warningCount": len(process_warnings) + len(parameter_warnings),
                "generationTest": self._generation_test,
                "timestamp": _utc_now(),
            }

            with self._lock:
                self._last_generation = {
                    "status": status,
                    "mode": display_mode,
                    "machine": machine,
                    "mold": mold,
                    "outputName": output_path.name,
                    "outputPath": str(output_path),
                    "warningCount": len(process_warnings) + len(parameter_warnings),
                    "timestamp": result_payload["timestamp"],
                }
                self._preview_cache = None

            self._emit_generation_progress(100, "Hoja generada y verificada correctamente.")
            return result_payload

        except Exception as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            extra = stderr.getvalue().strip()
            if extra and extra not in detail:
                technical = f"{detail}\n\n{extra}"
            else:
                technical = detail

            self._emit_generation_progress(100, "No se pudo generar la hoja.")
            return self._generation_error_payload(
                code="generation_error",
                title="No se pudo generar la hoja",
                message=detail,
                technical=technical,
            )
        finally:
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

            with self._lock:
                self._generation_running = False

    def get_latest_output(self) -> dict[str, Any]:
        """Devuelve solo la hoja generada durante la sesión actual.

        La Home de InjectFlow no recupera hojas de sesiones anteriores. Las
        generaciones históricas se consultan y abren exclusivamente desde la
        pantalla Historial mediante ``get_history`` / ``open_history_output``.
        """

        resolved = self._resolve_latest_output()
        if resolved is None:
            return {
                "ok": True,
                "available": False,
                "output": None,
            }

        return {
            "ok": True,
            "available": True,
            "output": resolved,
        }

    def open_latest_output(self) -> dict[str, Any]:
        """Abre solo la hoja generada durante la sesión actual."""

        resolved = self._resolve_latest_output()
        if resolved is None:
            return {
                "ok": False,
                "error": {
                    "code": "generated_output_missing",
                    "title": "No hay una hoja disponible en esta sesión",
                    "message": (
                        "Genera una hoja de parámetros en esta sesión antes de "
                        "utilizar Abrir hoja. Para hojas de sesiones anteriores, "
                        "utiliza Historial."
                    ),
                },
            }

        output_path = Path(str(resolved.get("path", ""))).resolve()
        output_dir = (self._project_root / "output").resolve()

        if (
            output_path.parent != output_dir
            or output_path.suffix.lower() != ".xlsx"
            or not output_path.is_file()
        ):
            return {
                "ok": False,
                "error": {
                    "code": "generated_output_invalid",
                    "title": "Hoja no disponible",
                    "message": (
                        "La hoja generada durante esta sesión ya no se encuentra "
                        "disponible en la carpeta output."
                    ),
                },
            }

        if sys.platform != "win32":
            return {
                "ok": False,
                "error": {
                    "code": "unsupported_platform",
                    "title": "Función no disponible",
                    "message": "Abrir la hoja está disponible en la versión Windows de InjectFlow.",
                },
            }

        try:
            os.startfile(str(output_path))  # type: ignore[attr-defined]
        except Exception as exc:
            return {
                "ok": False,
                "error": {
                    "code": "generated_output_open_error",
                    "title": "No se pudo abrir la hoja",
                    "message": str(exc),
                },
            }

        return {
            "ok": True,
            "name": output_path.name,
            "path": str(output_path),
            "source": "session",
        }

    def get_current_preview(self) -> dict[str, Any]:
        """Genera/recupera la vista previa de la hoja de la sesión actual.

        La Home nunca utiliza archivos históricos para este método. El PDF se
        genera temporalmente y se devuelve en base64; no se conserva un archivo
        PDF permanente dentro del proyecto.
        """

        with self._lock:
            if self._generation_running:
                return {
                    "ok": False,
                    "error": {
                        "code": "preview_generation_busy",
                        "title": "Vista previa no disponible",
                        "message": (
                            "Espera a que termine la generación actual antes de "
                            "abrir la vista previa."
                        ),
                    },
                }
            if self._preview_running:
                return {
                    "ok": False,
                    "retryable": True,
                    "error": {
                        "code": "preview_busy",
                        "title": "Vista previa ocupada",
                        "message": "La vista previa ya se está preparando.",
                    },
                }

        resolved = self._resolve_latest_output()
        if resolved is None:
            return {
                "ok": False,
                "error": {
                    "code": "preview_output_missing",
                    "title": "Vista previa no disponible",
                    "message": (
                        "Genera una hoja de parámetros en esta sesión antes de "
                        "abrir la vista previa. Las hojas anteriores se consultan "
                        "desde Historial."
                    ),
                },
            }

        output_path = Path(str(resolved.get("path", ""))).resolve()
        output_dir = (self._project_root / "output").resolve()
        if (
            output_path.parent != output_dir
            or output_path.suffix.lower() != ".xlsx"
            or not output_path.is_file()
        ):
            return {
                "ok": False,
                "error": {
                    "code": "preview_output_invalid",
                    "title": "Vista previa no disponible",
                    "message": "La hoja generada durante esta sesión ya no está disponible.",
                },
            }

        with self._lock:
            if self._preview_running:
                return {
                    "ok": False,
                    "retryable": True,
                    "error": {
                        "code": "preview_busy",
                        "title": "Vista previa ocupada",
                        "message": "La vista previa ya se está preparando.",
                    },
                }
            self._preview_running = True

        try:
            stat = output_path.stat()
            cache_key = f"{output_path}|{stat.st_mtime_ns}|{stat.st_size}"

            with self._lock:
                cached = dict(self._preview_cache) if self._preview_cache else None

            if cached and cached.get("key") == cache_key:
                return {
                    "ok": True,
                    "available": True,
                    "cached": True,
                    "preview": dict(cached["payload"]),
                }

            document = ExcelPdfPreviewRenderer().render(output_path)
            if document.size_bytes > MAX_PREVIEW_PDF_BYTES:
                raise RuntimeError(
                    "La vista previa excede el tamaño máximo permitido de 20 MB."
                )
            encoded = base64.b64encode(document.content).decode("ascii")
            payload = {
                "name": output_path.name,
                "sheet": document.sheet_name,
                "mimeType": "application/pdf",
                "base64": encoded,
                "sizeBytes": document.size_bytes,
                "source": "session",
            }

            with self._lock:
                self._preview_cache = {
                    "key": cache_key,
                    "payload": dict(payload),
                }

            return {
                "ok": True,
                "available": True,
                "cached": False,
                "preview": payload,
            }
        except Exception as exc:
            return {
                "ok": False,
                "retryable": True,
                "error": {
                    "code": "preview_render_error",
                    "title": "No se pudo crear la vista previa",
                    "message": str(exc),
                },
            }
        finally:
            with self._lock:
                self._preview_running = False

    def open_output_folder(self) -> dict[str, Any]:
        """Abre la carpeta output en Windows."""

        output_dir = self._project_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        if sys.platform != "win32":
            return {
                "ok": False,
                "error": {
                    "code": "unsupported_platform",
                    "title": "Función no disponible",
                    "message": "Abrir la carpeta está disponible en la versión Windows de InjectFlow.",
                },
            }

        try:
            os.startfile(str(output_dir))  # type: ignore[attr-defined]
        except Exception as exc:
            return {
                "ok": False,
                "error": {
                    "code": "output_folder_open_error",
                    "title": "No se pudo abrir la carpeta",
                    "message": str(exc),
                },
            }

        return {
            "ok": True,
            "path": str(output_dir),
        }

    def get_history(self) -> dict[str, Any]:

        """Devuelve el historial real de generaciones para la pantalla web.

        Mantiene la misma fuente de v1.3 (data/Historial.csv) y aplica la
        retención de 90 días antes de leer. Los archivos Excel generados nunca
        se eliminan desde esta función.
        """

        from app.history import HISTORY_FIELDS, HISTORY_RETENTION_DAYS

        cleanup_warning = self._cleanup_history_safely()
        history_path = self._history_path
        output_dir = (self._project_root / "output").resolve()

        rows: list[dict[str, str]] = []
        if history_path.is_file():
            try:
                with history_path.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        if not row:
                            continue
                        rows.append(
                            {
                                field: str(row.get(field, "") or "").strip()
                                for field in HISTORY_FIELDS
                            }
                        )
            except Exception as exc:
                return {
                    "ok": False,
                    "error": {
                        "code": "history_read_error",
                        "title": "No se pudo leer el historial",
                        "message": str(exc),
                    },
                    "items": [],
                    "count": 0,
                    "retentionDays": int(HISTORY_RETENTION_DAYS),
                    "source": str(history_path),
                }

        # app.history agrega al final; la UI muestra primero lo más reciente.
        rows.reverse()
        items: list[dict[str, Any]] = []

        for row in rows:
            file_name = row.get("ARCHIVO_GENERADO", "").strip()
            safe_name = Path(file_name).name if file_name else ""
            safe_file_name = safe_name if safe_name == file_name else ""
            output_path = output_dir / safe_file_name if safe_file_name else None
            output_exists = bool(output_path and output_path.is_file())

            items.append(
                {
                    "timestamp": row.get("FECHA_HORA", ""),
                    "machine": row.get("MAQUINA", ""),
                    "mold": row.get("MOLDE", ""),
                    "mode": row.get("MODO", ""),
                    "file": {
                        "name": file_name,
                        "path": str(output_path) if output_path else "",
                        "exists": output_exists,
                    },
                }
            )

        with self._lock:
            self._history_last_count = len(items)
            if cleanup_warning:
                self._history_startup_warning = cleanup_warning

        return {
            "ok": True,
            "items": items,
            "count": len(items),
            "retentionDays": int(HISTORY_RETENTION_DAYS),
            "source": str(history_path),
            "cleanupWarning": cleanup_warning or self._history_startup_warning,
            "historyTest": self._history_test,
        }

    def clear_history(self) -> dict[str, Any]:
        """Borra todos los registros del historial sin eliminar archivos Excel.

        La fuente sigue siendo ``data/Historial.csv``. Se elimina únicamente el
        archivo CSV; ``append_generation_history`` lo recreará automáticamente
        cuando exista una nueva generación exitosa.
        """

        history_path = self._history_path

        with self._lock:
            removed_count = int(self._history_last_count)

        try:
            history_path.unlink(missing_ok=True)
        except Exception as exc:
            return {
                "ok": False,
                "error": {
                    "code": "history_clear_error",
                    "title": "No se pudo borrar el historial",
                    "message": str(exc),
                },
            }

        with self._lock:
            self._history_last_count = 0
            self._history_startup_warning = ""

        return {
            "ok": True,
            "removedCount": removed_count,
            "source": str(history_path),
            "filesDeleted": False,
        }

    def open_history_output(self, file_name: str) -> dict[str, Any]:
        """Abre un Excel generado desde una entrada del historial."""

        requested = str(file_name or "").strip()
        safe_name = Path(requested).name

        if not requested or safe_name != requested or Path(safe_name).suffix.lower() != ".xlsx":
            return {
                "ok": False,
                "error": {
                    "code": "invalid_history_output",
                    "title": "Archivo no válido",
                    "message": "La referencia del historial no corresponde a un archivo Excel válido.",
                },
            }

        output_dir = (self._project_root / "output").resolve()
        output_path = (output_dir / safe_name).resolve()

        if output_path.parent != output_dir or not output_path.is_file():
            return {
                "ok": False,
                "error": {
                    "code": "history_output_missing",
                    "title": "Archivo no disponible",
                    "message": (
                        "El registro existe en el historial, pero el archivo generado "
                        "ya no se encuentra en la carpeta output."
                    ),
                },
            }

        if sys.platform != "win32":
            return {
                "ok": False,
                "error": {
                    "code": "unsupported_platform",
                    "title": "Función no disponible",
                    "message": "Abrir hojas del historial está disponible en Windows.",
                },
            }

        try:
            os.startfile(str(output_path))  # type: ignore[attr-defined]
        except Exception as exc:
            return {
                "ok": False,
                "error": {
                    "code": "history_output_open_error",
                    "title": "No se pudo abrir la hoja",
                    "message": str(exc),
                },
            }

        return {
            "ok": True,
            "name": safe_name,
            "path": str(output_path),
        }

    def get_status(self) -> dict[str, Any]:
        """Devuelve diagnóstico no sensible del puente."""

        with self._lock:
            selector_cache = self._selector_cache
            input_param = self._input_files["param"]
            input_resul = self._input_files["resul"]
            return {
                "ok": True,
                "bridge": {
                    "apiVersion": BRIDGE_API_VERSION,
                    "sessionId": self._session_id,
                    "renderer": self._renderer,
                    "pageLoaded": self._page_loaded,
                    "uiReady": self._ui_ready,
                    "pingCount": self._ping_count,
                    "startedAt": self._started_at,
                    "testMode": self._bridge_test,
                    "selectorsTest": self._selectors_test,
                    "filesTest": self._files_test,
                    "generationTest": self._generation_test,
                    "historyTest": self._history_test,
                    "previewTest": self._preview_test,
                    "genVTest": self._gen_v_test,
                    "genIIITest": self._gen_iii_test,
                },
                "selectors": {
                    "loaded": selector_cache is not None,
                    "machineCount": (
                        int(selector_cache.get("counts", {}).get("machines", 0))
                        if selector_cache
                        else 0
                    ),
                    "injectionControlCount": (
                        int(
                            selector_cache.get("counts", {}).get(
                                "injectionControls", 0
                            )
                        )
                        if selector_cache
                        else 0
                    ),
                },
                "files": {
                    "dragDropBound": self._drag_drop_bound,
                    "dragDropError": self._drag_drop_error,
                    "paramSelected": input_param is not None,
                    "resulSelected": input_resul is not None,
                    "paramSource": (
                        str(input_param.get("source", "")) if input_param else ""
                    ),
                    "resulSource": (
                        str(input_resul.get("source", "")) if input_resul else ""
                    ),
                },
                "generation": {
                    "running": self._generation_running,
                    "last": dict(self._last_generation) if self._last_generation else None,
                },
                "history": {
                    "path": str(self._history_path),
                    "count": self._history_last_count,
                    "startupWarning": self._history_startup_warning,
                },
                "preview": {
                    "enabled": CAPABILITIES["preview"],
                    "cached": self._preview_cache is not None,
                    "running": self._preview_running,
                    "sessionOutputAvailable": self._resolve_latest_output() is not None,
                },
                "runtime": {
                    "python": platform.python_version(),
                    "platform": platform.system(),
                },
            }

    # ------------------------------------------------------------------
    # Métodos privados: NO se exponen a JavaScript.
    # ------------------------------------------------------------------

    def _resolve_latest_output(self) -> dict[str, Any] | None:
        """Resuelve únicamente la hoja generada en la sesión actual."""

        output_dir = (self._project_root / "output").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        with self._lock:
            session_last = dict(self._last_generation) if self._last_generation else None

        if not session_last:
            return None

        session_path_text = str(session_last.get("outputPath", "") or "").strip()
        if not session_path_text:
            return None

        session_path = Path(session_path_text).resolve()
        if (
            session_path.parent == output_dir
            and session_path.suffix.lower() == ".xlsx"
            and session_path.is_file()
        ):
            return {
                "name": session_path.name,
                "path": str(session_path),
                "exists": True,
                "source": "session",
            }

        return None

    @staticmethod
    def _copy_selector_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "ok": bool(payload.get("ok", False)),
            "machines": [dict(item) for item in payload.get("machines", [])],
            "injectionControls": [
                dict(item) for item in payload.get("injectionControls", [])
            ],
            "counts": dict(payload.get("counts", {})),
            "source": dict(payload.get("source", {})),
        }

    @staticmethod
    def _copy_file_info(file_info: Mapping[str, Any] | None) -> dict[str, Any] | None:
        return dict(file_info) if file_info else None

    @staticmethod
    def _normalize_file_kind(kind: str) -> str:
        normalized = str(kind or "").strip().lower()
        if normalized not in INPUT_FILE_RULES:
            raise ValueError(f"Tipo de archivo no válido: {kind}")
        return normalized

    def _get_input_file(self, kind: str) -> dict[str, Any] | None:
        with self._lock:
            return self._copy_file_info(self._input_files[kind])

    def _file_error_payload(
        self,
        kind: str,
        *,
        code: str,
        title: str,
        message: str,
        technical: str = "",
        file_name: str = "",
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "kind": kind,
            "cancelled": False,
            "file": None,
            "error": {
                "code": code,
                "title": title,
                "message": message,
                "technical": technical,
                "fileName": file_name,
            },
        }

    def _accept_input_path(
        self,
        kind: str,
        raw_path: Any,
        *,
        source: str,
        dropped_count: int = 1,
    ) -> dict[str, Any]:
        """Valida y registra un archivo de entrada.

        Esta función centraliza las reglas tanto para el diálogo como para
        Drag & Drop y conserva la conducta validada de v1.3: se valida por
        extensión y existencia del archivo, no por nombre literal.
        """

        normalized_kind = self._normalize_file_kind(kind)
        # Snapshot the rule and machine atomically; a family switch must not
        # associate a rule from the previous machine with the new selection.
        with self._lock:
            unavailable = self._input_unavailable(normalized_kind)
            if unavailable:
                return unavailable
            rule = self._input_rule(normalized_kind)
            selected_machine = self._selected_machine

        if raw_path is None or not str(raw_path).strip():
            return self._file_error_payload(
                normalized_kind,
                code="missing_path",
                title="No se pudo leer el archivo",
                message=(
                    "PyWebView no proporcionó la ruta completa del archivo "
                    "seleccionado o arrastrado."
                ),
            )

        path = Path(str(raw_path)).expanduser()

        if path.suffix.lower() != rule["extension"]:
            return self._file_error_payload(
                normalized_kind,
                code="wrong_extension",
                title="Archivo incorrecto",
                message=(
                    f"Se esperaba un archivo {rule['extension']} para "
                    f"{rule['display']} y se seleccionó: {path.name}"
                ),
                file_name=path.name,
            )

        if not path.is_file():
            return self._file_error_payload(
                normalized_kind,
                code="file_not_found",
                title="Archivo no encontrado",
                message=f"No se encontró el archivo seleccionado: {path}",
                file_name=path.name,
            )

        resolved = path.resolve()
        stat = resolved.stat()
        info: dict[str, Any] = {
            "name": resolved.name,
            "path": str(resolved),
            "extension": resolved.suffix.lower(),
            "size": int(stat.st_size),
            "source": str(source),
            "selectedAt": _utc_now(),
        }

        with self._lock:
            unavailable = self._input_unavailable(normalized_kind)
            if unavailable:
                return unavailable
            if selected_machine != self._selected_machine:
                return self._file_error_payload(normalized_kind, code="machine_changed",
                    title="Cambio de maquina", message="Selecciona de nuevo el archivo para la maquina actual.")
            self._input_files[normalized_kind] = info

        return {
            "ok": True,
            "kind": normalized_kind,
            "cancelled": False,
            "file": dict(info),
            "ignoredCount": max(0, int(dropped_count) - 1),
        }

    def _accept_dropped_file(
        self,
        kind: str,
        raw_path: Any,
        *,
        dropped_count: int = 1,
    ) -> dict[str, Any]:
        return self._accept_input_path(
            kind,
            raw_path,
            source="drop",
            dropped_count=dropped_count,
        )

    @staticmethod
    def _extract_int_from_log(log: str, pattern: str) -> int | None:
        match = re.search(pattern, log, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _resolve_injection_control(raw: Any) -> tuple[str, int | None]:
        text = str(raw if raw is not None else "").strip()
        if not text:
            return "", None

        for item in INJECTION_CONTROL_OPTIONS:
            if text in {str(item["value"]), str(item["label"]), str(item["code"])}:
                return str(item["label"]), int(item["code"])

        return text, None

    def _generation_error_payload(
        self,
        *,
        code: str,
        title: str,
        message: str,
        status: str = "error",
        technical: str = "",
        missing_parameters: list[str] | None = None,
        mode: str = "",
        param_only: bool | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "generated": False,
            "status": status,
            "mode": mode,
            "paramOnly": param_only,
            "missingParameters": list(missing_parameters or []),
            "error": {
                "code": code,
                "title": title,
                "message": message,
                "technical": technical,
            },
            "generationTest": self._generation_test,
            "genVTest": self._gen_v_test,
            "genIIITest": self._gen_iii_test,
            "timestamp": _utc_now(),
        }

    def _emit_generation_progress(
        self,
        percent: int,
        message: str,
        *,
        indeterminate: bool = False,
    ) -> None:
        with self._lock:
            window = self._window

        if window is None:
            return

        payload = {
            "percent": max(0, min(100, int(percent))),
            "message": str(message),
            "indeterminate": bool(indeterminate),
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        try:
            window.run_js(
                "window.InjectFlowBridge && "
                f"window.InjectFlowBridge.receiveGenerationProgress({encoded});"
            )
        except Exception:
            # El progreso es auxiliar; nunca debe romper la generación real.
            pass

    def _cleanup_history_safely(self) -> str:
        """Aplica retención del historial sin impedir que InjectFlow arranque."""

        try:
            from app.history import cleanup_generation_history

            count = cleanup_generation_history(self._history_path)
            with self._lock:
                self._history_last_count = int(count)
                self._history_startup_warning = ""
            return ""
        except Exception as exc:
            return f"No se pudo aplicar la limpieza automática del historial: {exc}"

    def _attach_window(self, window: Any) -> None:
        with self._lock:
            self._window = window

    def _set_renderer(self, renderer: Any) -> None:
        with self._lock:
            self._renderer = str(renderer or "")

    def _set_page_loaded(self, loaded: bool = True) -> None:
        with self._lock:
            self._page_loaded = bool(loaded)

    def _set_drag_drop_state(self, bound: bool, error: str = "") -> None:
        with self._lock:
            self._drag_drop_bound = bool(bound)
            self._drag_drop_error = str(error or "")
