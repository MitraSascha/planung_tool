"""Title/Body-Generatoren fuer Push-Benachrichtigungen (Phase 14.4)."""
from __future__ import annotations

from app.db.orm_models import Blocker, DailyReport, Project


_DEFAULT_BODY_LIMIT = 140


def _trim(text: str | None, limit: int = _DEFAULT_BODY_LIMIT) -> str:
    if not text:
        return ""
    cleaned = text.strip().replace("\n", " ")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def blocker_message(blocker: Blocker, project: Project) -> tuple[str, str]:
    """Title/Body fuer einen neuen Blocker."""
    severity_label = {
        "low": "niedrig",
        "medium": "mittel",
        "high": "hoch",
        "critical": "kritisch",
    }.get(blocker.severity, blocker.severity)
    title = f"Blocker ({severity_label}): {project.name}"
    body = _trim(blocker.description) or "Neuer Blocker eingetragen."
    return title, body


def daily_report_red_message(report: DailyReport, project: Project) -> tuple[str, str]:
    """Title/Body fuer einen Tagesbericht mit Status 'red'."""
    title = f"Tagesbericht ROT: {project.name}"
    parts: list[str] = []
    if report.blockers:
        parts.append(f"Blocker: {_trim(report.blockers, 80)}")
    if report.material_missing:
        parts.append(f"Material: {_trim(report.material_missing, 80)}")
    if report.notes:
        parts.append(_trim(report.notes, 80))
    body = " | ".join(parts) or "Status 'rot' gemeldet."
    return title, _trim(body)


def repeated_red_message(project: Project, count: int) -> tuple[str, str]:
    """Title/Body, wenn mehrere rote Tagesberichte in Folge auftreten."""
    title = f"Haeufung roter Tagesberichte: {project.name}"
    body = f"{count} rote Tagesberichte innerhalb der letzten 7 Tage."
    return title, body
