"""Tests fuer ``app.services.push_service.send_push_notification``.

Der eigentliche ``pywebpush.webpush``-Aufruf wird gemockt, damit die
Test-Suite ohne externe Push-Services laeuft.
"""
from __future__ import annotations

import pytest

from app.db.orm_models import PushSubscription, User
from app.services import push_service


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeWebPushException(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.response = _FakeResponse(status_code) if status_code is not None else None


@pytest.fixture()
def user_with_subs(db_session):
    user = User(
        username="bauleiter",
        display_name="Bauleiter Test",
        password_hash="x",
        global_role="bauleitung",
    )
    db_session.add(user)
    db_session.flush()

    sub_a = PushSubscription(
        user_id=user.id,
        endpoint="https://push.example/sub-a",
        p256dh_key="p256dh-a",
        auth_key="auth-a",
        user_agent="ChromeTest",
        active=True,
    )
    sub_b = PushSubscription(
        user_id=user.id,
        endpoint="https://push.example/sub-b",
        p256dh_key="p256dh-b",
        auth_key="auth-b",
        user_agent="FirefoxTest",
        active=True,
    )
    db_session.add_all([sub_a, sub_b])
    db_session.commit()
    return user, [sub_a, sub_b]


def _enable_push(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import settings

    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key", raising=False)
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key", raising=False)
    monkeypatch.setattr(settings, "vapid_subject", "mailto:test@example.com", raising=False)


def test_send_push_noop_without_vapid_keys(
    db_session, user_with_subs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ohne konfigurierte Keys gibt es keine Sends, ``enabled=0``."""
    from app.core.settings import settings

    monkeypatch.setattr(settings, "vapid_public_key", None, raising=False)
    monkeypatch.setattr(settings, "vapid_private_key", None, raising=False)
    user, _ = user_with_subs

    calls: list[dict] = []

    def fake_webpush(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(push_service, "_webpush_callable", lambda: fake_webpush)

    stats = push_service.send_push_notification(
        db_session, [user.id], "Hi", "Body"
    )
    assert stats == {"sent": 0, "failed": 0, "expired": 0, "enabled": 0}
    assert calls == []


def test_send_push_to_all_active_subs(
    db_session, user_with_subs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_push(monkeypatch)
    user, subs = user_with_subs

    calls: list[dict] = []

    def fake_webpush(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(push_service, "_webpush_callable", lambda: fake_webpush)
    monkeypatch.setattr(push_service, "_webpush_exception_cls", lambda: _FakeWebPushException)

    stats = push_service.send_push_notification(
        db_session, [user.id], "Titel", "Body-Text", url="/projects/foo"
    )
    assert stats["sent"] == 2
    assert stats["failed"] == 0
    assert stats["expired"] == 0
    assert stats["enabled"] == 1
    assert len(calls) == 2
    endpoints = sorted(c["subscription_info"]["endpoint"] for c in calls)
    assert endpoints == sorted(sub.endpoint for sub in subs)

    for sub in subs:
        db_session.refresh(sub)
        assert sub.last_used_at is not None


def test_send_push_marks_expired_on_410(
    db_session, user_with_subs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_push(monkeypatch)
    user, subs = user_with_subs

    def fake_webpush(**kwargs):
        # erste Sub: ok, zweite Sub: 410
        if kwargs["subscription_info"]["endpoint"].endswith("sub-b"):
            raise _FakeWebPushException("gone", status_code=410)

    monkeypatch.setattr(push_service, "_webpush_callable", lambda: fake_webpush)
    monkeypatch.setattr(push_service, "_webpush_exception_cls", lambda: _FakeWebPushException)

    stats = push_service.send_push_notification(db_session, [user.id], "T", "B")
    assert stats["sent"] == 1
    assert stats["expired"] == 1
    assert stats["failed"] == 0

    db_session.refresh(subs[0])
    db_session.refresh(subs[1])
    assert subs[0].active is True
    assert subs[1].active is False


def test_send_push_counts_failed_on_generic_error(
    db_session, user_with_subs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_push(monkeypatch)
    user, subs = user_with_subs

    def fake_webpush(**kwargs):
        raise _FakeWebPushException("boom", status_code=500)

    monkeypatch.setattr(push_service, "_webpush_callable", lambda: fake_webpush)
    monkeypatch.setattr(push_service, "_webpush_exception_cls", lambda: _FakeWebPushException)

    stats = push_service.send_push_notification(db_session, [user.id], "T", "B")
    assert stats["sent"] == 0
    assert stats["failed"] == 2
    assert stats["expired"] == 0
    for sub in subs:
        db_session.refresh(sub)
        assert sub.active is True


def test_send_push_skips_inactive_subs(
    db_session, user_with_subs, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_push(monkeypatch)
    user, subs = user_with_subs
    subs[0].active = False
    db_session.commit()

    calls: list[dict] = []
    monkeypatch.setattr(
        push_service, "_webpush_callable", lambda: (lambda **kw: calls.append(kw))
    )
    monkeypatch.setattr(push_service, "_webpush_exception_cls", lambda: _FakeWebPushException)

    stats = push_service.send_push_notification(db_session, [user.id], "T", "B")
    assert stats["sent"] == 1
    assert len(calls) == 1


def test_send_push_returns_zero_when_no_users(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_push(monkeypatch)
    stats = push_service.send_push_notification(db_session, [], "T", "B")
    assert stats == {"sent": 0, "failed": 0, "expired": 0, "enabled": 1}
