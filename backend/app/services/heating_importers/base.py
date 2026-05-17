from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.heating import HeatingDesignImportPreview


# Canonical field names that adapters must map to.
KNOWN_CIRCUIT_FIELDS: tuple[str, ...] = (
    "strand",
    "room",
    "floor",
    "radiator_type",
    "area_sqm",
    "heat_load_w",
    "volume_flow_lph",
    "pressure_drop_pa",
    "pipe_length_m",
    "valve_type",
    "valve_preset",
    "kv_value",
    "notes",
)


@dataclass
class ColumnMapping:
    """Mapping from external column names to canonical heating_circuit fields.

    keys   = canonical field name (from KNOWN_CIRCUIT_FIELDS or "system_type", ...)
    values = column name as it appears in the source file
    """

    circuit_columns: dict[str, str] = field(default_factory=dict)
    design_overrides: dict[str, float | str | None] = field(default_factory=dict)


class HeatingImporterError(ValueError):
    """Raised when a source file cannot be parsed."""


class HeatingImporter(ABC):
    """A strategy that converts source bytes into a HeatingDesignImportPreview.

    Subclasses must declare ``source_name`` (used in the DB ``source`` column)
    and provide ``can_handle`` (cheap detection) and ``parse`` (full read).
    """

    source_name: str = "abstract"
    display_name: str = "Abstract importer"
    accepts_extensions: tuple[str, ...] = ()

    @abstractmethod
    def can_handle(self, filename: str, content_head: bytes) -> bool:
        """Return True if this adapter is willing to attempt parsing.

        ``content_head`` is the first few KB of the upload, useful for magic-byte sniffing.
        """

    @abstractmethod
    def parse(
        self,
        filename: str,
        content: bytes,
        mapping: ColumnMapping | None = None,
    ) -> HeatingDesignImportPreview:
        """Parse the upload into a structured preview.

        If ``mapping`` is provided, it overrides the adapter's own auto-detection
        (useful when the user has corrected the mapping in the preview UI).
        """
