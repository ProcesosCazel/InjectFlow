from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalogs import DataCatalog, MappingCatalog, MappingRow
from .errors import ConfigurationError, ProcessWarning, SourceDataError
from .input_policy import JUPITER_GROUP
from .utils import clean_text, normalize_control_value, split_pipe


# Fixed profile labels (1, 2, 3, End) belong to the locked Jupiter template.
# The planner must not rewrite or clear them.


@dataclass(frozen=True)
class Operation:
    kind: str
    cell: str
    value: Any = None
    ref_cell: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class GenerationPlan:
    template_group: str
    layout_id: str
    operations: tuple[Operation, ...]
    active_cores: tuple[str, ...]
    active_valve_gates: tuple[int, ...] = ()


class PlanBuilder:
    def __init__(self, mapping: MappingCatalog, data: DataCatalog | None = None):
        self.mapping = mapping
        self.data = data

    def build(
        self,
        group: str,
        layout_id: str,
        values: dict[str, Any],
        manual_values: dict[str, Any],
        enabled_sources: set[str] | None = None,
    ) -> GenerationPlan:
        all_values = dict(values)
        all_values.update(manual_values)
        rows = self.mapping.rows_for(group, layout_id)
        ops: list[Operation] = []
        normalized_sources = (
            {clean_text(source).upper() for source in enabled_sources}
            if enabled_sources is not None
            else None
        )

        generic_active_ref, generic_inactive_ref = self._generic_fill_refs(group, layout_id)

        for row in rows:
            if normalized_sources is not None and clean_text(row.source).upper() not in normalized_sources:
                continue
            if row.map_status in {"NOT_USED", "CORE_DYNAMIC", "VALVE_GATE_DYNAMIC"}:
                continue
            if row.map_status != "MAPPED":
                raise ConfigurationError(f"Unsupported MAP STATUS {row.map_status!r} for {row.map_id}")
            if not row.cell or row.cell.upper() in {"NOT USED", "CORE_DYNAMIC", "INPUT_ONLY"}:
                raise ConfigurationError(f"Mapped row {row.map_id} has no valid CELL")
            value_available = row.key in all_values

            if row.format_rule == "STATIC":
                if value_available:
                    ops.append(Operation("WRITE", row.cell, self._display_value_for_row(row, all_values[row.key]), note=row.map_id))
                else:
                    # Best-effort mode: never leave an old/default value in a cell
                    # when the corresponding source key was unavailable.
                    ops.append(Operation("CLEAR", row.cell, note=f"{row.map_id}:MISSING:{row.key}"))
            elif row.format_rule == "STATIC_ACTIVE":
                # Some locked Jupiter cells are intentionally gray in the blank
                # template but must become normal/transparent as soon as a real
                # process value is written (for example Mold Protect).
                if value_available:
                    ops.append(Operation("COPY_FILL", row.cell, ref_cell=generic_active_ref, note=row.map_id))
                    ops.append(Operation("WRITE", row.cell, self._display_value_for_row(row, all_values[row.key]), note=row.map_id))
                else:
                    ops.append(Operation("CLEAR", row.cell, note=f"{row.map_id}:MISSING:{row.key}"))
                    ops.append(Operation("COPY_FILL", row.cell, ref_cell=generic_inactive_ref, note=f"{row.map_id}:MISSING"))
            elif row.format_rule == "PROFILE_END":
                # The fixed End row is visually active only when the profile has
                # at least one point.  The End value is never compacted into a
                # numbered row.
                if not row.controlled_by:
                    raise ConfigurationError(f"PROFILE_END row {row.map_id} lacks controller")
                raw_count = all_values.get(row.controlled_by)
                try:
                    profile_active = raw_count is not None and int(raw_count) > 0
                except (TypeError, ValueError):
                    profile_active = False
                if profile_active and value_available:
                    ops.append(Operation("COPY_FILL", row.cell, ref_cell=generic_active_ref, note=row.map_id))
                    ops.append(Operation("WRITE", row.cell, self._display_value_for_row(row, all_values[row.key]), note=row.map_id))
                else:
                    ops.append(Operation("CLEAR", row.cell, note=row.map_id))
                    ops.append(Operation("COPY_FILL", row.cell, ref_cell=generic_inactive_ref, note=row.map_id))
            elif row.format_rule == "ZONE":
                if not row.controlled_by or row.zone_index is None:
                    raise ConfigurationError(f"ZONE row {row.map_id} lacks controller/index")
                if row.controlled_by not in all_values:
                    # Without the controller we cannot know whether this physical
                    # zone is active. Clear its value and preserve the template fill.
                    ops.append(Operation("CLEAR", row.cell, note=f"{row.map_id}:MISSING_CONTROLLER:{row.controlled_by}"))
                    continue
                rule = self.mapping.zone_rule(group, layout_id, row.controlled_by, all_values[row.controlled_by])
                active = row.zone_index in rule.active_indexes
                if active:
                    ops.append(Operation("COPY_FILL", row.cell, ref_cell=rule.active_fill_ref, note=row.map_id))
                    if value_available:
                        ops.append(Operation("WRITE", row.cell, self._display_value_for_row(row, all_values[row.key]), note=row.map_id))
                    else:
                        ops.append(Operation("CLEAR", row.cell, note=f"{row.map_id}:MISSING:{row.key}"))
                else:
                    ops.append(Operation("CLEAR", row.cell, note=row.map_id))
                    ops.append(Operation("COPY_FILL", row.cell, ref_cell=rule.inactive_fill_ref, note=row.map_id))
            elif row.format_rule == "INJECTION_CONTROL_MODE":
                ops.extend(
                    self._build_injection_control_mode_ops(
                        row, all_values, generic_active_ref
                    )
                )
            elif row.format_rule == "INJECTION_PRESSURE_ZONE":
                ops.extend(
                    self._build_injection_pressure_zone_ops(
                        row, group, layout_id, all_values,
                        generic_active_ref, generic_inactive_ref,
                    )
                )
            elif row.format_rule == "STATE_CONTROLLED":
                if not row.controlled_by:
                    raise ConfigurationError(f"STATE_CONTROLLED row {row.map_id} lacks controller")
                if row.controlled_by not in all_values:
                    ops.append(Operation("CLEAR", row.cell, note=f"{row.map_id}:MISSING_CONTROLLER:{row.controlled_by}"))
                    continue
                active = clean_text(all_values[row.controlled_by]).upper() == "ON"
                if active:
                    ops.append(Operation("COPY_FILL", row.cell, ref_cell=generic_active_ref, note=row.map_id))
                    if value_available:
                        ops.append(Operation("WRITE", row.cell, self._display_value_for_row(row, all_values[row.key]), note=row.map_id))
                    else:
                        ops.append(Operation("CLEAR", row.cell, note=f"{row.map_id}:MISSING:{row.key}"))
                else:
                    ops.append(Operation("CLEAR", row.cell, note=row.map_id))
                    ops.append(Operation("COPY_FILL", row.cell, ref_cell=generic_inactive_ref, note=row.map_id))
            elif row.format_rule in {"NONE", ""}:
                # Normally controls are NOT_USED. A mapped NONE row is treated as a direct write.
                if value_available:
                    ops.append(Operation("WRITE", row.cell, self._display_value_for_row(row, all_values[row.key]), note=row.map_id))
                else:
                    ops.append(Operation("CLEAR", row.cell, note=f"{row.map_id}:MISSING:{row.key}"))
            else:
                raise ConfigurationError(f"Unsupported FORMAT RULE {row.format_rule!r} for {row.map_id}")


        core_ops, active_cores = self._build_core_ops(group, layout_id, all_values, generic_active_ref, generic_inactive_ref)
        ops.extend(core_ops)
        valve_ops, active_valve_gates = self._build_valve_gate_ops(group, layout_id, all_values)
        ops.extend(valve_ops)
        return GenerationPlan(
            group,
            layout_id,
            tuple(ops),
            tuple(active_cores),
            tuple(active_valve_gates),
        )

    @staticmethod
    def _injection_mode(values: dict[str, Any], key: str = "InjectionControlMode") -> int:
        if key not in values:
            raise SourceDataError(f"Missing manual injection control mode {key}")
        raw = values[key]
        text = clean_text(raw).upper()
        aliases = {
            "0": 0,
            "MODO VELOCIDAD": 0,
            "VELOCIDAD": 0,
            "1": 1,
            "MODO PRESION": 1,
            "MODO PRESIÓN": 1,
            "PRESION": 1,
            "PRESIÓN": 1,
        }
        if text in aliases:
            return aliases[text]
        try:
            numeric = int(raw)
        except (TypeError, ValueError):
            numeric = -1
        if numeric in (0, 1):
            return numeric
        raise ConfigurationError(
            f"InjectionControlMode invalido: {raw!r}. Valores permitidos: "
            "0=Modo velocidad, 1=Modo presion."
        )

    def _build_injection_control_mode_ops(
        self,
        row: MappingRow,
        values: dict[str, Any],
        active_fill_ref: str,
    ) -> list[Operation]:
        """Velocity mode: write only the physical P1 pressure cell.

        In pressure mode this row intentionally does nothing because the
        INJECTION_PRESSURE_ZONE rows own all pressure cells, including P1.
        """
        controllers = split_pipe(row.controlled_by)
        mode_key = controllers[0] if controllers else "InjectionControlMode"
        mode = self._injection_mode(values, mode_key)
        if mode == 1:
            return []
        ops = [Operation("COPY_FILL", row.cell, ref_cell=active_fill_ref, note=row.map_id)]
        if row.key in values:
            ops.append(
                Operation(
                    "WRITE", row.cell,
                    self._display_value_for_row(row, values[row.key]),
                    note=row.map_id,
                )
            )
        else:
            ops.append(Operation("CLEAR", row.cell, note=f"{row.map_id}:MISSING:{row.key}"))
        return ops

    def _build_injection_pressure_zone_ops(
        self,
        row: MappingRow,
        group: str,
        layout_id: str,
        values: dict[str, Any],
        active_fill_ref: str,
        inactive_fill_ref: str,
    ) -> list[Operation]:
        """Apply v1.3 pressure-mode activation using InjectionZones.

        Pressure mode follows exactly the existing injection-zone pattern:
        1=P6/PE; 2=P1+P6/PE; 3=P1+P2+P6/PE; ...;
        6=P1+P2+P3+P4+P5+P6/PE.
        """
        controllers = split_pipe(row.controlled_by)
        mode_key = controllers[0] if controllers else "InjectionControlMode"
        zone_key = controllers[1] if len(controllers) > 1 else "InjectionZones"
        mode = self._injection_mode(values, mode_key)

        if row.zone_index is None:
            raise ConfigurationError(
                f"INJECTION_PRESSURE_ZONE row {row.map_id} lacks ZONE INDEX"
            )

        if mode == 0:
            # P1 is managed by the velocity-mode row and shares the same cell.
            # Do not clear it here. All other pressure cells must remain inactive.
            if row.zone_index == 1:
                return []
            return [
                Operation("CLEAR", row.cell, note=f"{row.map_id}:VELOCITY_MODE"),
                Operation(
                    "COPY_FILL", row.cell, ref_cell=inactive_fill_ref,
                    note=f"{row.map_id}:VELOCITY_MODE",
                ),
            ]

        if zone_key not in values:
            return [Operation(
                "CLEAR", row.cell,
                note=f"{row.map_id}:MISSING_CONTROLLER:{zone_key}",
            )]

        rule = self.mapping.zone_rule(
            group, layout_id, zone_key, values[zone_key]
        )
        active = row.zone_index in rule.active_indexes
        if not active:
            return [
                Operation("CLEAR", row.cell, note=row.map_id),
                Operation(
                    "COPY_FILL", row.cell, ref_cell=rule.inactive_fill_ref,
                    note=row.map_id,
                ),
            ]

        ops = [
            Operation(
                "COPY_FILL", row.cell, ref_cell=rule.active_fill_ref, note=row.map_id
            )
        ]
        if row.key in values:
            ops.append(
                Operation(
                    "WRITE", row.cell,
                    self._display_value_for_row(row, values[row.key]),
                    note=row.map_id,
                )
            )
        else:
            ops.append(Operation("CLEAR", row.cell, note=f"{row.map_id}:MISSING:{row.key}"))
        return ops

    def _generic_fill_refs(self, group: str, layout_id: str) -> tuple[str, str]:
        settings = self.mapping.core_settings(group, layout_id)
        active = clean_text(settings.get("ACTIVE_FILL_REF"))
        inactive = clean_text(settings.get("INACTIVE_FILL_REF"))
        if active and inactive:
            return active, inactive
        rules = [r for r in self.mapping.zone_rules if r.template_group == group and r.layout_id == layout_id]
        if rules:
            return rules[0].active_fill_ref, rules[0].inactive_fill_ref
        raise ConfigurationError("No active/inactive fill reference cells defined")

    CHECKBOX_KEYS = frozenset({"SuckBackActive", "PreReleaseMode"})
    JUPITER_CHECKBOX_KEYS = frozenset({
        "MoldOpenUseFastOpen",
        "MoldOpenFastRelease",
        "MoldOpenUseBufferRelease",
        "Injection1UsePosition",
        "Injection1UseTimer",
        "Injection1UsePressure",
        "Injection2UsePosition",
        "Injection2UseTimer",
        "Injection2UsePressure",
    })

    @classmethod
    def _display_value_for_row(cls, row: MappingRow, value: Any) -> Any:
        # Only fields explicitly known to be checkbox-style should convert ON/OFF.
        # Other state values must remain as text so they are never silently blanked.
        if row.key in cls.JUPITER_CHECKBOX_KEYS:
            return cls._jupiter_checkbox_value(value)
        if row.key in cls.CHECKBOX_KEYS:
            return cls._checkbox_value(value)
        return value

    @staticmethod
    def _jupiter_checkbox_value(value: Any) -> Any:
        text = clean_text(value).upper() if isinstance(value, str) else None
        if text == "ON":
            return "\u2713"
        if text == "OFF":
            return None
        return value

    @staticmethod
    def _checkbox_value(value: Any) -> Any:
        text = clean_text(value).upper() if isinstance(value, str) else None
        if text == "ON":
            return "\u221a"
        if text == "OFF":
            return None
        return value

    @staticmethod
    def _display_value(value: Any) -> Any:
        # Preserve ordinary state values exactly as resolved by Data.xlsx.
        return value

    def _build_core_ops(
        self,
        group: str,
        layout_id: str,
        values: dict[str, Any],
        active_fill_ref: str,
        inactive_fill_ref: str,
    ) -> tuple[list[Operation], list[str]]:
        settings = self.mapping.core_settings(group, layout_id)
        order = split_pipe(settings.get("CORE_ORDER")) or ["A", "B", "C", "D"]
        selector_keys = split_pipe(settings.get("SELECTOR_KEYS"))
        if not selector_keys:
            selector_keys = [f"Core{x}Mode" for x in order]
        if len(selector_keys) != len(order):
            raise ConfigurationError("CORE_ORDER and SELECTOR_KEYS lengths differ")

        active_cores = [core for core, key in zip(order, selector_keys) if clean_text(values.get(key)).upper() == "ON"]

        layout_rows = self.mapping.core_layout(group, layout_id)
        field_rows = self.mapping.core_fields(group, layout_id)

        configured_slots = [
            clean_text(slot).upper()
            for slot in split_pipe(settings.get("SLOT_ORDER"))
            if clean_text(slot)
        ]
        if configured_slots:
            slot_order = configured_slots
        else:
            # Legacy layouts did not need SLOT_ORDER.  Derive physical slots
            # from CoreLayout in first-seen order so Gen V (LEFT/RIGHT) and
            # Gen III _500 (LEFT) keep their existing behavior unchanged.
            slot_order: list[str] = []
            for row in layout_rows:
                slot = clean_text(row.get("SLOT")).upper()
                if slot and slot not in slot_order:
                    slot_order.append(slot)

        if not slot_order:
            raise ConfigurationError(f"No CoreLayout slots configured for {group}/{layout_id}")
        if len(set(slot_order)) != len(slot_order):
            raise ConfigurationError(f"Duplicate SLOT_ORDER entries for {group}/{layout_id}: {slot_order}")

        max_cores = int(settings.get("MAX_ACTIVE_CORES", len(slot_order)))
        if max_cores > len(slot_order):
            raise ConfigurationError(
                f"Core configuration for {group}/{layout_id} allows {max_cores} active cores "
                f"but only {len(slot_order)} physical slots are configured: {', '.join(slot_order)}"
            )
        if len(active_cores) > max_cores:
            raise ProcessWarning(
                "Se detectaron mas Noyos activos de los que admite la plantilla. "
                f"Plantilla {group}: maximo {max_cores}; detectados {', '.join(active_cores)}. "
                "La hoja no se genero para evitar omitir un Noyo activo."
            )

        slot_to_core: dict[str, str | None] = {slot: None for slot in slot_order}
        assignment_mode = clean_text(settings.get("ASSIGNMENT_MODE") or "COMPACT").upper()
        if assignment_mode == "FIXED_BY_CORE":
            fixed = {slot: clean_text(settings.get(f"{slot}_FIXED_CORE")).upper()
                     for slot in slot_order}
            if (any(core not in order for core in fixed.values())
                    or len(set(fixed.values())) != len(fixed)
                    or any(core not in fixed.values() for core in active_cores)):
                raise ConfigurationError(f"Invalid fixed core assignment for {group}/{layout_id}: {fixed}")
            for slot, core in fixed.items():
                slot_to_core[slot] = core if core in active_cores else None
        elif assignment_mode != "COMPACT":
            raise ConfigurationError(f"Unsupported core ASSIGNMENT_MODE: {assignment_mode}")
        elif len(active_cores) == 1:
            one_core_slot = clean_text(settings.get("ONE_CORE_SLOT")).upper() or slot_order[0]
            if one_core_slot not in slot_to_core:
                raise ConfigurationError(
                    f"ONE_CORE_SLOT={one_core_slot!r} is not present in SLOT_ORDER for {group}/{layout_id}"
                )
            slot_to_core[one_core_slot] = active_cores[0]
        elif active_cores:
            for slot, core in zip(slot_order, active_cores):
                slot_to_core[slot] = core
        layout_index: dict[tuple[str, str, str], str] = {}
        for row in layout_rows:
            slot = clean_text(row.get("SLOT")).upper()
            field = clean_text(row.get("FIELD")).upper()
            direction = clean_text(row.get("DIRECTION")).upper()
            cell = clean_text(row.get("CELL"))
            if slot and field and direction and cell:
                layout_index[(slot, field, direction)] = cell

        ops: list[Operation] = []
        for slot in slot_order:
            core = slot_to_core[slot]
            id_cell = clean_text(settings.get(f"{slot}_CORE_ID_CELL"))
            action_label = clean_text(settings.get(f"{slot}_ACTION_LABEL"))
            action_value = clean_text(settings.get(f"{slot}_ACTION_VALUE"))
            status_cell = clean_text(settings.get(f"{slot}_STATUS_CELL"))
            in_label = clean_text(settings.get(f"{slot}_IN_LABEL"))
            out_label = clean_text(settings.get(f"{slot}_OUT_LABEL"))

            slot_cells = sorted({
                clean_text(r.get("CELL"))
                for r in layout_rows
                if clean_text(r.get("SLOT")).upper() == slot and clean_text(r.get("CELL"))
            })

            if core is None:
                for cell in slot_cells:
                    ops.append(Operation("CLEAR", cell, note=f"CORE_{slot}_OFF"))
                    ops.append(Operation("COPY_FILL", cell, ref_cell=inactive_fill_ref, note=f"CORE_{slot}_OFF"))
                for cell in (id_cell, action_label, action_value, in_label, out_label):
                    if cell:
                        ops.append(Operation("CLEAR", cell, note=f"CORE_{slot}_OFF"))
                if status_cell:
                    # The status displayed beside the fixed Noyo A/B/C label is
                    # independent from the parameter-area shading. A physical slot
                    # with no selected core must explicitly show OFF instead of
                    # retaining the template's default ON text.
                    ops.append(Operation("WRITE", status_cell, "OFF", note=f"CORE_{slot}_STATUS"))
                continue

            # Enable all physical parameter cells first, including format-only Hold/Hold Adv rows.
            for cell in slot_cells:
                ops.append(Operation("COPY_FILL", cell, ref_cell=active_fill_ref, note=f"CORE_{slot}_{core}"))
                ops.append(Operation("CLEAR", cell, note=f"CORE_{slot}_{core}_RESET"))

            if status_cell:
                ops.append(Operation("WRITE", status_cell, "ON", note=f"CORE_{slot}_STATUS"))
            if id_cell:
                ops.append(Operation("WRITE", id_cell, core, note=f"CORE_{slot}_ID"))
            if action_label:
                ops.append(Operation("WRITE", action_label, f"Core {core} action", note=f"CORE_{slot}_LABEL"))
            if in_label:
                ops.append(Operation("WRITE", in_label, f"Core {core} in", note=f"CORE_{slot}_LABEL"))
            if out_label:
                ops.append(Operation("WRITE", out_label, f"Core {core} out", note=f"CORE_{slot}_LABEL"))
            selector = f"Core{core}Mode"
            if action_value:
                ops.append(Operation("WRITE", action_value, self._checkbox_value(values.get(selector, "ON")), note=f"CORE_{slot}_ACTION"))

            for field_row in field_rows:
                if clean_text(field_row.get("CORE")).upper() != core:
                    continue
                if clean_text(field_row.get("STATUS")).upper() != "MAPPED":
                    continue
                data_key = clean_text(field_row.get("DATA KEY"))
                dest_field = clean_text(field_row.get("DESTINATION FIELD")).upper()
                direction = clean_text(field_row.get("DIRECTION")).upper()
                if not data_key:
                    raise ConfigurationError(f"CoreFields entry for Core {core} has no DATA KEY")
                cell = layout_index.get((slot, dest_field, direction))
                if not cell:
                    raise ConfigurationError(f"No CoreLayout cell for {slot}/{dest_field}/{direction}")

                # Core Out During Mold is displayed as a binary visual field.
                # ON  -> remove gray fill and write the literal text "ON".
                # OFF -> clear the value and apply the inactive gray fill.
                # This same source is mapped to Simultaneous on Gen III and
                # Hold on Gen V.
                is_out_during_mold = (
                    data_key.endswith("OutDuringMold")
                    and dest_field in {"DURING_MOLD", "HOLD"}
                )
                if is_out_during_mold:
                    if data_key not in values:
                        # Missing source is already reported as a warning by the
                        # resolver. Render the field conservatively as inactive.
                        ops.append(Operation("CLEAR", cell, note=f"CORE_{core}:{data_key}:MISSING"))
                        ops.append(Operation("COPY_FILL", cell, ref_cell=inactive_fill_ref, note=f"CORE_{core}:{data_key}:MISSING"))
                        continue
                    state = clean_text(values[data_key]).upper()
                    if state == "ON":
                        ops.append(Operation("COPY_FILL", cell, ref_cell=active_fill_ref, note=f"CORE_{core}:{data_key}:ON"))
                        ops.append(Operation("WRITE", cell, "ON", note=f"CORE_{core}:{data_key}"))
                    elif state == "OFF":
                        ops.append(Operation("CLEAR", cell, note=f"CORE_{core}:{data_key}:OFF"))
                        ops.append(Operation("COPY_FILL", cell, ref_cell=inactive_fill_ref, note=f"CORE_{core}:{data_key}:OFF"))
                    else:
                        raise ConfigurationError(
                            f"Invalid {data_key} state {values[data_key]!r}; expected ON/OFF"
                        )
                    continue

                # Gen V Hold Adv. is controlled by the same Hold state used by
                # Core Out During Mold. Each direction displays its own counter:
                #   IN  -> Core{X}InCounter
                #   OUT -> Core{X}OutCounter
                # Hold ON  -> unshade and write the counter value.
                # Hold OFF -> shade and leave the field blank.
                is_hold_adv_counter = (
                    group == "HAITIAN_ZE_V"
                    and dest_field == "HOLD_ADV"
                    and data_key.endswith(("InCounter", "OutCounter"))
                )
                if is_hold_adv_counter:
                    hold_key = f"Core{core}OutDuringMold"
                    if hold_key not in values:
                        # Missing Hold state is already reported by the resolver.
                        # Render Hold Adv. conservatively as disabled.
                        ops.append(Operation("CLEAR", cell, note=f"CORE_{core}:{data_key}:HOLD_MISSING"))
                        ops.append(Operation("COPY_FILL", cell, ref_cell=inactive_fill_ref, note=f"CORE_{core}:{data_key}:HOLD_MISSING"))
                        continue

                    hold_state = clean_text(values[hold_key]).upper()
                    if hold_state == "OFF":
                        ops.append(Operation("CLEAR", cell, note=f"CORE_{core}:{data_key}:HOLD_OFF"))
                        ops.append(Operation("COPY_FILL", cell, ref_cell=inactive_fill_ref, note=f"CORE_{core}:{data_key}:HOLD_OFF"))
                        continue
                    if hold_state != "ON":
                        raise ConfigurationError(
                            f"Invalid {hold_key} state {values[hold_key]!r}; expected ON/OFF"
                        )

                    ops.append(Operation("COPY_FILL", cell, ref_cell=active_fill_ref, note=f"CORE_{core}:{data_key}:HOLD_ON"))
                    if data_key in values:
                        ops.append(Operation("WRITE", cell, self._display_value(values[data_key]), note=f"CORE_{core}:{data_key}"))
                    else:
                        # Keep the field enabled because Hold is ON, but leave it
                        # blank when the counter source is absent. The resolver
                        # records the missing parameter as a warning.
                        ops.append(Operation("CLEAR", cell, note=f"CORE_{core}:{data_key}:MISSING"))
                    continue

                # Gen III Mold Position is conditional on CORE_MOLD_TYPE for
                # each direction independently:
                #   IN  -> Core{X}InMoldType  controls Core{X}InMoldPosition  (O55)
                #   OUT -> Core{X}OutMoldType controls Core{X}OutMoldPosition (O60)
                # CIER. BLOQ. -> disable the physical field (clear + shade).
                # POS MOLD    -> enable the field (unshade) and write the position.
                expected_suffix = f"{direction.title()}MoldPosition" if direction in {"IN", "OUT"} else ""
                is_gen3_mold_position = (
                    group == "HAITIAN_ZE_III"
                    and dest_field == "START_POS"
                    and direction in {"IN", "OUT"}
                    and expected_suffix
                    and data_key.endswith(expected_suffix)
                )
                if is_gen3_mold_position:
                    prefix = direction.upper()
                    default_control_pattern = f"Core{{CORE}}{direction.title()}MoldType"
                    control_pattern = (
                        clean_text(settings.get(f"{prefix}_MOLD_POSITION_CONTROL_KEY_PATTERN"))
                        or default_control_pattern
                    )
                    control_key = control_pattern.replace("{CORE}", core)
                    enabled_value = (
                        clean_text(settings.get(f"{prefix}_MOLD_POSITION_ENABLED_VALUE"))
                        or clean_text(settings.get("IN_MOLD_POSITION_ENABLED_VALUE"))
                        or "POS MOLD"
                    )
                    disabled_value = (
                        clean_text(settings.get(f"{prefix}_MOLD_POSITION_DISABLED_VALUE"))
                        or clean_text(settings.get("IN_MOLD_POSITION_DISABLED_VALUE"))
                        or "CIER. BLOQ."
                    )

                    if control_key not in values:
                        # Missing controller is already reported by the resolver.
                        # Render conservatively as disabled.
                        ops.append(Operation("CLEAR", cell, note=f"CORE_{core}:{data_key}:{control_key}:MISSING"))
                        ops.append(Operation("COPY_FILL", cell, ref_cell=inactive_fill_ref, note=f"CORE_{core}:{data_key}:{control_key}:MISSING"))
                        continue

                    mold_type = clean_text(values[control_key]).upper()
                    if mold_type == enabled_value.upper():
                        ops.append(Operation("COPY_FILL", cell, ref_cell=active_fill_ref, note=f"CORE_{core}:{data_key}:POS_MOLD"))
                        if data_key in values:
                            ops.append(Operation("WRITE", cell, self._display_value(values[data_key]), note=f"CORE_{core}:{data_key}"))
                        else:
                            # Keep enabled but blank if the position itself is missing.
                            ops.append(Operation("CLEAR", cell, note=f"CORE_{core}:{data_key}:MISSING"))
                        continue
                    if mold_type == disabled_value.upper():
                        ops.append(Operation("CLEAR", cell, note=f"CORE_{core}:{data_key}:CIER_BLOQ"))
                        ops.append(Operation("COPY_FILL", cell, ref_cell=inactive_fill_ref, note=f"CORE_{core}:{data_key}:CIER_BLOQ"))
                        continue

                    raise ConfigurationError(
                        f"Invalid {control_key} state {values[control_key]!r}; "
                        f"expected {enabled_value!r} or {disabled_value!r}"
                    )

                if data_key not in values:
                    # The slot was cleared above; leave this one field blank and
                    # continue generating the rest of the sheet.
                    continue
                ops.append(Operation("WRITE", cell, self._display_value(values[data_key]), note=f"CORE_{core}:{data_key}"))

        return ops, active_cores

    def _build_valve_gate_ops(
        self,
        group: str,
        layout_id: str,
        values: dict[str, Any],
    ) -> tuple[list[Operation], list[int]]:
        settings = self.mapping.valve_gate_settings(group, layout_id)
        layout_rows = self.mapping.valve_gate_layout(group, layout_id)
        field_rows = self.mapping.valve_gate_fields(group, layout_id)
        if not settings and not layout_rows and not field_rows:
            return [], []
        if not settings or not layout_rows or not field_rows:
            raise ConfigurationError(
                f"Incomplete Valve Gate configuration for {group}/{layout_id}"
            )

        gate_order_text = split_pipe(settings.get("GATE_ORDER"))
        if not gate_order_text:
            controller_max = int(settings.get("CONTROLLER_MAX_GATES", 13))
            gate_order = list(range(1, controller_max + 1))
        else:
            try:
                gate_order = [int(x) for x in gate_order_text]
            except ValueError as exc:
                raise ConfigurationError("GATE_ORDER must contain integer Valve Gate indexes") from exc

        selector_pattern = clean_text(settings.get("SELECTOR_KEY_PATTERN")) or "ValveGate{GATE}State"
        active_selector = clean_text(settings.get("ACTIVE_SELECTOR_VALUE") or "ON").upper()
        max_active = int(settings.get("TEMPLATE_MAX_ACTIVE_GATES", 4))

        # ValveGateFields is authoritative for which selectors are production-ready.
        selector_status: dict[int, str] = {}
        selector_key: dict[int, str] = {}
        for row in field_rows:
            if clean_text(row.get("FIELD")).upper() != "SELECTOR":
                continue
            try:
                gate = int(row.get("GATE"))
            except (TypeError, ValueError):
                continue
            selector_status[gate] = clean_text(row.get("STATUS")).upper()
            key = clean_text(row.get("DATA KEY"))
            if key:
                selector_key[gate] = key

        # Controller index 9 is reserved/non-existent on validated Haitian
        # exports. The HMI skips it: raw 10 is shown as Gate 9, raw 21 as Gate 20.
        # Keep raw controller indexes for data lookup and convert only for
        # user-visible numbering.
        numbering_policy = clean_text(settings.get("NUMBERING_POLICY") or "ZERES_RESERVED_9").upper()
        if numbering_policy not in {"DIRECT", "ZERES_RESERVED_9"}:
            raise ConfigurationError(f"Unsupported Valve Gate NUMBERING_POLICY: {numbering_policy}")
        direct_numbering = numbering_policy == "DIRECT"
        gate_number = (lambda g: g) if direct_numbering else self._valve_gate_hmi_number
        active_controller_gates: list[int] = []
        for gate in gate_order:
            if gate == 9 and not direct_numbering:
                continue
            status = selector_status.get(gate, "CONTROL")
            if status == "REVIEW":
                continue
            if status not in {"CONTROL", "MAPPED"}:
                continue
            key = selector_key.get(gate) or selector_pattern.replace("{GATE}", str(gate))
            if key not in values:
                continue
            if clean_text(values[key]).upper() == active_selector:
                active_controller_gates.append(gate)

        active_gates = [gate_number(g) for g in active_controller_gates]

        if len(active_controller_gates) > max_active:
            action = clean_text(settings.get("OVER_LIMIT_ACTION") or "WARNING").upper()
            message = (
                f"Se detectaron {len(active_controller_gates)} Valve Gates activos: "
                f"{', '.join(str(g) for g in active_gates)}. "
                f"La plantilla solo admite {max_active} Valve Gates a la vez. "
                "La hoja no se genero para evitar omitir compuertas activas."
            )
            if action in {"WARNING", "ERROR", "BLOCK"}:
                raise ProcessWarning(message)
            raise ConfigurationError(f"Unsupported Valve Gate OVER_LIMIT_ACTION {action!r}")

        layout_index: dict[tuple[str, str], str] = {}
        slot_names: list[str] = []
        for row in layout_rows:
            slot = clean_text(row.get("SLOT")).upper()
            field = clean_text(row.get("FIELD")).upper()
            cell = clean_text(row.get("CELL"))
            if slot and field and cell:
                layout_index[(slot, field)] = cell
                if slot not in slot_names:
                    slot_names.append(slot)
        slot_names.sort(key=self._slot_sort_key)
        if len(slot_names) < max_active:
            raise ConfigurationError(
                f"ValveGateLayout defines {len(slot_names)} slots but TEMPLATE_MAX_ACTIVE_GATES={max_active}"
            )

        fields_by_gate: dict[int, list[dict[str, Any]]] = {}
        for row in field_rows:
            try:
                gate = int(row.get("GATE"))
            except (TypeError, ValueError):
                continue
            fields_by_gate.setdefault(gate, []).append(row)

        ops: list[Operation] = []
        active_fill_ref, inactive_fill_ref = self._generic_fill_refs(group, layout_id)

        # Reset every physical sequencer row, then explicitly apply its visual
        # state. Unused rows must be blank AND shaded; active rows must retain
        # the normal transparent/active fill. This prevents empty Valve Gate
        # slots from looking enabled when fewer than four gates are active.
        active_slot_count = len(active_controller_gates)
        for slot_index, slot in enumerate(slot_names[:max_active]):
            cells = sorted({
                cell for (slot_name, _field), cell in layout_index.items()
                if slot_name == slot
            })
            fill_ref = active_fill_ref if slot_index < active_slot_count else inactive_fill_ref
            fill_state = "ACTIVE" if slot_index < active_slot_count else "INACTIVE"
            for cell in cells:
                ops.append(Operation("CLEAR", cell, note=f"VALVE_GATE_{slot}_RESET"))
                ops.append(
                    Operation(
                        "COPY_FILL",
                        cell,
                        ref_cell=fill_ref,
                        note=f"VALVE_GATE_{slot}_{fill_state}",
                    )
                )

        for slot, gate in zip(slot_names[:max_active], active_controller_gates):
            gate_no_cell = layout_index.get((slot, "GATE_NO"))
            if not gate_no_cell:
                raise ConfigurationError(f"No ValveGateLayout GATE_NO cell for {slot}")
            hmi_gate = gate_number(gate)
            ops.append(
                Operation(
                    "WRITE", gate_no_cell, hmi_gate,
                    note=f"VALVE_GATE_{slot}:HMI_{hmi_gate}:RAW_{gate}",
                )
            )

            gate_fields = fields_by_gate.get(gate, [])
            holding_state_key = ""
            for candidate in gate_fields:
                if (
                    clean_text(candidate.get("STATUS")).upper() == "MAPPED"
                    and clean_text(candidate.get("FIELD")).upper() == "HOLDING_STATE"
                ):
                    holding_state_key = clean_text(candidate.get("DATA KEY"))
                    break

            # "Valv. On cuando 2a. Presion" is the master switch for its
            # Retardo/Tiempo columns. Values may remain stored in the controller
            # while the function is OFF, so those residual values must never be
            # printed. Treat a missing state as disabled for the same reason.
            holding_enabled = (
                bool(holding_state_key)
                and holding_state_key in values
                and clean_text(values[holding_state_key]).upper() == "ON"
            )

            for field_row in gate_fields:
                status = clean_text(field_row.get("STATUS")).upper()
                field = clean_text(field_row.get("FIELD")).upper()
                data_key = clean_text(field_row.get("DATA KEY"))
                if status != "MAPPED" or field == "SELECTOR":
                    continue
                if not data_key:
                    raise ConfigurationError(f"ValveGateFields Gate {gate}/{field} has no DATA KEY")

                cell = layout_index.get((slot, field))
                if not cell:
                    raise ConfigurationError(f"No ValveGateLayout cell for {slot}/{field}")

                if field in {"HOLDING_DELAY", "HOLDING_TIME"} and not holding_enabled:
                    # The slot itself is active, but these two dependent fields
                    # are not applicable while the 2nd-pressure function is OFF.
                    # Clear them and shade only these cells with the standard
                    # inactive fill; do not gray the rest of the Valve Gate row.
                    ops.append(
                        Operation(
                            "CLEAR",
                            cell,
                            note=f"VALVE_GATE_{gate}:{field}_DISABLED",
                        )
                    )
                    ops.append(
                        Operation(
                            "COPY_FILL",
                            cell,
                            ref_cell=inactive_fill_ref,
                            note=f"VALVE_GATE_{gate}:{field}_INACTIVE",
                        )
                    )
                    continue

                if data_key not in values:
                    # The physical slot was reset before writing. Keep the field
                    # blank when its source parameter is unavailable.
                    continue

                display_value = values[data_key]
                if field in {"START_CON", "STOP_CON"}:
                    display_value = self._translate_valve_gate_condition(
                        group, layout_id, field, display_value
                    )
                elif group == JUPITER_GROUP and field in {"START_USE", "HOLDING_STATE"}:
                    display_value = self._jupiter_checkbox_value(display_value)
                    if display_value is None:
                        # Slot reset above already blanked the checkbox while
                        # retaining the active-row fill.
                        continue
                ops.append(
                    Operation(
                        "WRITE",
                        cell,
                        self._display_value(display_value),
                        note=f"VALVE_GATE_{gate}:{data_key}",
                    )
                )

        return ops, active_gates

    @staticmethod
    def _valve_gate_hmi_number(controller_gate: int) -> int:
        """Convert controller Valve Gate index to the number shown on the HMI."""
        if controller_gate == 9:
            raise ConfigurationError(
                "Valve Gate controller index 9 is reserved and must be ignored"
            )
        return controller_gate if controller_gate < 9 else controller_gate - 1

    def _translate_valve_gate_condition(
        self,
        group: str,
        layout_id: str,
        field: str,
        value: Any,
    ) -> Any:
        """Translate Valve Gate Start/Stop states for the selected family.

        Jupiter uses its own direct 0=POSITION / 1=TIME contract and must never
        fall through to the generation-specific Zeres StateMaps. DataResolver
        normally supplies the translated Jupiter text already; accepting the raw
        controller code here as well keeps PlanBuilder safe for isolated callers.
        """
        field_u = clean_text(field).upper()
        if field_u not in {"START_CON", "STOP_CON"}:
            return value
        if group == JUPITER_GROUP:
            text_value = clean_text(value).upper()
            if text_value in {"POSITION", "TIME"}:
                return text_value

            raw_key = normalize_control_value(value)
            settings = self.mapping.valve_gate_settings(group, layout_id)
            map_id = clean_text(settings.get("CONTROL_MODE_MAP")) or "JUPITER_GATE_CONTROL"

            if self.data is None:
                direct_map = {0: "POSITION", 1: "TIME"}
                if raw_key not in direct_map:
                    raise SourceDataError(
                        f"Unknown Jupiter Valve Gate control mode {value!r}; expected 0=POSITION or 1=TIME"
                    )
                return direct_map[raw_key]

            if map_id not in self.data.state_maps:
                raise ConfigurationError(
                    f"Data.xlsx StateMap {map_id!r} configured for Jupiter Valve Gates does not exist."
                )
            state_map = {
                normalize_control_value(k): clean_text(v).upper()
                for k, v in self.data.state_maps[map_id].items()
            }
            if raw_key not in state_map:
                raise SourceDataError(
                    f"Unknown Jupiter Valve Gate control mode {value!r} using {map_id}"
                )
            translated = state_map[raw_key]
            if translated not in {"POSITION", "TIME"}:
                raise ConfigurationError(
                    f"Jupiter Valve Gate StateMap {map_id!r} returned unsupported value {translated!r}."
                )
            return translated

        # Keeping DataCatalog optional preserves compatibility for isolated planner
        # tests/callers that already provide display text. Production always passes it.
        if self.data is None:
            return value

        kind = "START" if field_u == "START_CON" else "STOP"
        setting = f"VALVE_GATE_{kind}_STATE_MAP_{clean_text(group).upper()}"
        map_id = clean_text(self.data.cfg(setting))
        if not map_id:
            raise ConfigurationError(
                f"Data.xlsx is missing Config setting {setting} for Valve Gate {kind}."
            )
        if map_id not in self.data.state_maps:
            raise ConfigurationError(
                f"Data.xlsx StateMap {map_id!r} configured by {setting} does not exist."
            )

        raw_key = normalize_control_value(value)
        state_map = {
            normalize_control_value(k): v
            for k, v in self.data.state_maps[map_id].items()
        }
        if raw_key not in state_map:
            raise SourceDataError(
                f"Unknown Valve Gate {kind} state {value!r} for {group} using {map_id}"
            )
        return state_map[raw_key]

    @staticmethod
    def _slot_sort_key(slot: str) -> tuple[int, str]:
        text = clean_text(slot).upper()
        digits = "".join(ch for ch in text if ch.isdigit())
        return (int(digits) if digits else 10**9, text)
