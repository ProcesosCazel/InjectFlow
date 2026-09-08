from __future__ import annotations

import argparse
from datetime import datetime
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

from .catalogs import DataCatalog, MappingCatalog
from .errors import AutomationError, ProcessWarning
from .excel_writer import ExcelComWriter
from .history import append_generation_history, build_dynamic_output_path
from .parsers import ParamDatParser, ResulCsvParser
from .plan import GenerationPlan, Operation, PlanBuilder
from .plan_debug import write_plan_csv
from .report import write_report
from .resolver import DataResolver
from .template_validation import validate_template
from .utils import is_truthy


def project_root() -> Path:
    """Return the folder that contains editable production assets.

    In development this is the project root. In a PyInstaller build it is the
    folder containing the .exe, so data/, plantillas/, input/ and output/ can
    live outside _internal and be updated without recompiling.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    root = project_root()
    p = argparse.ArgumentParser(description="Genera HojaDeParametros.xlsx para maquinas Haitian Zeres Gen V y Gen III.")
    p.add_argument("--machine", help="Numero de maquina, por ejemplo 112C")
    p.add_argument("--mold", help="Numero de molde")
    p.add_argument(
        "--injection-control-mode",
        choices=("0", "1"),
        default=None,
        help="Modo de Control de Inyeccion: 0=Modo velocidad, 1=Modo presion.",
    )
    p.add_argument("--data", type=Path, default=root / "data" / "Data.xlsx")
    p.add_argument("--mapping", type=Path, default=root / "data" / "Mapeo.xlsx")
    p.add_argument("--param", type=Path, default=root / "input" / "Param.dat")
    p.add_argument("--resul", type=Path, default=root / "input" / "Resul.csv")
    p.add_argument(
        "--param-only",
        action="store_true",
        help="Genera la hoja usando solo Param.dat; Resul.csv no es requerido ni procesado.",
    )
    p.add_argument("--templates-dir", type=Path, default=root / "plantillas")
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ruta de salida opcional. Si se omite, se genera un nombre dinamico con molde, maquina, fecha y hora.",
    )
    p.add_argument("--history", type=Path, default=root / "data" / "Historial.csv")
    p.add_argument("--report", type=Path, default=root / "output" / "Reporte_Validacion.txt")
    p.add_argument("--plan-csv", type=Path, default=root / "output" / "Plan_Escritura.csv")
    p.add_argument("--plan-only", action="store_true", help="Valida y genera el plan, pero no abre Excel.")
    p.add_argument("--allow-template-mismatch", action="store_true", help="No bloquear por cambios en el numero de celdas combinadas.")
    return p


def _param_only_formula_cleanup(
    template_path: Path,
    sheet_name: str,
    mapping: MappingCatalog,
    group: str,
    layout_id: str,
) -> tuple[Operation, ...]:
    """Clear template formulas whose inputs are resultants omitted in Param-only mode.

    The template itself is never saved with openpyxl; it is only inspected. This
    prevents formulas such as Pieces/Hour from displaying #DIV/0! when CycleTime
    is intentionally absent.
    """
    result_cells = {
        row.cell.replace("$", "").upper()
        for row in mapping.rows_for(group, layout_id)
        if row.map_status == "MAPPED"
        and row.cell
        and row.source.strip().upper() == "RESUL"
    }
    if not result_cells:
        return ()

    try:
        wb = load_workbook(template_path, data_only=False, read_only=False)
        ws = wb[sheet_name]
        operations: list[Operation] = []
        for row in ws.iter_rows():
            for cell in row:
                formula = cell.value
                if not isinstance(formula, str) or not formula.startswith("="):
                    continue
                normalized = formula.replace("$", "").upper()
                for ref in result_cells:
                    if re.search(rf"(?<![A-Z0-9_]){re.escape(ref)}(?![A-Z0-9_])", normalized):
                        operations.append(
                            Operation(
                                "CLEAR",
                                cell.coordinate,
                                note="PARAM_ONLY:DEPENDENT_FORMULA",
                            )
                        )
                        break
        return tuple(operations)
    finally:
        try:
            wb.close()
        except Exception:
            pass


def _prompt_machine(mapping: MappingCatalog) -> str:
    valid = sorted(mapping.machines)
    print("Maquinas disponibles:", ", ".join(valid))
    while True:
        value = input("Numero de maquina: ").strip().upper()
        if value in mapping.machines:
            return value
        print("Maquina no valida.")


def _prompt_required(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print("Este dato es obligatorio.")


def _prompt_injection_control_mode() -> int:
    print("Modo de Control de Inyeccion:")
    print("  0 = Modo velocidad")
    print("  1 = Modo presion")
    while True:
        value = input("Selecciona modo [0/1]: ").strip()
        if value in {"0", "1"}:
            return int(value)
        print("Modo no valido. Usa 0 o 1.")


def _resolve_injection_control_mode(args: argparse.Namespace) -> int:
    raw = getattr(args, "injection_control_mode", None)
    if raw is None or str(raw).strip() == "":
        return _prompt_injection_control_mode()
    text = str(raw).strip()
    if text not in {"0", "1"}:
        raise ValueError(
            "Modo de Control de Inyeccion invalido. Usa 0=Modo velocidad o 1=Modo presion."
        )
    return int(text)


def _filter_required_keys_for_injection_mode(
    required_keys: set[str],
    mapping: MappingCatalog,
    group: str,
    layout_id: str,
    injection_control_mode: int,
) -> set[str]:
    """Do not resolve values that the selected injection mode will not use."""
    result = set(required_keys)
    for row in mapping.rows_for(group, layout_id):
        if row.format_rule == "INJECTION_PRESSURE_ZONE" and injection_control_mode == 0:
            result.discard(row.key)
        elif row.format_rule == "INJECTION_CONTROL_MODE" and injection_control_mode == 1:
            result.discard(row.key)
    return result


def run(args: argparse.Namespace) -> int:
    data = DataCatalog(args.data)
    mapping = MappingCatalog(args.mapping)

    machine = (args.machine or "").strip().upper() or _prompt_machine(mapping)
    mold = (args.mold or "").strip() or _prompt_required("Numero de molde")
    injection_control_mode = _resolve_injection_control_mode(args)
    group, template_def = mapping.resolve_machine(machine)
    template_path = args.templates_dir / template_def.template_file

    output_arg = getattr(args, "output", None)
    output_path = (
        Path(output_arg)
        if output_arg
        else build_dynamic_output_path(project_root() / "output", mold=mold, machine=machine)
    )
    history_path = Path(getattr(args, "history", project_root() / "data" / "Historial.csv"))

    include_resultants = not bool(getattr(args, "param_only", False))
    enabled_sources = {"PARAM", "MANUAL"}
    if include_resultants:
        enabled_sources.add("RESUL")

    required_keys = mapping.required_keys_for(
        group,
        template_def.layout_id,
        enabled_sources=enabled_sources,
    )
    required_keys = _filter_required_keys_for_injection_mode(
        required_keys, mapping, group, template_def.layout_id, injection_control_mode
    )
    data_keys = {r.key for r in data.param_rules if r.active} | {r.key for r in data.resul_rules if r.active}
    manual_keys = mapping.manual_input_keys(group) | {
        "MachineNumber", "MoldNumber", "InjectionControlMode"
    }
    missing_catalog_keys = sorted(required_keys - data_keys - manual_keys)
    if missing_catalog_keys:
        from .errors import ConfigurationError
        raise ConfigurationError(
            "Mapeo.xlsx requires keys that are not defined in Data.xlsx: " + ", ".join(missing_catalog_keys)
        )

    validation = validate_template(
        template_path,
        template_def,
        mapping,
        strict=not args.allow_template_mismatch,
    )

    param_parser = ParamDatParser(
        encoding=str(data.cfg("PARAM_ENCODING", "gb18030")),
        header_lines=int(data.cfg("PARAM_HEADER_LINES", 4)),
        validate_crc=is_truthy(data.cfg("PARAM_VALIDATE_CRC32", True)),
    )
    param_records = param_parser.parse(args.param)
    resolver = DataResolver(data)
    param_values = resolver.resolve_param(param_records, required_keys=required_keys)
    parameter_warnings = tuple(resolver.parameter_warnings)

    resul_values: dict[str, object] = {}
    if include_resultants:
        if args.resul is None:
            raise FileNotFoundError("Resul.csv is required unless --param-only is used")
        resul_parser = ResulCsvParser(
            encoding=str(data.cfg("RESUL_ENCODING", "ascii")),
            record_size=int(data.cfg("RESUL_RECORD_SIZE_BYTES", 300)),
            header_records=int(data.cfg("RESUL_HEADER_RECORDS", 1)),
        )
        _, resul_rows = resul_parser.parse(args.resul)
        resul_values = resolver.resolve_resul(resul_rows, required_keys=required_keys)

    values = dict(param_values)
    values.update(resul_values)
    # Capture the generation date once so the sheet, report and file generation
    # all refer to the same execution date. A midnight datetime is used because
    # Excel COM preserves it as a real Excel date and applies the template's
    # existing date number format.
    generation_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    manual = {
        "MachineNumber": machine,
        "MoldNumber": mold,
        "InjectionControlMode": injection_control_mode,
        "GenerationDate": generation_date,
    }
    plan = PlanBuilder(mapping, data).build(
        group,
        template_def.layout_id,
        values,
        manual,
        enabled_sources=enabled_sources,
    )
    if not include_resultants:
        formula_cleanup = _param_only_formula_cleanup(
            template_path,
            validation.sheet_name,
            mapping,
            group,
            template_def.layout_id,
        )
        if formula_cleanup:
            plan = GenerationPlan(
                plan.template_group,
                plan.layout_id,
                plan.operations + formula_cleanup,
                plan.active_cores,
                plan.active_valve_gates,
            )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_plan_csv(args.plan_csv, plan)

    print(f"Maquina: {machine}")
    print(f"Molde: {mold}")
    execution_mode = "PARAMETROS + RESULTANTES" if include_resultants else "SOLO PARAM.DAT"
    print(f"Plantilla: {template_def.template_file}")
    print(f"Modo: {execution_mode}")
    injection_mode_label = (
        "MODO VELOCIDAD" if injection_control_mode == 0 else "MODO PRESION"
    )
    print(f"Modo Control Inyeccion: {injection_mode_label}")
    print(f"Hoja detectada: {validation.sheet_name}")
    print(f"Cores activos: {', '.join(plan.active_cores) if plan.active_cores else 'NINGUNO'}")
    print(
        "Valve Gates activos: "
        + (", ".join(str(g) for g in plan.active_valve_gates) if plan.active_valve_gates else "NINGUNO")
    )
    print(f"Operaciones planeadas: {len(plan.operations)}")
    print(f"Plan detallado: {args.plan_csv}")
    if parameter_warnings:
        print(f"Parametros no encontrados: {len(parameter_warnings)}")
        for warning in parameter_warnings:
            print(f"ADVERTENCIA PARAMETRO: {warning}")
    else:
        print("Parametros no encontrados: 0")

    if args.plan_only:
        write_report(
            args.report,
            machine=machine,
            mold_number=mold,
            template_group=group,
            template_file=template_def.template_file,
            param_values=param_values,
            resul_values=resul_values,
            plan=plan,
            execution_mode=execution_mode,
            injection_control_mode=injection_mode_label,
            template_warnings=validation.warnings,
            parameter_warnings=parameter_warnings,
        )
        print(f"PLAN OK. Reporte: {args.report}")
        return 0

    writer = ExcelComWriter(visible=False)
    verification = writer.write(template_path, output_path, plan.operations, rename_sheet=True)
    write_report(
        args.report,
        machine=machine,
        mold_number=mold,
        template_group=group,
        template_file=template_def.template_file,
        param_values=param_values,
        resul_values=resul_values,
        plan=plan,
        execution_mode=execution_mode,
        injection_control_mode=injection_mode_label,
        template_warnings=validation.warnings,
        parameter_warnings=parameter_warnings,
        verification=verification,
    )
    try:
        history_rows = append_generation_history(
            history_path,
            machine=machine,
            mold=mold,
            mode=execution_mode,
            output_path=output_path,
        )
        history_message = f"Historial actualizado: {history_path} ({history_rows} registros vigentes)"
    except Exception as exc:
        history_message = f"ADVERTENCIA HISTORIAL: no se pudo actualizar {history_path}: {exc}"

    print(f"Verificacion Excel OK: {verification.checked_cells} celdas finales")
    print(f"Celdas combinadas normalizadas: {verification.merged_cells_normalized}")
    print(f"Archivo generado: {output_path}")
    print(history_message)
    print(f"Reporte: {args.report}")
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(run(args))
    except ProcessWarning as exc:
        print(f"ADVERTENCIA: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except (AutomationError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
