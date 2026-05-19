"""Nachkalkulation: Welche Materialien hat der Monteur ad-hoc aus dem
Großhandel (Artikelstamm) verbaut, die NICHT durch das ursprüngliche
Angebot abgedeckt waren?

Basis für Nachträge an den Kunden. Wir filtern auf
``MaterialItem.source == 'artikelstamm'`` (das Tag, das die
Artikelstamm-Suche beim Anlegen setzt) und multiplizieren die Ist-Menge
(durch ``MaterialUsage``-Buchungen aggregiert) mit dem damals geltenden
Listenpreis (``artikelstamm_preis_eur``).

Aggregation gruppiert pro Bauabschnitt — so kann das Office den
Nachtrag analog zur Angebotsstruktur an den Kunden verschicken.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.orm_models import MaterialItem, Project


# ───────────────────────────────────────────────────────────────────────
# Output dataclasses (-> Pydantic models in app/models/nachkalkulation.py)
# ───────────────────────────────────────────────────────────────────────


@dataclass
class NachkalkulationItem:
    item_id: int
    artikelnummer: str | None
    name: str
    unit: str | None
    ist_qty: float
    preis_eur: float | None
    position_sum: float
    note: str | None = None


@dataclass
class NachkalkulationSection:
    section_number: int | None
    section_name: str | None
    items: list[NachkalkulationItem] = field(default_factory=list)
    subtotal: float = 0.0
    item_count: int = 0


@dataclass
class NachkalkulationResult:
    project_slug: str
    project_name: str
    items_total: int
    sections_total: int
    grand_total: float
    sections: list[NachkalkulationSection] = field(default_factory=list)
    # Zähler für Items, die schon eine Ist-Buchung haben (verbaut) — der
    # Rest sind reine "Bestellungen", die noch nicht eingebaut wurden.
    items_verbaut: int = 0


# ───────────────────────────────────────────────────────────────────────
# Service
# ───────────────────────────────────────────────────────────────────────


def nachkalkulation_for_project(
    db: Session,
    project: Project,
) -> NachkalkulationResult:
    """Aggregiere alle ad-hoc-Käufe (``source='artikelstamm'``) eines
    Projekts in eine Nachkalkulations-Sicht.

    Args:
        db: SQLAlchemy-Session (aktiv).
        project: Projekt-Entity (Caller hat slug→project schon aufgelöst).

    Returns:
        ``NachkalkulationResult`` mit Items gruppiert pro Bauabschnitt,
        plus Subtotals und Gesamtsumme netto.
    """
    items = (
        db.query(MaterialItem)
        .filter(
            MaterialItem.project_id == project.id,
            MaterialItem.source == "artikelstamm",
        )
        .order_by(MaterialItem.section_number, MaterialItem.name)
        .all()
    )

    section_name_lookup = {s.number: s.name for s in project.sections}

    # Pro section_number gruppieren — None landet als "Ohne Zuordnung".
    buckets: dict[int | None, list[NachkalkulationItem]] = defaultdict(list)
    items_verbaut = 0
    grand_total = 0.0

    for it in items:
        ist = float(it.ist_qty or 0.0)
        preis = float(it.artikelstamm_preis_eur or 0.0)
        position_sum = round(ist * preis, 2)
        if ist > 0:
            items_verbaut += 1
        grand_total += position_sum
        buckets[it.section_number].append(
            NachkalkulationItem(
                item_id=it.id,
                artikelnummer=it.artikelstamm_artikelnummer,
                name=it.name,
                unit=it.unit,
                ist_qty=round(ist, 3),
                preis_eur=round(preis, 2) if it.artikelstamm_preis_eur is not None else None,
                position_sum=position_sum,
                note=it.note,
            )
        )

    sections: list[NachkalkulationSection] = []
    sorted_keys = sorted(buckets.keys(), key=lambda k: (k is None, k or 0))
    for sec in sorted_keys:
        sec_items = buckets[sec]
        subtotal = round(sum(i.position_sum for i in sec_items), 2)
        sections.append(
            NachkalkulationSection(
                section_number=sec,
                section_name=section_name_lookup.get(sec) if sec is not None else None,
                items=sec_items,
                subtotal=subtotal,
                item_count=len(sec_items),
            )
        )

    return NachkalkulationResult(
        project_slug=project.slug,
        project_name=project.name,
        items_total=len(items),
        sections_total=len(sections),
        grand_total=round(grand_total, 2),
        items_verbaut=items_verbaut,
        sections=sections,
    )
