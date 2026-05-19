"""Tests für den Material-Abgleich Angebot ↔ Verbrauch.

Diese Schicht ist kritisch: das Bauleitung verlässt sich darauf, dass
"X von Y Stk verbaut" stimmt. Wenn der Abgleich silently kaputt geht,
wird falsch nachbestellt und auf der Baustelle fehlt Material.

Test-Cases decken die realen Bedrohungen ab:

- Aggregation: ist_qty = SUM(usages.qty_used), immer.
- Re-Upload eines Angebots erzeugt KEINE Duplikate.
- Manuelle Section-Zuweisung überlebt einen Re-Upload.
- Manuelle Stamm-Einträge (kein offer_item_id) bleiben unangetastet.
- Pauschal-Positionen werden nicht zu material_items.
- Verbrauchsbuchungen überleben Löschung von Angebot oder Material.
- Konsistenz-Check entdeckt absichtlich erzeugte Drift.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _enable_sqlite_fk(db_engine):
    """SQLite ignoriert FK-Constraints (und CASCADE/SET NULL) per default.
    Für diesen Test-Modul brauchen wir das echte Verhalten."""
    @event.listens_for(db_engine, "connect")
    def _fk_on(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    # Force-trigger auf bestehender Connection
    with db_engine.connect() as c:
        c.exec_driver_sql("PRAGMA foreign_keys=ON")

from app.db.orm_models import (
    MaterialItem,
    MaterialUsage,
    Offer,
    OfferItem,
    Project,
    ProjectSection,
    User,
)
from app.services.auth import hash_password
from app.services.material_usage import recalc_ist_qty
from app.services.offer_to_material import sync_offer_to_material


# ---------------------------------------------------------------- helpers
def _make_project(db: Session, slug: str) -> Project:
    project = Project(slug=slug, name=f"P {slug}", project_type="standard")
    db.add(project)
    db.flush()
    return project


def _make_sections(db: Session, project: Project, names: list[str]) -> list[ProjectSection]:
    rows = []
    for i, name in enumerate(names, start=1):
        s = ProjectSection(project_id=project.id, number=i, name=name)
        db.add(s)
        rows.append(s)
    db.flush()
    return rows


def _make_user(db: Session, username: str) -> User:
    u = User(
        username=username,
        display_name=username.title(),
        password_hash=hash_password("pw"),
        global_role="bauleitung",
    )
    db.add(u)
    db.flush()
    return u


def _make_offer_with_items(
    db: Session,
    project: Project,
    item_specs: list[tuple[str, str, float, str]],  # (label, name, qty, unit)
    supplier: str = "IMMOMAKS",
) -> Offer:
    """Lege ein Angebot mit Positionen an. label ist position_label."""
    offer = Offer(
        project_id=project.id,
        supplier_name=supplier,
        offer_no=f"ANG-TEST-{supplier}",
        offer_date=date.today(),
        currency="EUR",
        source_type="xlsx",
        source_file=f"test-{supplier}.xlsx",
    )
    db.add(offer)
    db.flush()
    for i, (label, name, qty, unit) in enumerate(item_specs):
        db.add(
            OfferItem(
                offer_id=offer.id,
                position_index=i,
                position_label=label,
                name=name,
                qty=qty,
                unit=unit,
                unit_price_net_eur=10.0,
                total_net_eur=10.0 * qty,
            )
        )
    db.flush()
    return offer


# ---------------------------------------------------------------- 1. Aggregation
def test_usage_aggregation_basic(db_session: Session) -> None:
    """ist_qty = SUM(usages.qty_used), nach Create und nach Delete."""
    project = _make_project(db_session, "agg")
    item = MaterialItem(
        project_id=project.id, kind="material", name="Rohrschelle DN20",
        soll_qty=100.0, unit="Stk",
    )
    db_session.add(item)
    db_session.flush()

    # Drei Buchungen anlegen
    for qty in (10.0, 15.0, 25.0):
        db_session.add(MaterialUsage(
            project_id=project.id, material_item_id=item.id,
            qty_used=qty, used_at=date.today(),
        ))
    db_session.flush()

    new_ist = recalc_ist_qty(db_session, item.id)
    assert new_ist == 50.0
    db_session.refresh(item)
    assert item.ist_qty == 50.0

    # Eine Buchung löschen → ist_qty fällt um 15
    usage_to_delete = db_session.query(MaterialUsage).filter_by(qty_used=15.0).one()
    db_session.delete(usage_to_delete)
    db_session.flush()
    new_ist = recalc_ist_qty(db_session, item.id)
    assert new_ist == 35.0


def test_usage_aggregation_zero_when_no_usages(db_session: Session) -> None:
    project = _make_project(db_session, "agg-zero")
    item = MaterialItem(project_id=project.id, kind="material", name="X", soll_qty=10.0)
    db_session.add(item)
    db_session.flush()
    assert recalc_ist_qty(db_session, item.id) == 0.0


def test_usage_overrun_allowed_and_visible(db_session: Session) -> None:
    """Mehr verbaut als Soll ist erlaubt (Realität: Verschnitt) und sichtbar."""
    project = _make_project(db_session, "overrun")
    item = MaterialItem(project_id=project.id, kind="material", name="X", soll_qty=100.0)
    db_session.add(item)
    db_session.flush()
    db_session.add(MaterialUsage(
        project_id=project.id, material_item_id=item.id,
        qty_used=150.0, used_at=date.today(),
    ))
    db_session.flush()
    assert recalc_ist_qty(db_session, item.id) == 150.0
    db_session.refresh(item)
    # Status bleibt 'vorhanden' — Overrun ist eine View-Schicht-Konzept.
    assert item.ist_qty > item.soll_qty


# ---------------------------------------------------------------- 2. Re-Upload-Dedup
def test_offer_reupload_does_not_duplicate_material_items(db_session: Session) -> None:
    """KRITISCH: Hochladen des gleichen Angebots mehrfach darf KEINE
    duplikatären material_items erzeugen.
    """
    project = _make_project(db_session, "reupload")

    # Initial-Upload
    offer1 = _make_offer_with_items(db_session, project, [
        ("3.001", "COSMO Heizkörper Typ 22 600x920", 2, "Stk"),
        ("3.002", "COSMO Heizkörper Typ 22 900x920", 2, "Stk"),
    ])
    sync_offer_to_material(db_session, offer1.id)
    db_session.commit()
    count1 = db_session.query(MaterialItem).filter_by(project_id=project.id).count()
    assert count1 == 2

    # Lieferant macht eine Korrektur, lädt nochmal hoch → neues Offer,
    # neue offer_item_ids. ABER: gleiche Positionen.
    offer2 = _make_offer_with_items(db_session, project, [
        ("3.001", "COSMO Heizkörper Typ 22 600x920", 2, "Stk"),
        ("3.002", "COSMO Heizkörper Typ 22 900x920", 2, "Stk"),
    ])
    sync_offer_to_material(db_session, offer2.id)
    db_session.commit()
    count2 = db_session.query(MaterialItem).filter_by(project_id=project.id).count()
    assert count2 == count1, f"Re-Upload erzeugte {count2 - count1} Duplikat(e)"


def test_offer_reupload_preserves_manual_section_assignment(db_session: Session) -> None:
    """Wenn der User dem Material einen Abschnitt zugewiesen hat,
    überschreibt Re-Upload die section_number NICHT."""
    project = _make_project(db_session, "reupload-section")
    sections = _make_sections(db_session, project, ["Kellerleitung", "Stränge"])

    offer1 = _make_offer_with_items(db_session, project, [
        ("1.001", "Klemme XY", 10, "Stk"),
    ])
    sync_offer_to_material(db_session, offer1.id)
    db_session.commit()
    mi = db_session.query(MaterialItem).filter_by(project_id=project.id).one()
    assert mi.section_number is None  # Heuristik schlug fehl

    # User weist manuell Abschnitt 2 zu
    mi.section_number = 2
    db_session.commit()

    # Re-Upload
    offer2 = _make_offer_with_items(db_session, project, [
        ("1.001", "Klemme XY", 10, "Stk"),
    ])
    sync_offer_to_material(db_session, offer2.id)
    db_session.commit()
    mi = db_session.query(MaterialItem).filter_by(project_id=project.id).one()
    assert mi.section_number == 2, "Manuelle Section-Zuweisung wurde überschrieben!"


def test_offer_reupload_preserves_usages(db_session: Session) -> None:
    """Wenn der User schon Verbrauch gebucht hat, dürfen die Buchungen
    nicht durch Re-Upload verloren gehen — und das material_item-Match
    muss erhalten bleiben, sonst zeigt das Sheet die Buchungen als
    'gelöscht' an.
    """
    project = _make_project(db_session, "reupload-usage")
    offer1 = _make_offer_with_items(db_session, project, [
        ("1.001", "Rohrschelle DN20", 100, "Stk"),
    ])
    sync_offer_to_material(db_session, offer1.id)
    db_session.commit()
    mi = db_session.query(MaterialItem).filter_by(project_id=project.id).one()
    original_mi_id = mi.id

    # Verbuche 30 Stk
    db_session.add(MaterialUsage(
        project_id=project.id, material_item_id=mi.id,
        qty_used=30.0, used_at=date.today(),
    ))
    db_session.flush()
    recalc_ist_qty(db_session, mi.id)
    db_session.commit()

    # Re-Upload
    offer2 = _make_offer_with_items(db_session, project, [
        ("1.001", "Rohrschelle DN20", 100, "Stk"),
    ])
    sync_offer_to_material(db_session, offer2.id)
    db_session.commit()

    # Nur EIN material_item, dasselbe wie vorher, und ist_qty=30 erhalten.
    items = db_session.query(MaterialItem).filter_by(project_id=project.id).all()
    assert len(items) == 1
    assert items[0].id == original_mi_id
    assert items[0].ist_qty == 30.0

    # Buchung zeigt noch auf valides material_item.
    usage = db_session.query(MaterialUsage).one()
    assert usage.material_item_id == original_mi_id


# ---------------------------------------------------------------- 3. Manuelle Stamm-Einträge
def test_manual_material_item_not_touched_by_offer_sync(db_session: Session) -> None:
    """Ein vom User manuell angelegtes Material (kein offer_item_id)
    darf vom Angebot-Sync nicht angefasst werden."""
    project = _make_project(db_session, "manual")
    manual = MaterialItem(
        project_id=project.id, kind="werkzeug", name="Schweißgerät",
        soll_qty=1.0, unit="Stk", status="vorhanden",
    )
    db_session.add(manual)
    db_session.flush()
    manual_id = manual.id

    offer = _make_offer_with_items(db_session, project, [
        ("1.001", "Schweißgerät", 1, "Stk"),  # Gleicher Name!
    ])
    sync_offer_to_material(db_session, offer.id)
    db_session.commit()

    # Erwartet: zwei material_items (das manuelle bleibt, das aus Angebot
    # ist NEU). Manuelles soll nicht "gestohlen" werden.
    items = db_session.query(MaterialItem).filter_by(project_id=project.id).all()
    # Das manuelle existiert noch mit kind=werkzeug, offer_item_id=NULL.
    manual_still = next((i for i in items if i.id == manual_id), None)
    assert manual_still is not None
    assert manual_still.kind == "werkzeug"
    assert manual_still.offer_item_id is None


# ---------------------------------------------------------------- 4. Pauschalen-Skip
def test_pauschal_positions_are_skipped(db_session: Session) -> None:
    """Anfahrtskosten / Stunden / Pauschalen werden NICHT zu Material."""
    project = _make_project(db_session, "skip")
    offer = _make_offer_with_items(db_session, project, [
        ("1.001", "Anfahrtskosten", 1, "pauschal"),
        ("1.002", "Monteurstunden", 40, "Std"),
        ("1.003", "Klemme M8", 50, "Stk"),  # Echtes Material
    ])
    stats = sync_offer_to_material(db_session, offer.id)
    db_session.commit()
    assert stats["created"] == 1
    assert stats["skipped"] == 2
    items = db_session.query(MaterialItem).filter_by(project_id=project.id).all()
    assert len(items) == 1
    assert items[0].name == "Klemme M8"


# ---------------------------------------------------------------- 5. Lösch-Resilienz
def test_offer_delete_keeps_material_and_usages(db_session: Session) -> None:
    """Wenn das Angebot gelöscht wird, bleibt das material_item + Verbrauch.
    Nur die Rückreferenz wird NULL."""
    project = _make_project(db_session, "del-offer")
    offer = _make_offer_with_items(db_session, project, [
        ("1.001", "Klemme", 10, "Stk"),
    ])
    sync_offer_to_material(db_session, offer.id)
    db_session.commit()
    mi = db_session.query(MaterialItem).filter_by(project_id=project.id).one()
    db_session.add(MaterialUsage(
        project_id=project.id, material_item_id=mi.id,
        qty_used=3.0, used_at=date.today(),
    ))
    db_session.commit()

    # Offer löschen
    db_session.delete(offer)
    db_session.commit()

    # Material überlebt, Buchung überlebt, offer_item_id ist NULL.
    mi_refresh = db_session.query(MaterialItem).one()
    assert mi_refresh.offer_item_id is None
    usage = db_session.query(MaterialUsage).one()
    assert usage.qty_used == 3.0


def test_material_delete_keeps_usages_as_orphans(db_session: Session) -> None:
    """Wenn ein material_item gelöscht wird, bleiben Buchungen als
    Audit-Spur (material_item_id = NULL)."""
    project = _make_project(db_session, "del-material")
    mi = MaterialItem(project_id=project.id, kind="material", name="X", soll_qty=10.0)
    db_session.add(mi)
    db_session.flush()
    db_session.add(MaterialUsage(
        project_id=project.id, material_item_id=mi.id,
        qty_used=5.0, used_at=date.today(),
    ))
    db_session.commit()

    db_session.delete(mi)
    db_session.commit()

    usage = db_session.query(MaterialUsage).one()
    assert usage.material_item_id is None
    assert usage.qty_used == 5.0


# ---------------------------------------------------------------- 6. Konsistenz-Check
def test_consistency_check_finds_drift(db_session: Session) -> None:
    """Der Konsistenz-Check muss DB-Drift erkennen, falls jemand
    manuell ist_qty gepatcht hat ohne usage-Sync."""
    from app.services.material_usage import find_material_drift

    project = _make_project(db_session, "drift")
    mi = MaterialItem(
        project_id=project.id, kind="material", name="X",
        soll_qty=100.0, ist_qty=0.0,
    )
    db_session.add(mi)
    db_session.flush()
    db_session.add(MaterialUsage(
        project_id=project.id, material_item_id=mi.id,
        qty_used=20.0, used_at=date.today(),
    ))
    db_session.flush()
    recalc_ist_qty(db_session, mi.id)
    db_session.commit()

    # Saboteur setzt ist_qty manuell auf 999
    mi.ist_qty = 999.0
    db_session.commit()

    drifts = find_material_drift(db_session, project.id)
    assert len(drifts) == 1
    assert drifts[0]["material_item_id"] == mi.id
    assert drifts[0]["stored_ist"] == 999.0
    assert drifts[0]["computed_ist"] == 20.0
