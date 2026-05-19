"""Artikelstamm-Suche (externe DATANORM-DB, > 2 Mio Artikel).

Stellt zwei Endpunkte bereit:

  * ``GET  /api/articles/search?q=…``  — Live-Suche aus dem Material-Picker
  * ``POST /api/projects/{slug}/material-items/from-artikelstamm``
        — legt aus einem Artikelstamm-Eintrag einen neuen MaterialItem im
          Projekt an (source='artikelstamm'). Damit hat der Monteur ad-hoc
          gekauftes Material direkt im Projekt-Stamm verfügbar — und die
          Nachkalkulation kann später per source-Filter alle „nicht im
          Angebot enthaltenen" Posten anzeigen.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import MaterialItem, Project, User
from app.services import artikelstamm
from app.services.auth import (
    PROJECT_READ_ROLES,
    get_current_user,
    require_project_role,
)

router = APIRouter()


# ───────────────────────────────────────────────────────────────────────
# Search
# ───────────────────────────────────────────────────────────────────────


class ArticleHit(BaseModel):
    artikelnummer: str
    kurztext1: str | None = None
    kurztext2: str | None = None
    warengruppe: str | None = None
    mengeneinheit: str | None = None
    preis_eur: float | None = None
    hersteller: str | None = None
    hersteller_artikelnummer: str | None = None
    ean: str | None = None


@router.get("/articles/search", response_model=list[ArticleHit])
def search_artikelstamm(
    q: str = Query(..., min_length=2, description="Suchbegriff (mind. 2 Zeichen)"),
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
) -> list[ArticleHit]:
    """Live-Suche im Artikelstamm. Auth-pflichtig wie der Rest der App,
    aber kein Projekt-Bezug — jeder eingeloggte User kann suchen.

    Wenn die externe DB nicht konfiguriert/erreichbar ist, kommt eine
    leere Liste zurück (kein 5xx — Tool soll auch ohne Artikelstamm
    laufen, die Suche ist dann eben leer)."""
    rows = artikelstamm.search_articles(q, limit=limit)
    return [ArticleHit(**r) for r in rows]


@router.get("/articles/availability")
def availability(
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Frontend kann damit prüfen, ob der Artikelstamm-Tab im Material-
    Picker aktiviert werden soll (DB konfiguriert + reachable)."""
    return {"available": artikelstamm.is_available()}


# ───────────────────────────────────────────────────────────────────────
# Material-Item aus Artikelstamm anlegen
# ───────────────────────────────────────────────────────────────────────


class CreateFromArtikelstamm(BaseModel):
    artikelnummer: str = Field(min_length=1, max_length=32)
    soll_qty: float | None = Field(default=None, ge=0)
    section_number: int | None = None
    note: str | None = None


def _project_or_404(db: Session, slug: str) -> Project:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/projects/{slug}/material-items/from-artikelstamm")
def create_material_item_from_artikelstamm(
    slug: str,
    payload: CreateFromArtikelstamm,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Legt aus einem Artikelstamm-Eintrag einen MaterialItem im Projekt an.

    Idempotenz: wenn ein MaterialItem mit derselben artikelnummer im selben
    Projekt schon existiert (z.B. weil ein Kollege es schon hinzugefügt
    hat), wird dessen ID zurückgegeben — kein Duplikat.

    Permission: jeder Projekt-Mitarbeiter darf das (Monteur kauft ad-hoc
    Material und meldet das). Die source='artikelstamm'-Markierung erlaubt
    der Bauleitung später, alle nicht-im-Angebot-Posten zu filtern.
    """
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    article = artikelstamm.get_article(payload.artikelnummer)
    if article is None:
        raise HTTPException(
            status_code=404,
            detail=f"Artikel {payload.artikelnummer!r} im Artikelstamm nicht gefunden.",
        )

    existing = (
        db.query(MaterialItem)
        .filter(
            MaterialItem.project_id == project.id,
            MaterialItem.artikelstamm_artikelnummer == payload.artikelnummer,
        )
        .first()
    )
    if existing is not None:
        return {
            "id": existing.id,
            "duplicate": True,
            "message": "Artikel war bereits im Projekt-Stamm",
        }

    name_parts = [article.get("kurztext1"), article.get("kurztext2")]
    name = " ".join(p for p in name_parts if p) or article["artikelnummer"]
    if article.get("hersteller"):
        name = f"{article['hersteller']} · {name}"

    item = MaterialItem(
        project_id=project.id,
        user_id=current_user.id,
        section_number=payload.section_number,
        kind="material",
        name=name[:255],
        soll_qty=payload.soll_qty,
        unit=article.get("mengeneinheit"),
        status="vorhanden",
        note=payload.note,
        source="artikelstamm",
        artikelstamm_artikelnummer=article["artikelnummer"],
        artikelstamm_preis_eur=article.get("preis_eur"),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "id": item.id,
        "duplicate": False,
        "name": item.name,
        "unit": item.unit,
        "artikelnummer": item.artikelstamm_artikelnummer,
        "preis_eur": item.artikelstamm_preis_eur,
        "source": item.source,
    }
