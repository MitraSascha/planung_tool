"""HERO-Tracking-Time-Push beim DailyReport-Save.

Pro Attendee mit gesetztem ``hero_partner_id`` wird **eine** Tracking-Time
im HERO angelegt — bei Edit-Aufrufen wird die existierende HERO-Zeile
aktualisiert (Idempotenz via :class:`DailyReportHeroPush`).

Heuristik für Start/End:
  * Default-Start: 07:00 Berlin-Zeit am ``report_date``
  * End: Start + ``ist_hours`` (pro Attendee voll, nicht aufgeteilt — Chef-
    Entscheidung 2026-05-19: jeder Mann bucht seine eigene 8h-Schicht).
  * Falls ``ist_hours`` fehlt: 8.0 als Fallback.

Wird in einem Hintergrund-Thread vom DailyReport-Create/Update-Handler
aufgerufen (Best-Effort) — HERO-Failures blockieren das lokale Speichern
nicht. Fehler landen in ``DailyReportHeroPush.last_error``.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, time, timedelta, timezone as dt_tz
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db import database as _database
from app.db.orm_models import (
    DailyReport,
    DailyReportAttendee,
    DailyReportHeroPush,
    Project,
    User,
)

from .client import HeroError, is_configured
from .service import get_tracking_time_categories, push_tracking_time

logger = logging.getLogger(__name__)

BERLIN_TZ = ZoneInfo("Europe/Berlin")
DEFAULT_START_TIME = time(hour=7, minute=0)
DEFAULT_HOURS = 8.0

# Cache für die Default-Kategorie (erste mit is_working_time=true). Wird beim
# ersten Push gelookuped und dann gehalten — HERO ändert seine Stamm-Kategorien
# nicht mehrmals pro Tag.
_default_category_cache: int | None = None


def _default_working_category_id() -> int | None:
    """Hole (mit Cache) die erste Kategorie mit ``is_working_time=true``."""
    global _default_category_cache
    if _default_category_cache is not None:
        return _default_category_cache
    try:
        rows = get_tracking_time_categories()
    except HeroError as exc:
        logger.warning("HERO: tracking_times_categories konnte nicht geladen werden: %s", exc)
        return None
    for r in rows:
        if r.get("is_working_time") and r.get("id") is not None:
            _default_category_cache = int(r["id"])
            logger.info(
                "HERO Default-Tracking-Kategorie gewählt: id=%s name=%r",
                _default_category_cache, r.get("name"),
            )
            return _default_category_cache
    logger.warning("HERO: keine Kategorie mit is_working_time=true gefunden")
    return None


def _start_end_for(report: DailyReport, hours: float) -> tuple[str, str]:
    """Konstruiert ISO-Strings für start/end in Berlin-Zeit."""
    start_local = datetime.combine(report.report_date, DEFAULT_START_TIME, tzinfo=BERLIN_TZ)
    end_local = start_local + timedelta(hours=hours)
    return start_local.isoformat(), end_local.isoformat()


def _comment_for(report: DailyReport, project: Project) -> str:
    """Kurzer Kommentar pro HERO-Eintrag — hilft beim Identifizieren im CRM."""
    parts = [f"Tagesbericht #{report.id}"]
    if project.slug:
        parts.append(project.slug)
    if report.section_number:
        parts.append(f"Abschnitt {report.section_number}")
    if report.completed_work:
        snippet = report.completed_work.strip().split("\n")[0][:80]
        if snippet:
            parts.append(snippet)
    return " · ".join(parts)


def _push_for_attendee(
    db: Session,
    *,
    report: DailyReport,
    project: Project,
    attendee_user: User,
    hours: float,
    category_id: int | None,
) -> None:
    """Push für einen einzelnen Attendee. Idempotent via DailyReportHeroPush."""
    push_row = (
        db.query(DailyReportHeroPush)
        .filter_by(daily_report_id=report.id, user_id=attendee_user.id)
        .one_or_none()
    )
    if push_row is None:
        push_row = DailyReportHeroPush(
            daily_report_id=report.id, user_id=attendee_user.id
        )
        db.add(push_row)
        db.flush()

    push_row.last_attempt_at = datetime.now(tz=dt_tz.utc)

    if attendee_user.hero_partner_id is None:
        push_row.last_error = "hero_partner_id leer — User noch nicht gemappt"
        db.commit()
        return

    start_iso, end_iso = _start_end_for(report, hours)
    try:
        resp = push_tracking_time(
            partner_id=attendee_user.hero_partner_id,
            project_match_id=project.hero_project_match_id,
            start_iso=start_iso,
            end_iso=end_iso,
            category_id=category_id,
            comment=_comment_for(report, project),
            existing_id=push_row.hero_tracking_time_id,
        )
    except HeroError as exc:
        logger.warning(
            "HERO-Push fehlgeschlagen (report=%s user=%s): %s",
            report.id, attendee_user.id, exc,
        )
        push_row.last_error = str(exc)[:1000]
        db.commit()
        return

    new_id = resp.get("id")
    if new_id is not None:
        push_row.hero_tracking_time_id = int(new_id)
    new_uuid = resp.get("uuid")
    if new_uuid:
        push_row.hero_tracking_time_uuid = str(new_uuid)[:64]
    push_row.pushed_at = datetime.now(tz=dt_tz.utc)
    push_row.last_error = None
    db.commit()
    logger.info(
        "HERO-Push OK: report=%s user=%s → tracking_time_id=%s",
        report.id, attendee_user.id, push_row.hero_tracking_time_id,
    )


def dry_run_daily_report(report_id: int) -> list[dict]:
    """Wie :func:`push_daily_report`, aber **kein** HERO-Call — nur Compute
    der Payloads. Liefert was beim Live-Push gesendet würde, für jeden
    Attendee einen Eintrag. Damit kann der Admin verifizieren, ob das
    Mapping (partner_id, project_match_id, Start/End, Kategorie, Kommentar)
    korrekt ist, bevor er den Echt-Push freigibt.
    """
    if not is_configured():
        return [{"error": "hero_api_token nicht konfiguriert"}]
    category_id = _default_working_category_id()
    payloads: list[dict] = []
    with _database.SessionLocal() as db:
        report = db.query(DailyReport).filter(DailyReport.id == report_id).one_or_none()
        if report is None:
            return [{"error": f"DailyReport {report_id} nicht gefunden"}]
        project = db.query(Project).filter(Project.id == report.project_id).one()
        attendees = (
            db.query(DailyReportAttendee, User)
            .join(User, DailyReportAttendee.user_id == User.id)
            .filter(DailyReportAttendee.daily_report_id == report.id)
            .all()
        )
        hours = float(report.ist_hours) if report.ist_hours is not None else DEFAULT_HOURS
        start_iso, end_iso = _start_end_for(report, hours)
        for _, user in attendees:
            existing = (
                db.query(DailyReportHeroPush)
                .filter_by(daily_report_id=report.id, user_id=user.id)
                .one_or_none()
            )
            payloads.append({
                "user_id": user.id,
                "user_display_name": user.display_name,
                "hero_partner_id": user.hero_partner_id,
                "project_match_id": project.hero_project_match_id,
                "start": start_iso,
                "end": end_iso,
                "hours": hours,
                "category_id": category_id,
                "comment": _comment_for(report, project),
                "would_update_existing_id": existing.hero_tracking_time_id if existing else None,
                "ready": user.hero_partner_id is not None,
            })
    return payloads


def push_daily_report(report_id: int) -> dict[str, int]:
    """Synchron-Variante (für Tests/Manuell): für alle Attendees pushen.

    Returns: Counter ``{pushed, skipped, errors}``.
    """
    counters = {"pushed": 0, "skipped": 0, "errors": 0}
    if not is_configured():
        logger.info("HERO-Push übersprungen: nicht konfiguriert")
        return counters
    category_id = _default_working_category_id()
    with _database.SessionLocal() as db:
        report = db.query(DailyReport).filter(DailyReport.id == report_id).one_or_none()
        if report is None:
            return counters
        project = db.query(Project).filter(Project.id == report.project_id).one()
        attendees = (
            db.query(DailyReportAttendee, User)
            .join(User, DailyReportAttendee.user_id == User.id)
            .filter(DailyReportAttendee.daily_report_id == report.id)
            .all()
        )
        hours = float(report.ist_hours) if report.ist_hours is not None else DEFAULT_HOURS
        for _, user in attendees:
            if user.hero_partner_id is None:
                counters["skipped"] += 1
                continue
            try:
                _push_for_attendee(
                    db,
                    report=report,
                    project=project,
                    attendee_user=user,
                    hours=hours,
                    category_id=category_id,
                )
                counters["pushed"] += 1
            except Exception as exc:  # noqa: BLE001 — best-effort
                logger.exception("HERO-Push unerwarteter Fehler: %s", exc)
                counters["errors"] += 1
    return counters


def push_daily_report_async(report_id: int) -> None:
    """Spawnt einen Daemon-Thread für den Push, damit das HTTP-Response
    nicht warten muss. Analoge Logik wie ``whisper_pipeline``."""
    if not is_configured():
        return
    threading.Thread(
        target=_push_in_background,
        args=(report_id,),
        name=f"hero-push-{report_id}",
        daemon=True,
    ).start()


def _push_in_background(report_id: int) -> None:
    try:
        push_daily_report(report_id)
    except Exception:  # noqa: BLE001 — Thread darf nie crashen
        logger.exception("HERO-Push-Worker abgestürzt für report %s", report_id)
