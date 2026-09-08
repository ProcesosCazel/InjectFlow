from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .excel_writer import WriteVerification
from .plan import GenerationPlan


def write_report(
    path: Path,
    *,
    machine: str,
    mold_number: str,
    template_group: str,
    template_file: str,
    param_values: dict[str, Any],
    resul_values: dict[str, Any],
    plan: GenerationPlan,
    execution_mode: str = "PARAMETROS + RESULTANTES",
    injection_control_mode: str | None = None,
    template_warnings: tuple[str, ...] = (),
    parameter_warnings: tuple[str, ...] = (),
    verification: WriteVerification | None = None,
) -> None:
    counts = Counter(op.kind for op in plan.operations)
    lines = [
        "AUTOMATIZACION DE HOJA DE PARAMETROS",
        "===================================",
        f"Fecha: {datetime.now().isoformat(timespec='seconds')}",
        f"Maquina: {machine}",
        f"Molde: {mold_number}",
        f"Grupo de plantilla: {template_group}",
        f"Plantilla: {template_file}",
        f"Modo de ejecucion: {execution_mode}",
        f"Modo Control Inyeccion: {injection_control_mode or 'NO INFORMADO'}",
        f"Parametros resueltos: {len(param_values)}",
        f"Resultantes resueltas: {len(resul_values)}",
        f"Operaciones totales: {len(plan.operations)}",
        f"WRITE planeados: {counts.get('WRITE', 0)}",
        f"CLEAR planeados: {counts.get('CLEAR', 0)}",
        f"COPY_FILL planeados: {counts.get('COPY_FILL', 0)}",
        f"Cores activos: {', '.join(plan.active_cores) if plan.active_cores else 'NINGUNO'}",
        f"Valve Gates activos: {', '.join(str(x) for x in plan.active_valve_gates) if plan.active_valve_gates else 'NINGUNO'}",
        "",
        "RESULTANTES:",
    ]
    if resul_values:
        for key in sorted(resul_values):
            lines.append(f"- {key}: {resul_values[key]}")
    else:
        lines.append("- No incluidas en esta ejecucion")
    if parameter_warnings:
        lines.extend([
            "",
            f"ADVERTENCIAS DE PARAMETROS NO ENCONTRADOS ({len(parameter_warnings)}):",
        ])
        lines.extend(f"- {w}" for w in parameter_warnings)
    if template_warnings:
        lines.extend(["", "ADVERTENCIAS DE PLANTILLA:"])
        lines.extend(f"- {w}" for w in template_warnings)
    if verification is not None:
        lines.extend([
            "",
            "VERIFICACION EXCEL:",
            f"- Celdas finales verificadas: {verification.checked_cells}",
            f"- Celdas finales con valor: {verification.write_cells}",
            f"- Celdas finales limpias: {verification.clear_cells}",
            f"- Diferencias: {len(verification.mismatches)}",
            f"- Operaciones normalizadas a celda superior izquierda de rango combinado: {verification.merged_cells_normalized}",
            "",
            "RESULTADO: ARCHIVO GENERADO Y VERIFICADO",
        ])
    else:
        lines.extend(["", "RESULTADO: PLAN GENERADO CORRECTAMENTE"])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
