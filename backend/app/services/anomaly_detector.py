"""Lightweight, rule-based anomaly detection over the reports schema.

Three heuristics, all purely local (no LLM, no network):

- ``consecutive_red``      — >= 3 DailyReports with status="red" in the last 14 days.
- ``recurring_material``   — >= 3 MaterialIssues with the same (normalised)
                             description text in the last 30 days.
- ``stale_blocker``        — Blocker with status="open" AND created_at older
                             than 7 days.

Designed for cheap polling: the function reads from the DB once per call
and returns a flat list of ``Anomaly`` objects ready for serialisation.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.orm_models import Blocker, DailyReport, MaterialIssue, Project


@dataclass
class Anomaly:
    project_slug: str
    kind: str   # "consecutive_red" | "recurring_material" | "stale_blocker"
    severity: str  # "info" | "warning" | "critical"
    title: str
    detail: str
    related_ids: list[int] = field(default_factory=list)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_WHITESPACE_RE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Lowercase + collapse whitespace + strip."""
    return _WHITESPACE_RE.sub(" ", text.lower()).strip()


def _ensure_aware(value: datetime) -> datetime:
    """SQLite drops timezones on stored DateTime values; normalise to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _detect_consecutive_red(
    db: Session, project: Project, *, now: datetime
) -> Anomaly | None:
    window_start = (now - timedelta(days=14)).date()
    reports: list[DailyReport] = (
        db.query(DailyReport)
        .filter(
            DailyReport.project_id == project.id,
            DailyReport.status == "red",
            DailyReport.report_date >= window_start,
        )
        .order_by(DailyReport.report_date.desc())
        .all()
    )
    if len(reports) < 3:
        return None

    dates = ", ".join(r.report_date.isoformat() for r in reports[:5])
    return Anomaly(
        project_slug=project.slug,
        kind="consecutive_red",
        severity="critical",
        title=f"{len(reports)} rote Tagesberichte in den letzten 14 Tagen",
        detail=(
            f"In den letzten 14 Tagen wurden {len(reports)} Tagesberichte mit "
            f"Status 'rot' erfasst (Datum: {dates}). Bitte pruefen, ob die "
            "Ursachen adressiert sind."
        ),
        related_ids=[r.id for r in reports],
    )


def _detect_recurring_material(
    db: Session, project: Project, *, now: datetime
) -> list[Anomaly]:
    window_start = now - timedelta(days=30)
    issues: list[MaterialIssue] = (
        db.query(MaterialIssue)
        .filter(
            MaterialIssue.project_id == project.id,
            MaterialIssue.created_at >= window_start,
        )
        .order_by(MaterialIssue.created_at.asc())
        .all()
    )

    buckets: dict[str, list[MaterialIssue]] = defaultdict(list)
    for issue in issues:
        key = _normalise(issue.description or "")
        if not key:
            continue
        buckets[key].append(issue)

    anomalies: list[Anomaly] = []
    for normalised, group in buckets.items():
        if len(group) < 3:
            continue
        original = group[0].description or normalised
        snippet = original.strip()
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        anomalies.append(
            Anomaly(
                project_slug=project.slug,
                kind="recurring_material",
                severity="warning",
                title=f"Wiederkehrendes Material-Problem ({len(group)}x)",
                detail=(
                    f"In den letzten 30 Tagen wurde {len(group)}-mal das gleiche "
                    f"Material-Problem gemeldet: '{snippet}'. Strukturelle "
                    "Ursache prüfen."
                ),
                related_ids=[issue.id for issue in group],
            )
        )
    return anomalies


def _detect_stale_blockers(
    db: Session, project: Project, *, now: datetime
) -> list[Anomaly]:
    cutoff = now - timedelta(days=7)
    blockers: list[Blocker] = (
        db.query(Blocker)
        .filter(
            Blocker.project_id == project.id,
            Blocker.status == "open",
        )
        .all()
    )

    anomalies: list[Anomaly] = []
    for blocker in blockers:
        created = _ensure_aware(blocker.created_at)
        if created >= cutoff:
            continue
        age_days = (now - created).days
        snippet = (blocker.description or "").strip()
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        severity = "critical" if blocker.severity in {"high", "critical"} else "warning"
        anomalies.append(
            Anomaly(
                project_slug=project.slug,
                kind="stale_blocker",
                severity=severity,
                title=f"Offener Blocker seit {age_days} Tagen",
                detail=(
                    f"Blocker '{snippet}' ist seit {age_days} Tagen offen "
                    f"(Schweregrad: {blocker.severity})."
                ),
                related_ids=[blocker.id],
            )
        )
    return anomalies


def detect_project_anomalies(
    db: Session,
    project: Project,
    *,
    now: datetime | None = None,
) -> list[Anomaly]:
    """Run all heuristics for one project, return their findings."""
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    anomalies: list[Anomaly] = []

    consecutive = _detect_consecutive_red(db, project, now=current)
    if consecutive is not None:
        anomalies.append(consecutive)

    anomalies.extend(_detect_recurring_material(db, project, now=current))
    anomalies.extend(_detect_stale_blockers(db, project, now=current))

    return anomalies
