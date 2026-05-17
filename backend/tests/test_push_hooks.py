"""Tests fuer die SQLAlchemy-Event-Listener in ``app.services.push_hooks``."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from app.db import database as database_module
from app.db.orm_models import (
    Blocker,
    DailyReport,
    Project,
    ProjectMember,
    PushSubscription,
    User,
)
from app.services import push_hooks, push_service


@pytest.fixture()
def world(db_engine, db_session):
    """Projekt + Bauleiter + globaler Admin + Subscriptions."""
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    original = database_module.SessionLocal
    database_module.SessionLocal = factory
    try:
        project = Project(slug="alpha", name="Alpha")
        admin = User(
            username="admin",
            display_name="Admin",
            password_hash="x",
            global_role="admin",
        )
        bauleiter = User(
            username="bauleiter",
            display_name="Bauleiter",
            password_hash="x",
            global_role="bauleitung",
        )
        monteur = User(
            username="monteur",
            display_name="Monteur",
            password_hash="x",
            global_role="monteur",
        )
        db_session.add_all([project, admin, bauleiter, monteur])
        db_session.flush()

        db_session.add(
            ProjectMember(
                project_id=project.id,
                user_id=bauleiter.id,
                project_role="bauleitung",
            )
        )
        db_session.add(
            ProjectMember(
                project_id=project.id,
                user_id=monteur.id,
                project_role="monteur",
            )
        )

        for user in (admin, bauleiter, monteur):
            db_session.add(
                PushSubscription(
                    user_id=user.id,
                    endpoint=f"https://push.example/{user.username}",
                    p256dh_key="p",
                    auth_key="a",
                    user_agent="UA",
                    active=True,
                )
            )
        db_session.commit()
        yield {
            "project": project,
            "admin": admin,
            "bauleiter": bauleiter,
            "monteur": monteur,
        }
    finally:
        database_module.SessionLocal = original


def _enable_push(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import settings

    monkeypatch.setattr(settings, "vapid_public_key", "pub", raising=False)
    monkeypatch.setattr(settings, "vapid_private_key", "priv", raising=False)
    monkeypatch.setattr(settings, "disable_push_hook", False, raising=False)


def test_collect_lead_user_ids_includes_admins_and_bauleiter(world, db_session) -> None:
    user_ids = push_hooks._collect_lead_user_ids(db_session, world["project"].id)
    assert world["admin"].id in user_ids
    assert world["bauleiter"].id in user_ids
    assert world["monteur"].id not in user_ids


def test_handle_blocker_async_invokes_push_for_high_severity(
    world, monkeypatch: pytest.MonkeyPatch, db_session
) -> None:
    _enable_push(monkeypatch)

    calls: list[dict] = []

    def fake_send(db, user_ids, title, body, **kwargs):
        calls.append({
            "user_ids": list(user_ids),
            "title": title,
            "body": body,
            "kwargs": kwargs,
        })
        return {"sent": len(user_ids), "failed": 0, "expired": 0, "enabled": 1}

    monkeypatch.setattr(push_service, "send_push_notification", fake_send)

    blocker = Blocker(
        project_id=world["project"].id,
        user_id=world["bauleiter"].id,
        description="Stromversorgung fehlt",
        severity="high",
    )
    db_session.add(blocker)
    db_session.commit()

    push_hooks._handle_blocker_async(blocker.id)
    assert len(calls) == 1
    assert "Stromversorgung fehlt" in calls[0]["body"]
    assert world["admin"].id in calls[0]["user_ids"]
    assert world["bauleiter"].id in calls[0]["user_ids"]
    assert world["monteur"].id not in calls[0]["user_ids"]


def test_handle_blocker_async_skips_low_severity(
    world, monkeypatch: pytest.MonkeyPatch, db_session
) -> None:
    _enable_push(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(
        push_service,
        "send_push_notification",
        lambda *a, **kw: (calls.append({"a": a, "kw": kw}) or {"sent": 0, "failed": 0, "expired": 0, "enabled": 1}),
    )

    blocker = Blocker(
        project_id=world["project"].id,
        user_id=world["bauleiter"].id,
        description="Kleinigkeit",
        severity="medium",
    )
    db_session.add(blocker)
    db_session.commit()

    push_hooks._handle_blocker_async(blocker.id)
    assert calls == []


def test_handle_daily_report_async_triggers_for_red(
    world, monkeypatch: pytest.MonkeyPatch, db_session
) -> None:
    _enable_push(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(
        push_service,
        "send_push_notification",
        lambda db, user_ids, title, body, **kw: (
            calls.append({"title": title, "body": body, "kw": kw})
            or {"sent": len(user_ids), "failed": 0, "expired": 0, "enabled": 1}
        ),
    )

    report = DailyReport(
        project_id=world["project"].id,
        user_id=world["bauleiter"].id,
        report_date=date.today(),
        status="red",
        blockers="Stromausfall",
        notes="Baustelle steht",
    )
    db_session.add(report)
    db_session.commit()

    push_hooks._handle_daily_report_async(report.id)
    # Mind. ein Push fuer den roten Tagesbericht; wir akzeptieren auch
    # einen zusaetzlichen "Haeufungs"-Push, wenn die DB-Daten das hergeben.
    assert len(calls) >= 1
    assert "ROT" in calls[0]["title"]


def test_handle_daily_report_async_skips_green(
    world, monkeypatch: pytest.MonkeyPatch, db_session
) -> None:
    _enable_push(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(
        push_service,
        "send_push_notification",
        lambda *a, **kw: (calls.append(1) or {"sent": 0, "failed": 0, "expired": 0, "enabled": 1}),
    )

    report = DailyReport(
        project_id=world["project"].id,
        user_id=world["bauleiter"].id,
        report_date=date.today(),
        status="green",
    )
    db_session.add(report)
    db_session.commit()

    push_hooks._handle_daily_report_async(report.id)
    assert calls == []


def test_handle_daily_report_async_emits_cluster_push(
    world, monkeypatch: pytest.MonkeyPatch, db_session
) -> None:
    """Drei oder mehr rote Reports → zwei Pushes (Einzel + Haeufung)."""
    _enable_push(monkeypatch)

    titles: list[str] = []

    def fake_send(db, user_ids, title, body, **kwargs):
        titles.append(title)
        return {"sent": len(user_ids), "failed": 0, "expired": 0, "enabled": 1}

    monkeypatch.setattr(push_service, "send_push_notification", fake_send)

    for i in range(3):
        db_session.add(
            DailyReport(
                project_id=world["project"].id,
                user_id=world["bauleiter"].id,
                report_date=date.today(),
                status="red",
                notes=f"Lage {i}",
            )
        )
    db_session.commit()
    last = (
        db_session.query(DailyReport)
        .filter(DailyReport.project_id == world["project"].id)
        .order_by(DailyReport.id.desc())
        .first()
    )

    push_hooks._handle_daily_report_async(last.id)
    assert any("ROT" in t for t in titles)
    assert any("Haeufung" in t for t in titles)


def test_register_listeners_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import settings as live_settings
    from sqlalchemy import event

    push_hooks.unregister_listeners()
    monkeypatch.setattr(live_settings, "disable_push_hook", True, raising=False)

    push_hooks.register_listeners()
    assert not event.contains(Blocker, "after_insert", push_hooks._blocker_after_insert)
    assert not event.contains(
        DailyReport, "after_insert", push_hooks._daily_report_after_insert
    )
    push_hooks.unregister_listeners()


def test_register_listeners_attaches_hooks_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.settings import settings as live_settings
    from sqlalchemy import event

    push_hooks.unregister_listeners()
    monkeypatch.setattr(live_settings, "disable_push_hook", False, raising=False)
    push_hooks.register_listeners()
    try:
        assert event.contains(Blocker, "after_insert", push_hooks._blocker_after_insert)
        assert event.contains(
            DailyReport, "after_insert", push_hooks._daily_report_after_insert
        )
    finally:
        push_hooks.unregister_listeners()
