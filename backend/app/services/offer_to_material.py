"""Synchronisiert offer_items → material_items.

Beim Hochladen eines Angebots wird pro offer_item ein material_item
angelegt (sofern noch nicht vorhanden), damit der Bauleiter / Monteur
die Angebots-Positionen direkt im Material-Sheet als Soll-Liste hat
und Verbrauchsbuchungen darauf machen kann.

Idempotenz:
  - Bestehende material_items mit derselben offer_item_id werden
    *aktualisiert* (Name/Menge/Einheit), nicht dupliziert.
  - material_items ohne offer_item_id (manuell angelegte Extras) bleiben
    unangetastet.
"""
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from app.db.orm_models import MaterialItem, Offer, OfferItem, ProjectSection


def _is_skipable(item: OfferItem) -> bool:
    """Pauschal-Positionen wie 'Anfahrt', 'Entsorgung', 'Std', 'pauschal'
    sind keine verbaubaren Materialien — überspringen.
    """
    if not item.qty or item.qty <= 0:
        return True
    unit = (item.unit or "").strip().lower()
    if unit in {"pauschal", "std", "stunde", "stunden", "h", "psch"}:
        return True
    return False


def _guess_section_number(offer: Offer, sections: list[ProjectSection]) -> int | None:
    """Heuristik: wenn source_file/supplier/offer_no genau einen
    Section-Namen enthält, gibt diese Section-Nummer zurück.
    Sonst None (User muss manuell zuordnen).
    """
    haystack = " ".join(
        [
            offer.source_file or "",
            offer.notes or "",
            offer.offer_no or "",
        ]
    ).lower()
    matches = [s.number for s in sections if s.name and s.name.lower() in haystack]
    if len(matches) == 1:
        return matches[0]
    return None


def _norm_key(article_no: str | None, name: str) -> str:
    """Stabiler Match-Key für Re-Upload-Dedup, normalisiert
    Whitespace und Case."""
    parts = []
    if article_no:
        parts.append(article_no.strip().lower())
    parts.append(" ".join((name or "").lower().split()))
    return "|".join(parts)


def sync_offer_to_material(db: Session, offer_id: int) -> dict:
    """Lege/aktualisiere material_items für ein einzelnes Offer.

    Dedup-Strategie (in dieser Reihenfolge):
      1) Match per offer_item_id (alter Stand)
      2) Match per (article_no, normalisierter Name) gegen andere
         material_items dieses Projekts, die entweder aus einem alten
         Angebot stammen (offer_item_id wurde durch ein vorheriges
         offer-delete SET NULL gesetzt) oder aus früherem Re-Upload.

    Manuelle Stamm-Einträge (kind='werkzeug' ODER offer_item_id IS NULL
    UND existing_mi.created vor diesem Offer) werden NICHT übernommen —
    der User hat sie bewusst angelegt.

    Returns Stats: ``{created, updated, skipped, relinked, guessed_section}``.
    """
    offer = (
        db.query(Offer)
        .options(selectinload(Offer.items))
        .filter(Offer.id == offer_id)
        .one_or_none()
    )
    if offer is None:
        return {"error": "offer_not_found"}

    sections = (
        db.query(ProjectSection)
        .filter(ProjectSection.project_id == offer.project_id)
        .order_by(ProjectSection.number)
        .all()
    )
    guessed_section = _guess_section_number(offer, sections)

    # 1) Vorhandene material_items dieses Projekts
    all_project_items = (
        db.query(MaterialItem)
        .filter(MaterialItem.project_id == offer.project_id)
        .all()
    )
    # by_offer_item_id enthält NUR Verlinkungen zum aktuellen Offer
    # (Re-Sync desselben Angebots) — Items, die zu anderen Offers gehören,
    # dürfen über by_norm_key re-linked werden.
    this_offer_item_ids = {i.id for i in offer.items}
    by_offer_item_id = {
        m.offer_item_id: m
        for m in all_project_items
        if m.offer_item_id is not None and m.offer_item_id in this_offer_item_ids
    }
    # Match-Index per Name für Re-Upload-Dedup. Werkzeug-Einträge
    # ausschließen, damit ein Angebot keinen Werkzeug-Stamm "stiehlt".
    # Auch verlinkte material_items werden indiziert: wenn ein Re-Upload
    # die selbe Position bringt, wird das material_item auf das neue
    # offer_item umverlinkt (das alte Offer-Item zeigt dann auf nichts
    # mehr — gewünscht, weil es überholt ist).
    by_norm_key: dict[str, MaterialItem] = {}
    for m in all_project_items:
        if m.kind == "werkzeug":
            continue
        # article_no haben wir auf material_items nicht — Fallback nur per Name.
        key = _norm_key(None, m.name)
        # Bei Kollision: der älteste (kleinste ID) gewinnt — stabilstes Verhalten.
        if key not in by_norm_key or m.id < by_norm_key[key].id:
            by_norm_key[key] = m

    # IDs der zum *aktuellen* Offer gehörenden material_items — diese
    # dürfen wir nicht über by_norm_key "umverlinken" (sie sind ja bereits
    # via by_offer_item_id korrekt zugeordnet).
    already_linked_to_this_offer = {m.id for m in by_offer_item_id.values()}

    created = 0
    updated = 0
    relinked = 0
    skipped = 0

    for item in offer.items:
        if _is_skipable(item):
            skipped += 1
            continue
        name = (item.name or item.description or "").strip()
        if not name:
            skipped += 1
            continue
        # Auf 255 Zeichen kappen (DB-Limit auf material_items.name)
        name = name[:255]

        # 1) Direkter Match per offer_item_id (Re-sync desselben Offers)
        existing_mi = by_offer_item_id.get(item.id)

        # 2) Sonst per Name → re-link an dieses neue offer_item
        if existing_mi is None:
            key = _norm_key(item.article_no, name)
            relink_candidate = by_norm_key.get(key)
            if relink_candidate is not None and relink_candidate.id not in already_linked_to_this_offer:
                existing_mi = relink_candidate
                existing_mi.offer_item_id = item.id
                relinked += 1
                # Aus dem Index entfernen — kein zweiter Re-Link auf dasselbe
                del by_norm_key[key]
                already_linked_to_this_offer.add(existing_mi.id)

        if existing_mi is not None:
            existing_mi.name = name
            existing_mi.soll_qty = item.qty
            existing_mi.unit = item.unit
            # section_number nur setzen, wenn noch nicht vorhanden (manuelle
            # Zuweisung des Users hat Vorrang vor der Heuristik).
            if existing_mi.section_number is None and guessed_section is not None:
                existing_mi.section_number = guessed_section
            updated += 1
        else:
            mi = MaterialItem(
                project_id=offer.project_id,
                offer_item_id=item.id,
                section_number=guessed_section,
                kind="material",
                name=name,
                soll_qty=item.qty,
                ist_qty=0.0,
                unit=item.unit,
                status="vorhanden",
            )
            db.add(mi)
            created += 1

    db.flush()
    return {
        "created": created,
        "updated": updated,
        "relinked": relinked,
        "skipped": skipped,
        "guessed_section": guessed_section,
    }


def sync_all_offers_to_material(db: Session, project_id: int) -> dict:
    """Wende sync_offer_to_material auf alle Angebote eines Projekts an."""
    offers = db.query(Offer).filter(Offer.project_id == project_id).all()
    totals = {"created": 0, "updated": 0, "skipped": 0, "offers": 0}
    for o in offers:
        stats = sync_offer_to_material(db, o.id)
        if "error" in stats:
            continue
        totals["offers"] += 1
        for k in ("created", "updated", "skipped"):
            totals[k] += stats[k]
    return totals
