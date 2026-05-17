"""DTOs fuer den Web-Push-API-Layer (Phase 14.4)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PushSubscriptionCreate(BaseModel):
    """Eingang vom Browser nach erfolgreichem ``PushManager.subscribe()``.

    ``keys`` enthaelt mindestens die Felder ``p256dh`` und ``auth`` (URL-safe
    base64). Das Backend speichert beide einzeln in der DB.
    """

    endpoint: str = Field(min_length=8, max_length=1024)
    keys: dict[str, str]
    user_agent: str | None = None


class PushSubscriptionRead(BaseModel):
    id: int
    endpoint: str
    user_agent: str | None
    active: bool
    created_at: datetime
    last_used_at: datetime | None


class PushPublicKeyResponse(BaseModel):
    """Antwort von ``GET /api/push/public-key``.

    ``enabled=False`` bedeutet: Der Server hat keine VAPID-Keys konfiguriert,
    das Frontend soll Push-Funktionalitaet ausblenden.
    """

    vapid_public_key: str | None = None
    enabled: bool = False


class PushTestRequest(BaseModel):
    title: str | None = None
    body: str | None = None


class PushTestResponse(BaseModel):
    sent: int
    failed: int
    expired: int
    enabled: bool
