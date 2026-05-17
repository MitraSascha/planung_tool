from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.offers import OfferImportPreview


KNOWN_ITEM_FIELDS: tuple[str, ...] = (
    "position_label",
    "article_no",
    "name",
    "description",
    "qty",
    "unit",
    "unit_price_net_eur",
    "total_net_eur",
    "vat_rate",
    "notes",
)

# Either a per-unit price or a line-total must be present, otherwise the
# table is not an offer (probably a stock list, a bauphysik sheet, or a
# heating-design import that was uploaded to the wrong slot).
CORE_REQUIRED_FIELDS: tuple[str, ...] = ("unit_price_net_eur", "total_net_eur")


@dataclass
class OfferColumnMapping:
    item_columns: dict[str, str] = field(default_factory=dict)
    header_overrides: dict[str, str | float | None] = field(default_factory=dict)


class OfferImporterError(ValueError):
    """Raised when a source file cannot be parsed as an offer."""


class OfferImporter(ABC):
    source_name: str = "abstract"
    display_name: str = "Abstract offer importer"
    accepts_extensions: tuple[str, ...] = ()

    @abstractmethod
    def can_handle(self, filename: str, content_head: bytes) -> bool:
        ...

    @abstractmethod
    def parse(
        self,
        filename: str,
        content: bytes,
        mapping: OfferColumnMapping | None = None,
    ) -> OfferImportPreview:
        ...
