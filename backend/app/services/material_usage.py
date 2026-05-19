"""Service-Funktionen für material_usages.

Aggregiert verbaute Mengen (aus `material_usages`) zurück in
``material_items.ist_qty``, sodass das Status-Feld
(vorhanden/fehlt/bestellt/geliefert) und alle Reports immer konsistent
sind, ohne dass UI-Code den Soll/Ist-Vergleich selbst rechnen muss.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.orm_models import MaterialItem, MaterialUsage


def recalc_ist_qty(db: Session, material_item_id: int) -> float | None:
    """Setze ``material_items.ist_qty`` als Summe aller usages.

    Wird nach jedem CREATE/DELETE einer Usage aufgerufen. Returns the
    new ist_qty (oder None wenn das Item nicht mehr existiert).
    """
    item = db.query(MaterialItem).filter(MaterialItem.id == material_item_id).one_or_none()
    if item is None:
        return None
    total = (
        db.query(func.coalesce(func.sum(MaterialUsage.qty_used), 0.0))
        .filter(MaterialUsage.material_item_id == material_item_id)
        .scalar()
    )
    item.ist_qty = float(total) if total is not None else 0.0
    db.flush()
    return item.ist_qty


def find_material_drift(db: Session, project_id: int, tolerance: float = 1e-6) -> list[dict]:
    """Liefere alle material_items, deren gespeicherte ist_qty von der
    Summe ihrer usages abweicht.

    Drift entsteht, wenn:
      - jemand ist_qty manuell per DB/PATCH gepatcht hat
      - eine recalc_ist_qty-Operation während einer Transaktion
        teilweise gescheitert ist
      - ein Schema-Migrations-Backfill vergessen wurde

    ``tolerance`` toleriert Floating-Point-Rundung; alles darüber gilt
    als echte Drift, die heilen sollte.
    """
    rows = (
        db.query(
            MaterialItem.id,
            MaterialItem.name,
            MaterialItem.ist_qty,
            func.coalesce(func.sum(MaterialUsage.qty_used), 0.0),
        )
        .outerjoin(MaterialUsage, MaterialUsage.material_item_id == MaterialItem.id)
        .filter(MaterialItem.project_id == project_id)
        .group_by(MaterialItem.id, MaterialItem.name, MaterialItem.ist_qty)
        .all()
    )
    drifts = []
    for item_id, name, stored_ist, computed_ist in rows:
        stored = float(stored_ist or 0.0)
        computed = float(computed_ist or 0.0)
        if abs(stored - computed) > tolerance:
            drifts.append(
                {
                    "material_item_id": item_id,
                    "name": name,
                    "stored_ist": stored,
                    "computed_ist": computed,
                    "delta": stored - computed,
                }
            )
    return drifts


def heal_material_drift(db: Session, project_id: int) -> dict:
    """Korrigiere alle drift-behafteten ist_qty per recalc_ist_qty.
    Returns: ``{healed, items}``.
    """
    drifts = find_material_drift(db, project_id)
    for d in drifts:
        recalc_ist_qty(db, d["material_item_id"])
    db.flush()
    return {"healed": len(drifts), "items": [d["material_item_id"] for d in drifts]}
