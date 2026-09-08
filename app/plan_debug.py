from __future__ import annotations

import csv
from pathlib import Path

from .plan import GenerationPlan
from .utils import scalar_for_excel


def write_plan_csv(path: Path, plan: GenerationPlan) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["SEQ", "KIND", "CELL", "VALUE", "REF_CELL", "NOTE"])
        for idx, op in enumerate(plan.operations, start=1):
            writer.writerow([
                idx,
                op.kind,
                op.cell,
                scalar_for_excel(op.value),
                op.ref_cell or "",
                op.note or "",
            ])
