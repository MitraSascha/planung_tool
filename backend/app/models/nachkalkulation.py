"""Pydantic-Read-Modelle für die Nachkalkulations-API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class NachkalkulationItemRead(BaseModel):
    item_id: int
    artikelnummer: str | None = None
    name: str
    unit: str | None = None
    ist_qty: float
    preis_eur: float | None = None
    position_sum: float
    note: str | None = None


class NachkalkulationSectionRead(BaseModel):
    section_number: int | None = None
    section_name: str | None = None
    items: list[NachkalkulationItemRead] = Field(default_factory=list)
    subtotal: float = 0.0
    item_count: int = 0


class NachkalkulationResultRead(BaseModel):
    project_slug: str
    project_name: str
    items_total: int
    sections_total: int
    grand_total: float
    items_verbaut: int = 0
    sections: list[NachkalkulationSectionRead] = Field(default_factory=list)
