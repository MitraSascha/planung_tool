"""HERO GraphQL Client (synchron, mit Retry für transiente Fehler).

Angepasste Übernahme aus MitraApp/apps/hero/client.py. Statt
``django.conf.settings`` lesen wir aus ``app.core.settings.settings``.
"""
from __future__ import annotations

import logging
import time

import httpx

from app.core.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_GRAPHQL_URL = "https://login.hero-software.de/api/external/v7/graphql"

# HTTP-Status-Codes die als „temporäres Problem" gelten und Retry rechtfertigen.
_RETRY_STATUS_CODES = {500, 502, 503, 504, 429}
_RETRY_MAX = 3
_RETRY_BASE_DELAY = 1.0


class HeroError(Exception):
    pass


class HeroClient:
    """Synchroner GraphQL-Client mit Retry-Logic für transiente Fehler.

    Token aus ``settings.hero_api_token`` (Format: ``"Bearer xxx..."``).
    URL aus ``settings.hero_graphql_url`` (Default: HERO v7 GraphQL Endpoint).
    """

    def __init__(self, token: str | None = None, timeout: float = 30.0) -> None:
        self.token = token or settings.hero_api_token
        self.url = settings.hero_graphql_url or DEFAULT_GRAPHQL_URL
        self.timeout = timeout
        if not self.token:
            raise HeroError("HERO_API_TOKEN nicht konfiguriert")

    def _headers(self) -> dict[str, str]:
        # Token enthält bereits "Bearer ..." (Konvention aus bestehender Integration).
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    def execute(self, query: str, variables: dict | None = None) -> dict:
        """Führt eine GraphQL-Query aus, mit Retry bei 5xx/429/Network-Errors.
        Wirft :class:`HeroError` bei dauerhaftem Fehler."""
        payload = {"query": query, "variables": variables or {}}
        last_exc: Exception | None = None

        for versuch in range(_RETRY_MAX):
            try:
                response = httpx.post(
                    self.url,
                    json=payload,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
                if response.status_code in _RETRY_STATUS_CODES:
                    delay = _RETRY_BASE_DELAY * (2 ** versuch)
                    logger.warning(
                        "HERO HTTP %s (Versuch %d/%d) — warte %.1fs",
                        response.status_code, versuch + 1, _RETRY_MAX, delay,
                    )
                    if versuch < _RETRY_MAX - 1:
                        time.sleep(delay)
                        continue
                    raise HeroError(f"HERO {response.status_code} nach {_RETRY_MAX} Versuchen")

                response.raise_for_status()
                data = response.json()
                if "errors" in data:
                    raise HeroError(f"HERO GraphQL-Fehler: {data['errors']}")
                return data.get("data") or {}

            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                delay = _RETRY_BASE_DELAY * (2 ** versuch)
                logger.warning(
                    "HERO Netzwerk-Fehler %s (Versuch %d/%d) — warte %.1fs",
                    type(exc).__name__, versuch + 1, _RETRY_MAX, delay,
                )
                if versuch < _RETRY_MAX - 1:
                    time.sleep(delay)
                    continue
                raise HeroError(
                    f"HERO nicht erreichbar nach {_RETRY_MAX} Versuchen: {exc}"
                ) from exc

            except httpx.HTTPError as exc:
                raise HeroError(f"HERO HTTP-Fehler: {exc}") from exc

        raise HeroError(f"HERO unerreichbar: {last_exc}")


def is_configured() -> bool:
    """True wenn HERO-Token gesetzt ist. Frontend / Services können damit
    softfailen — leere Integration statt 500."""
    return bool(settings.hero_api_token)
