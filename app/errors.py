class AutomationError(Exception):
    """Base error for the parameter sheet automation."""


class ConfigurationError(AutomationError):
    """Invalid Data.xlsx / Mapeo.xlsx configuration."""


class SourceDataError(AutomationError):
    """Invalid or incomplete Param.dat / Resul.csv input."""


class MissingParameterError(SourceDataError):
    """A logical parameter could not be resolved because its source is unavailable.

    This error is intentionally distinct from malformed/invalid source data so the
    generation process can continue in best-effort mode while reporting exactly
    which parameters were not found.
    """

    def __init__(self, key: str, details: str):
        self.key = str(key)
        self.details = str(details)
        super().__init__(f"{self.key}: {self.details}")


class ProcessWarning(AutomationError):
    """User-facing warning that blocks generation to avoid an incomplete sheet."""


class TemplateError(AutomationError):
    """Template structure is not compatible with the mapping."""


class WriterError(AutomationError):
    """Unable to write the official Excel output."""
