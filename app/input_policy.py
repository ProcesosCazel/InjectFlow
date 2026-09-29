from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import SourceDataError

JUPITER_GROUP = "HAITIAN_JUPITER_TWOSHOT"


@dataclass(frozen=True)
class InputPolicy:
    """Family input contract shared by the CLI and the desktop bridge.

    XML_ONLY cannot be overridden by a stale CSV or by a client flag.
    Zeres retains its existing optional-resultants workflow.
    """

    input_mode: str = "DAT_OPTIONAL_RESUL"
    param_extension: str = ".dat"
    param_display: str = "Param.dat"
    supports_resultants: bool = True
    requires_injection_control: bool = True

    def validate_param_path(self, path: Path) -> None:
        if Path(path).suffix.lower() != self.param_extension:
            raise SourceDataError(
                f"Se requiere un archivo {self.param_extension} para esta familia; "
                f"se recibio: {Path(path).name}"
            )

    def execution_mode(self, include_resultants: bool) -> str:
        if not self.supports_resultants:
            return "SOLO PARAMETROS XML"
        return "PARAMETROS + RESULTANTES" if include_resultants else "SOLO PARAM.DAT"

    def display_mode(self, include_resultants: bool) -> str:
        if not self.supports_resultants:
            return "Solo par\u00e1metros (XML)"
        return "Par\u00e1metros + Resultantes" if include_resultants else "Solo Param.dat"

    def as_dict(self) -> dict[str, object]:
        return {
            "inputMode": self.input_mode,
            "paramExtension": self.param_extension,
            "paramDisplay": self.param_display,
            "supportsResultants": self.supports_resultants,
            "requiresInjectionControl": self.requires_injection_control,
        }


def policy_for_group(group: str) -> InputPolicy:
    if str(group).strip().upper() == JUPITER_GROUP:
        return InputPolicy("XML_ONLY", ".xml", "Par\u00e1metros XML", False, False)
    return InputPolicy()
