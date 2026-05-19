"""Match Heizkörper-Positionen aus Angeboten auf einzelne heating_circuits.

Workflow:
  1. Lese alle Heizkreise des Projekts (sortiert nach position).
  2. Lese alle Angebots-Positionen, deren Text Heizkörper-Schlagworte
     enthält und deren position_label dem Schema "<wohnung>.<pos>" folgt.
  3. Gruppiere Heizkörper-Positionen nach Wohnungs-Nummer (sortiert).
  4. Ordne Heizkreis i ⇒ Heizkörper-Gruppe i nach Index zu — robust gegen
     Wohnungs-Nummern-Offsets (z.B. Angebots-Wohnungen 3..16 ↔ Heizkreise 1..14,
     weil Wohnungen 1+2 im Angebot Pauschalen sind).
  5. Setze ``heating_circuits.radiator_type`` als zusammengefasste Liste.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from sqlalchemy.orm import Session, selectinload

from app.db.orm_models import (
    HeatingCircuit,
    HeatingDesign,
    Offer,
    OfferItem,
    Project,
)


RADIATOR_KEYWORDS: tuple[str, ...] = ("heizk", "badheizk", " hk ", "radiator")
POSITION_LABEL_RE = re.compile(r"^\s*(\d+)\.(\d+)\s*$")
MAX_RADIATOR_TYPE_LEN = 255  # DB-Spalte ist VARCHAR(255)


def _looks_like_radiator(item: OfferItem) -> bool:
    text = f" {item.name or ''} {item.description or ''} ".lower()
    return any(kw in text for kw in RADIATOR_KEYWORDS)


def _short_label(item: OfferItem) -> str:
    """Kompakte Bezeichnung für Konkatenation: 'Nx <Name>'.

    Nutzt name (falls vorhanden), sonst gekürzte description.
    """
    raw = (item.name or item.description or "").strip()
    # Lange RAL-/Maßangaben rausschneiden, aber Modell stehen lassen
    raw = re.sub(r"\s+", " ", raw)
    qty = item.qty
    qty_prefix = ""
    if qty and qty != 1:
        qty_prefix = f"{int(qty) if float(qty).is_integer() else qty}× "
    return f"{qty_prefix}{raw}"


def _group_radiators_by_wohnung(
    items: Iterable[OfferItem],
) -> dict[int, list[OfferItem]]:
    groups: dict[int, list[OfferItem]] = defaultdict(list)
    for item in items:
        if not item.position_label:
            continue
        m = POSITION_LABEL_RE.match(item.position_label)
        if not m:
            continue
        if not _looks_like_radiator(item):
            continue
        wohnung_nr = int(m.group(1))
        groups[wohnung_nr].append(item)
    # Sortiere innerhalb jeder Gruppe nach position_index für stabile Reihenfolge
    for nr in groups:
        groups[nr].sort(key=lambda x: x.position_index)
    return groups


def _join_radiator_labels(items: list[OfferItem]) -> str:
    parts = [_short_label(it) for it in items]
    joined = " + ".join(p for p in parts if p)
    if len(joined) <= MAX_RADIATOR_TYPE_LEN:
        return joined
    # Truncate konservativ am letzten ' + ' vor dem Limit
    cutoff = joined.rfind(" + ", 0, MAX_RADIATOR_TYPE_LEN - 1)
    if cutoff <= 0:
        return joined[: MAX_RADIATOR_TYPE_LEN - 1] + "…"
    return joined[:cutoff] + " …"


def apply_radiator_offers(db: Session, project_id: int) -> dict:
    """Schreibe radiator_type pro heating_circuit aus Angebots-Positionen.

    Returns:
        Stats-Dict: ``{circuits_total, circuits_matched, wohnung_groups,
        unmatched_groups, strategy}``.
    """
    project = (
        db.query(Project)
        .options(selectinload(Project.offers).selectinload(Offer.items))
        .filter(Project.id == project_id)
        .one_or_none()
    )
    if project is None:
        return {"error": "project_not_found"}

    design = (
        db.query(HeatingDesign)
        .filter(HeatingDesign.project_id == project_id)
        .one_or_none()
    )
    if design is None:
        return {"error": "no_heating_design", "circuits_matched": 0}

    circuits = (
        db.query(HeatingCircuit)
        .filter(HeatingCircuit.design_id == design.id)
        .order_by(HeatingCircuit.position)
        .all()
    )
    if not circuits:
        return {"error": "no_circuits", "circuits_matched": 0}

    # Sammle Heizkörper-Positionen aus allen Angeboten dieses Projekts
    all_items: list[OfferItem] = []
    for offer in project.offers:
        all_items.extend(offer.items)

    groups = _group_radiators_by_wohnung(all_items)
    if not groups:
        # Nichts zu matchen: bestehende radiator_type unberührt lassen
        return {
            "circuits_total": len(circuits),
            "circuits_matched": 0,
            "wohnung_groups": 0,
            "strategy": "no_offer_radiators",
        }

    # Strategie wählen:
    # - Falls Wohnungs-Nummern direkt zu circuit.position passen → 1:1 by number
    # - Sonst → 1:1 by sorted index (gleicht Offsets aus)
    sorted_group_keys = sorted(groups.keys())
    circuit_positions = [c.position for c in circuits]
    direct_match_count = sum(1 for p in circuit_positions if p in groups)

    if direct_match_count >= len(circuits) * 0.8:
        strategy = "direct"

        def assign_for(c: HeatingCircuit) -> list[OfferItem] | None:
            return groups.get(c.position)
    else:
        strategy = "indexed"
        index_map = dict(zip(range(len(circuits)), sorted_group_keys))

        def assign_for(c: HeatingCircuit) -> list[OfferItem] | None:
            idx = circuits.index(c)
            key = index_map.get(idx)
            return groups.get(key) if key is not None else None

    matched = 0
    for c in circuits:
        items = assign_for(c)
        if not items:
            continue
        label = _join_radiator_labels(items)
        if label:
            c.radiator_type = label
            matched += 1

    db.commit()

    return {
        "circuits_total": len(circuits),
        "circuits_matched": matched,
        "wohnung_groups": len(groups),
        "unmatched_groups": max(0, len(groups) - matched),
        "strategy": strategy,
    }
