"""Tests for ``app.services.anomaly_detector.detect_project_anomalies``."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.orm_models import Blocker, DailyReport, MaterialIssue, Project, User
from app.services.anomaly_detector import detect_project_anomalies
from app.services.auth import hash_password


_NOW = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)


def _make_user(db: Session, username: str = "alice") -> User:
    user = User(
        username=username,
        display_name=username.title(),
        password_hash=hash_password("pw"),
        global_role="monteur",
    )
    db.add(user)
    db.flush()
    return user


def _make_project(db: Session, slug: str = "proj") -> Project:
    project = Project(slug=slug, name=f"Projekt {slug}")
    db.add(project)
    db.flush()
    return project


def _add_daily_red(
    db: Session, project: Project, user: User, *, day: date
) -> DailyReport:
    report = DailyReport(
        project_id=project.id,
        user_id=user.id,
        report_date=day,
        status="red",
    )
    db.add(report)
    db.flush()
    return report


def test_consecutive_red_detected_with_three_reports_in_14_days(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    today = _NOW.date()
    _add_daily_red(db_session, project, user, day=today)
    _add_daily_red(db_session, project, user, day=today - timedelta(days=2))
    _add_daily_red(db_session, project, user, day=today - timedelta(days=5))
    db_session.commit()

    anomalies = detect_project_anomalies(db_session, project, now=_NOW)
    kinds = [a.kind for a in anomalies]
    assert "consecutive_red" in kinds
    red_anomaly = next(a for a in anomalies if a.kind == "consecutive_red")
    assert red_anomaly.severity == "critical"
    assert len(red_anomaly.related_ids) == 3


def test_consecutive_red_not_detected_with_only_two_reports(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    today = _NOW.date()
    _add_daily_red(db_session, project, user, day=today)
    _add_daily_red(db_session, project, user, day=today - timedelta(days=3))
    db_session.commit()

    anomalies = detect_project_anomalies(db_session, project, now=_NOW)
    assert all(a.kind != "consecutive_red" for a in anomalies)


def test_consecutive_red_ignores_reports_older_than_14_days(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    today = _NOW.date()
    _add_daily_red(db_session, project, user, day=today)
    _add_daily_red(db_session, project, user, day=today - timedelta(days=20))
    _add_daily_red(db_session, project, user, day=today - timedelta(days=25))
    db_session.commit()

    anomalies = detect_project_anomalies(db_session, project, now=_NOW)
    assert all(a.kind != "consecutive_red" for a in anomalies)


def test_recurring_material_detected_for_three_same_descriptions(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    for text in (
        "Pumpe Grundfos UPS 25-60 fehlt",
        "  pumpe grundfos UPS 25-60 fehlt  ",
        "Pumpe Grundfos UPS 25-60   fehlt",
    ):
        db_session.add(
            MaterialIssue(
                project_id=project.id,
                user_id=user.id,
                description=text,
            )
        )
    db_session.commit()

    anomalies = detect_project_anomalies(db_session, project, now=_NOW)
    recurring = [a for a in anomalies if a.kind == "recurring_material"]
    assert len(recurring) == 1
    assert recurring[0].severity == "warning"
    assert len(recurring[0].related_ids) == 3


def test_recurring_material_not_detected_for_only_two_matches(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    for text in ("Pumpe fehlt", "Pumpe fehlt"):
        db_session.add(
            MaterialIssue(
                project_id=project.id, user_id=user.id, description=text
            )
        )
    db_session.commit()

    anomalies = detect_project_anomalies(db_session, project, now=_NOW)
    assert all(a.kind != "recurring_material" for a in anomalies)


def test_stale_blocker_detected_when_older_than_seven_days(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    blocker = Blocker(
        project_id=project.id,
        user_id=user.id,
        description="Genehmigung steht aus",
        severity="high",
        status="open",
    )
    db_session.add(blocker)
    db_session.flush()
    # Backdate the created_at past the 7-day threshold.
    blocker.created_at = _NOW - timedelta(days=10)
    db_session.commit()

    anomalies = detect_project_anomalies(db_session, project, now=_NOW)
    stale = [a for a in anomalies if a.kind == "stale_blocker"]
    assert len(stale) == 1
    assert stale[0].related_ids == [blocker.id]
    assert stale[0].severity == "critical"  # high severity escalates


def test_stale_blocker_not_detected_for_recent_blocker(db_session: Session) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    blocker = Blocker(
        project_id=project.id,
        user_id=user.id,
        description="Neu",
        severity="medium",
        status="open",
    )
    db_session.add(blocker)
    db_session.flush()
    blocker.created_at = _NOW - timedelta(days=2)
    db_session.commit()

    anomalies = detect_project_anomalies(db_session, project, now=_NOW)
    assert all(a.kind != "stale_blocker" for a in anomalies)


def test_stale_blocker_ignores_closed_blockers(db_session: Session) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    blocker = Blocker(
        project_id=project.id,
        user_id=user.id,
        description="Erledigt",
        severity="medium",
        status="done",
    )
    db_session.add(blocker)
    db_session.flush()
    blocker.created_at = _NOW - timedelta(days=30)
    db_session.commit()

    anomalies = detect_project_anomalies(db_session, project, now=_NOW)
    assert all(a.kind != "stale_blocker" for a in anomalies)
