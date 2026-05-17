"""Web-Push-Versand-Service (Phase 14.4).

Kapselt den Aufruf gegen ``pywebpush.webpush()`` und reagiert auf
HTTP-410/404-Antworten der Push-Services, indem die betroffene
Subscription auf ``active=false`` gesetzt wird.

Der Service ist defensiv: Ist keine ``vapid_public_key`` konfiguriert,
wird kein Versuch unternommen, Nachrichten zu versenden (no-op).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.orm_models import PushSubscription

logger = logging.getLogger(__name__)


def _webpush_callable() -> Any:
    """Lazy-Import von ``pywebpush.webpush``. Tests koennen das Modul mocken
    oder die Funktion via Monkeypatch ersetzen, ohne ``pywebpush`` zur
    Test-Zeit installiert haben zu muessen.
    """
    try:
        from pywebpush import webpush  # type: ignore[import-untyped]

        return webpush
    except Exception:  # noqa: BLE001 — Lib evtl. nicht installiert
        return None


def _webpush_exception_cls() -> type[BaseException]:
    try:
        from pywebpush import WebPushException  # type: ignore[import-untyped]

        return WebPushException
    except Exception:  # noqa: BLE001
        return Exception


def is_push_enabled() -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def send_push_notification(
    db: Session,
    user_ids: list[int],
    title: str,
    body: str,
    *,
    icon: str | None = None,
    url: str | None = None,
    tag: str | None = None,
) -> dict[str, int]:
    """Schickt eine Web-Push an alle aktiven Subscriptions der Nutzer.

    Returns:
        Dict ``{"sent": N, "failed": N, "expired": N, "enabled": 0|1}``.
        ``expired`` zaehlt 410/404-Antworten — diese Subscriptions werden
        unmittelbar als ``active=false`` markiert.
    """
    stats = {"sent": 0, "failed": 0, "expired": 0, "enabled": 1 if is_push_enabled() else 0}

    if not is_push_enabled():
        return stats

    if not user_ids:
        return stats

    subs: list[PushSubscription] = (
        db.query(PushSubscription)
        .filter(
            PushSubscription.user_id.in_(user_ids),
            PushSubscription.active.is_(True),
        )
        .all()
    )

    if not subs:
        return stats

    webpush = _webpush_callable()
    WebPushExc = _webpush_exception_cls()

    if webpush is None:
        logger.warning(
            "pywebpush ist nicht installiert — Push-Versand uebersprungen (%d Subs)",
            len(subs),
        )
        stats["failed"] = len(subs)
        return stats

    payload = {
        "title": title,
        "body": body,
        "icon": icon,
        "url": url,
        "tag": tag,
    }
    data = json.dumps({k: v for k, v in payload.items() if v is not None})

    vapid_claims = {"sub": settings.vapid_subject}

    now = datetime.now(timezone.utc)

    for sub in subs:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh_key, "auth": sub.auth_key},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=data,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims=dict(vapid_claims),
            )
            sub.last_used_at = now
            stats["sent"] += 1
        except WebPushExc as exc:  # type: ignore[misc]
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in (404, 410):
                sub.active = False
                stats["expired"] += 1
                logger.info(
                    "Push-Subscription %s als abgelaufen markiert (HTTP %s)",
                    sub.id,
                    status_code,
                )
            else:
                stats["failed"] += 1
                logger.warning(
                    "Push-Versand fehlgeschlagen fuer Subscription %s: %s",
                    sub.id,
                    exc,
                )
        except Exception as exc:  # noqa: BLE001 — jeden Fehler einfangen
            stats["failed"] += 1
            logger.exception(
                "Unerwarteter Fehler beim Push-Versand fuer Subscription %s: %s",
                sub.id,
                exc,
            )

    try:
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Konnte Push-Subscription-Status nicht persistieren")

    return stats
