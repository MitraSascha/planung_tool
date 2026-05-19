"""Service: Auto-Meilensteine erzeugen, aktualisieren, abfragen.

Drei Typen werden automatisch gepflegt:

- ``section_end``    : pro Bauabschnitt einer, planned_date kommt vom
                       Section-Schedule (oder berechnet aus Plan-Stunden).
                       actual_date wird gesetzt, sobald alle drei
                       Checklisten-Phasen des Abschnitts (vor_beginn /
                       ausfuehrung / abschluss) abgehakt sind.

- ``druckpruefung`` : pro Bauabschnitt einer, getriggert wenn das
                       Feld 'abschluss.pruefprotokoll_erstellt' des
                       Abschnitts gehakt ist.

- ``inbetriebnahme``: einmalig, getriggert wenn alle section_end
                       Meilensteine 'done' sind.

``sync_milestones(project_id)`` ist idempotent und kann nach jedem
relevanten Event aufgerufen werden (Section-Update, Checklisten-Klick,
Daily-Report-Submit).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session, selectinload

from app.db.orm_models import (
    FormResponse,
    Milestone,
    Project,
    ProjectSection,
    SectionSchedule,
)


CHECKLIST_PHASE_FIELDS = {
    "vor_beginn": [
        "material_vollstaendig",
        "arbeitsbereiche_frei",
        "werkzeuge_funktional",
    ],
    "ausfuehrung": [
        "verbindungsstellen_geprueft",
        "leitungsverlegung_geprueft",
        "daemmung_geprueft",
        "pruefoeffnungen_vorbereitet",
    ],
    "abschluss": [
        "pruefprotokoll_erstellt",
        "sichtkontrolle_abgeschlossen",
        "baustelle_sauber",
    ],
}


def _checklist_field_value(
    db: Session, project_id: int, field_id: str
) -> bool:
    """Liefert True wenn mindestens ein User die Checkbox abgehakt hat."""
    rows = (
        db.query(FormResponse)
        .filter(
            FormResponse.project_id == project_id,
            FormResponse.field_id == field_id,
        )
        .all()
    )
    for r in rows:
        # FormResponse hat value_bool/value_text/value_number — wir suchen
        # nach value_bool=True ODER (für Sicherheits-Fallback) value_text='on'/'true'
        if getattr(r, "value_bool", None) is True:
            return True
        v = (getattr(r, "value_text", None) or "").strip().lower()
        if v in {"on", "true", "1", "ja"}:
            return True
    return False


def _section_checklist_done(
    db: Session, project_id: int, section_number: int
) -> bool:
    """Alle 10 Checkboxen eines Abschnitts gehakt?"""
    for phase, fields in CHECKLIST_PHASE_FIELDS.items():
        for f in fields:
            field_id = f"checkliste.s{section_number}.{phase}.{f}"
            if not _checklist_field_value(db, project_id, field_id):
                return False
    return True


def _druckpruefung_done(
    db: Session, project_id: int, section_number: int
) -> bool:
    field_id = f"checkliste.s{section_number}.abschluss.pruefprotokoll_erstellt"
    return _checklist_field_value(db, project_id, field_id)


def _upsert(
    db: Session,
    *,
    project_id: int,
    type_: str,
    section_id: int | None,
    title: str,
    description: str | None,
    planned_date: date | None,
    actual_date: date | None,
    auto_generated: bool = True,
) -> Milestone:
    """Insert or update — Key (project_id, type, section_id)."""
    q = db.query(Milestone).filter(
        Milestone.project_id == project_id, Milestone.type == type_
    )
    if section_id is None:
        q = q.filter(Milestone.section_id.is_(None))
    else:
        q = q.filter(Milestone.section_id == section_id)
    row = q.one_or_none()
    if row is None:
        row = Milestone(
            project_id=project_id,
            type=type_,
            section_id=section_id,
            auto_generated=auto_generated,
        )
        db.add(row)
    row.title = title
    row.description = description
    row.planned_date = planned_date
    row.actual_date = actual_date
    row.status = "done" if actual_date else "pending"
    # Overdue-Berechnung wird beim Lesen gemacht (date.today wäre hier flüchtig).
    return row


def sync_milestones(db: Session, project_id: int) -> dict:
    """Alle automatisch ableitbaren Meilensteine pflegen.
    Returns Stats: ``{section_end, druckpruefung, inbetriebnahme}``.
    """
    project = (
        db.query(Project)
        .options(selectinload(Project.sections))
        .filter(Project.id == project_id)
        .one_or_none()
    )
    if project is None:
        return {"error": "project_not_found"}

    sections = sorted(project.sections, key=lambda s: s.number)
    schedule_overrides = {
        r.section_id: r
        for r in db.query(SectionSchedule)
        .join(ProjectSection, SectionSchedule.section_id == ProjectSection.id)
        .filter(ProjectSection.project_id == project_id)
        .all()
    }

    section_end_count = 0
    druck_count = 0

    for s in sections:
        # Geplantes Ende: Schedule-Override hat Vorrang vor Projekt-Default.
        ov = schedule_overrides.get(s.id)
        planned_end = ov.end_date if ov and ov.end_date else None
        # Wenn kein Schedule: fall back auf project.planned_end (grob).
        if planned_end is None:
            planned_end = project.planned_end

        # section_end: actual_date = heute wenn alle Checklisten abgehakt.
        all_done = _section_checklist_done(db, project_id, s.number)
        section_actual = date.today() if all_done else None
        _upsert(
            db,
            project_id=project_id,
            type_="section_end",
            section_id=s.id,
            title=f"Abschnitt {s.number} – {s.name} abgeschlossen",
            description=s.goal,
            planned_date=planned_end,
            actual_date=section_actual,
        )
        section_end_count += 1

        # druckpruefung: actual = heute wenn pruefprotokoll_erstellt gehakt.
        druck_done = _druckpruefung_done(db, project_id, s.number)
        druck_actual = date.today() if druck_done else None
        _upsert(
            db,
            project_id=project_id,
            type_="druckpruefung",
            section_id=s.id,
            title=f"Druckprüfung – Abschnitt {s.number} ({s.name})",
            description="Belastungs-/Druckprüfung mit Protokoll",
            planned_date=planned_end,
            actual_date=druck_actual,
        )
        druck_count += 1

    # inbetriebnahme: actual = heute wenn alle section_end done sind.
    all_section_ends_done = (
        sections
        and all(
            _section_checklist_done(db, project_id, s.number) for s in sections
        )
    )
    inb_actual = date.today() if all_section_ends_done else None
    _upsert(
        db,
        project_id=project_id,
        type_="inbetriebnahme",
        section_id=None,
        title="Inbetriebnahme & Projektabschluss",
        description="Anlage in Betrieb, Übergabe an Bauherr",
        planned_date=project.planned_end,
        actual_date=inb_actual,
    )

    db.commit()
    return {
        "section_end": section_end_count,
        "druckpruefung": druck_count,
        "inbetriebnahme": 1,
    }


def list_milestones_for_render(db: Session, project_id: int) -> list[dict]:
    """Liefere die Meilensteine in Render-fertigem Format.
    Reihenfolge: nach planned_date (None ans Ende), 'overdue' wird live
    berechnet.
    """
    rows = (
        db.query(Milestone)
        .filter(Milestone.project_id == project_id)
        .order_by(Milestone.planned_date.is_(None), Milestone.planned_date)
        .all()
    )
    today = date.today()
    out = []
    for m in rows:
        status = m.status
        if status == "pending" and m.planned_date and m.planned_date < today:
            status = "overdue"
        out.append(
            {
                "id": m.id,
                "type": m.type,
                "title": m.title,
                "description": m.description,
                "planned_date": m.planned_date,
                "actual_date": m.actual_date,
                "status": status,
                "section_id": m.section_id,
            }
        )
    return out
