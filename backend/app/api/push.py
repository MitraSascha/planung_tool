"""Web-Push-API (Phase 14.4).

Endpoints:
- ``GET  /api/push/public-key``           — VAPID-Public-Key (no auth).
- ``POST /api/push/subscriptions``        — Subscription speichern.
- ``GET  /api/push/subscriptions``        — eigene Subscriptions auflisten.
- ``DELETE /api/push/subscriptions/{endpoint:path}`` — Subscription deaktivieren.
- ``POST /api/push/test``                 — Test-Notification an eigene Subs.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.database import get_db
from app.db.orm_models import PushSubscription, User
from app.models.push import (
    PushPublicKeyResponse,
    PushSubscriptionCreate,
    PushSubscriptionRead,
    PushTestRequest,
    PushTestResponse,
)
from app.services.auth import get_current_user
from app.services.push_service import is_push_enabled, send_push_notification

router = APIRouter()


def _to_read(sub: PushSubscription) -> PushSubscriptionRead:
    return PushSubscriptionRead(
        id=sub.id,
        endpoint=sub.endpoint,
        user_agent=sub.user_agent,
        active=sub.active,
        created_at=sub.created_at,
        last_used_at=sub.last_used_at,
    )


@router.get("/public-key", response_model=PushPublicKeyResponse)
def get_public_key() -> PushPublicKeyResponse:
    """Liefert den VAPID-Public-Key fuer ``PushManager.subscribe()``.

    Bewusst ohne Auth — das Frontend muss vor dem Login wissen, ob Push
    ueberhaupt aktiviert ist. Sensible Daten gibt es hier nicht.
    """
    if not is_push_enabled():
        return PushPublicKeyResponse(vapid_public_key=None, enabled=False)
    return PushPublicKeyResponse(
        vapid_public_key=settings.vapid_public_key,
        enabled=True,
    )


@router.post(
    "/subscriptions",
    response_model=PushSubscriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_subscription(
    request: PushSubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PushSubscriptionRead:
    """Speichert eine Push-Subscription. Idempotent ueber ``endpoint``.

    Existiert bereits eine Subscription mit dem gleichen ``endpoint``,
    werden die Keys/User-Agent aktualisiert und ``active`` wieder auf
    True gesetzt — das ist der Re-Subscribe-Fall, z. B. nach Browser-
    Wechsel oder Permission-Reset.
    """
    p256dh = request.keys.get("p256dh")
    auth_key = request.keys.get("auth")
    if not p256dh or not auth_key:
        raise HTTPException(
            status_code=400,
            detail="keys.p256dh and keys.auth are required",
        )

    sub = (
        db.query(PushSubscription)
        .filter(PushSubscription.endpoint == request.endpoint)
        .one_or_none()
    )
    if sub is None:
        sub = PushSubscription(
            user_id=current_user.id,
            endpoint=request.endpoint,
            p256dh_key=p256dh,
            auth_key=auth_key,
            user_agent=request.user_agent,
            active=True,
        )
        db.add(sub)
    else:
        sub.user_id = current_user.id
        sub.p256dh_key = p256dh
        sub.auth_key = auth_key
        sub.user_agent = request.user_agent or sub.user_agent
        sub.active = True
    db.commit()
    db.refresh(sub)
    return _to_read(sub)


@router.get("/subscriptions", response_model=list[PushSubscriptionRead])
def list_my_subscriptions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PushSubscriptionRead]:
    subs = (
        db.query(PushSubscription)
        .filter(PushSubscription.user_id == current_user.id)
        .order_by(PushSubscription.created_at.desc())
        .all()
    )
    return [_to_read(sub) for sub in subs]


@router.delete(
    "/subscriptions/{endpoint:path}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_subscription(
    endpoint: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    sub = (
        db.query(PushSubscription)
        .filter(
            PushSubscription.endpoint == endpoint,
            PushSubscription.user_id == current_user.id,
        )
        .one_or_none()
    )
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    sub.active = False
    sub.last_used_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/test", response_model=PushTestResponse)
def send_test_push(
    request: PushTestRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PushTestResponse:
    """Schickt eine Test-Notification an alle aktiven Subs des Users."""
    title = (request.title if request and request.title else None) or "Test-Benachrichtigung"
    body = (request.body if request and request.body else None) or (
        f"Hallo {current_user.display_name}, Web-Push funktioniert."
    )
    stats = send_push_notification(
        db,
        [current_user.id],
        title,
        body,
        url="/admin/push",
        tag="hez-test",
    )
    return PushTestResponse(
        sent=stats.get("sent", 0),
        failed=stats.get("failed", 0),
        expired=stats.get("expired", 0),
        enabled=bool(stats.get("enabled", 0)),
    )
