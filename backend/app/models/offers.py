from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


OfferSourceType = Literal["xlsx", "csv", "ugl", "pdf", "manual"]


class OfferItemBase(BaseModel):
    position_index: int = 0
    position_label: str | None = None
    article_no: str | None = None
    name: str | None = None
    description: str | None = None
    qty: float | None = None
    unit: str | None = None
    unit_price_net_eur: float | None = None
    total_net_eur: float | None = None
    vat_rate: float | None = None
    notes: str | None = None


class OfferItemRead(OfferItemBase):
    id: int


class OfferBase(BaseModel):
    supplier_name: str
    offer_no: str | None = None
    offer_date: date | None = None
    currency: str = "EUR"
    total_net_eur: float | None = None
    total_gross_eur: float | None = None
    vat_rate: float | None = None
    notes: str | None = None


class OfferWrite(OfferBase):
    source_type: OfferSourceType = "manual"
    source_file: str | None = None
    attached_file_path: str | None = None
    items: list[OfferItemBase] = Field(default_factory=list)


class OfferRead(OfferBase):
    id: int
    project_slug: str
    source_type: OfferSourceType
    source_file: str | None = None
    attached_file_path: str | None = None
    imported_at: datetime
    imported_by_user_id: int | None = None
    imported_by_username: str | None = None
    updated_at: datetime
    items: list[OfferItemRead] = Field(default_factory=list)


class OfferSummary(BaseModel):
    """Light-weight list view (no items)."""

    id: int
    project_slug: str
    supplier_name: str
    offer_no: str | None = None
    offer_date: date | None = None
    currency: str = "EUR"
    total_net_eur: float | None = None
    total_gross_eur: float | None = None
    source_type: OfferSourceType
    source_file: str | None = None
    attached_file_path: str | None = None
    imported_at: datetime
    item_count: int


class OfferImportPreview(BaseModel):
    """Preview returned by an importer before the user confirms persistence."""

    source_type: OfferSourceType
    source_file: str
    offer: OfferBase
    items: list[OfferItemBase]
    warnings: list[str] = Field(default_factory=list)
    detected_columns: dict[str, str] = Field(default_factory=dict)


class OfferPdfManualForm(BaseModel):
    """Used when the user uploads a PDF and types the headline figures by hand."""

    supplier_name: str
    offer_no: str | None = None
    offer_date: date | None = None
    total_net_eur: float | None = None
    total_gross_eur: float | None = None
    vat_rate: float | None = None
    notes: str | None = None
