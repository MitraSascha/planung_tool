"""Material-Catalog-Endpoint: Dropdown-Quelle für die Materialerfassung
im Tagesbericht (siehe ``services/material_catalog.py``).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import User
from app.services.auth import get_current_user
from app.services.material_catalog import (
    available_categories,
    available_types,
    search as catalog_search,
)

router = APIRouter()


class MaterialCatalogRead(BaseModel):
    id: int
    artikelnummer: str
    beschreibung_1: str
    beschreibung_2: str | None = None
    listenpreis_eur: float | None = None
    nettowert_eur: float | None = None
    einheit: str | None = None
    kategorie: str | None = None
    typ: str | None = None


@router.get("", response_model=list[MaterialCatalogRead])
def list_material_catalog(
    q: str | None = Query(None, description="Volltext-Filter auf Beschreibung + Artikelnummer"),
    kategorie: str | None = Query(None, description="Kategorie-Filter: standard | brandschutz | isolierung"),
    typ: str | None = Query(None, description="Material-Typ: rohr | ventil | formstueck | sonstiges"),
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MaterialCatalogRead]:
    """Liefert die aktive Materialliste alphabetisch sortiert. Filter via ``q``,
    ``kategorie``, ``typ`` (alle kombinierbar).

    Auth: jeder eingeloggte User (Monteure brauchen das im Tagesbericht).
    Server-seitig sortiert + gefiltert — Frontend rendert nur die Hits.
    """
    rows = catalog_search(db, query=q, kategorie=kategorie, typ=typ, limit=limit)
    return [
        MaterialCatalogRead(
            id=r.id,
            artikelnummer=r.artikelnummer,
            beschreibung_1=r.beschreibung_1,
            beschreibung_2=r.beschreibung_2,
            listenpreis_eur=r.listenpreis_eur,
            nettowert_eur=r.nettowert_eur,
            einheit=r.einheit,
            kategorie=r.kategorie,
            typ=r.typ,
        )
        for r in rows
    ]


@router.get("/categories", response_model=list[str])
def list_categories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[str]:
    """Distinct-Liste der vorhandenen Kategorien für die Filter-Chips."""
    return available_categories(db)


@router.get("/types", response_model=list[str])
def list_types(
    kategorie: str | None = Query(None, description="Falls gesetzt: nur Typen die in dieser Kategorie vorkommen"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[str]:
    """Distinct-Liste der Typen. Mit ``kategorie`` eingeschränkt — so kennt
    das Frontend nur Chips für tatsächlich verfügbare Typen."""
    return available_types(db, kategorie=kategorie)
