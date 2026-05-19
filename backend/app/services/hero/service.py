"""High-Level HERO-Service-Funktionen für das Planung-Tool.

Was hier verfügbar ist:

  * :func:`get_company_partners` — alle Mitarbeiter aus dem HERO-Account
  * :func:`sync_partners_to_users` — matcht HERO-Partner auf lokale User
    (über display_name, normalisiert) und schreibt ``users.hero_partner_id``
  * :func:`push_tracking_time` — sendet einen Tracking-Time-Eintrag zu HERO
    (create wenn ``id=None``, sonst update)
  * :func:`get_tracking_time_categories` — Liste der Kategorien (für die
    Default-Auswahl „Arbeitszeit")

Alle Funktionen sind defensiv: bei nicht konfiguriertem Token wird
``HeroError`` geworfen — die Aufrufer sollten das fangen wo HERO optional ist.
"""
from __future__ import annotations

import logging
import unicodedata
from typing import Any

from sqlalchemy.orm import Session

from app.db.orm_models import Project, User

from . import queries as Q
from .client import HeroClient, HeroError

logger = logging.getLogger(__name__)


def _client() -> HeroClient:
    return HeroClient()


# ─── Partners ────────────────────────────────────────────────────────────────


def get_company_partners() -> list[dict[str, Any]]:
    """Alle Mitarbeiter der eigenen Firma (über alle Branches).

    Returns: Liste ``[{id, full_name, email?}, ...]``. ``email`` ist optional
    (nicht alle HERO-Partner haben einen verknüpften User).
    """
    data = _client().execute(Q.COMPANY_PARTNERS)
    branches = (data.get("user") or {}).get("partner", {}).get("company", {}).get(
        "company_branches"
    ) or []
    result: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for branch in branches:
        for p in branch.get("partners") or []:
            pid = p.get("id")
            if pid is None or pid in seen_ids:
                continue
            seen_ids.add(pid)
            result.append({
                "id": int(pid),
                "full_name": (p.get("full_name") or "").strip(),
                "email": ((p.get("user") or {}).get("email") or "").strip() or None,
            })
    return result


def _normalize_name(name: str) -> str:
    """Lower-case + Unicode-Decompose + Entfernung Diakritika.

    „Müller, Hans" → „muller, hans". Damit matchen wir „Murat Özdemir" auch
    wenn HERO „Murat Özdemir" anders schreibt. Whitespace wird kollabiert.
    """
    n = unicodedata.normalize("NFD", name or "")
    n = "".join(ch for ch in n if unicodedata.category(ch) != "Mn")
    return " ".join(n.lower().split())


def sync_partners_to_users(db: Session) -> dict[str, int]:
    """Holt alle HERO-Partner und matcht sie auf lokale User.

    Match-Strategie (in dieser Reihenfolge — erster Hit gewinnt):
      1. **E-Mail**: wenn der HERO-Partner eine E-Mail hat, deren Local-Part
         dem lokalen Username entspricht (case-insensitive). Sehr verlässlich
         weil HERO-E-Mails meist `vorname.nachname@firma`, lokaler Username
         oft genau der Vorname oder Vorname.Nachname.
      2. **Voller Name**: normalisierter display_name == full_name.
      3. **Vorname**: lokaler display_name ist ein einzelnes Wort und matcht
         den **ersten Vornamen** im HERO full_name (z.B. „Patrick" matcht
         „Patrick van Dalen"). Bei mehreren Treffern → ambiguous.

    Bei mehrdeutigen Matches oder gar keinem Treffer wird ``hero_partner_id``
    nicht gesetzt — Admin entscheidet manuell. Bereits gesetzte IDs werden
    nicht überschrieben.
    """
    partners = get_company_partners()

    # Index 1: voller normalisierter Name
    by_fullname: dict[str, list[dict]] = {}
    # Index 2: Vorname (erstes Token im full_name)
    by_firstname: dict[str, list[dict]] = {}
    # Index 3: E-Mail-Local-Part (vor @)
    by_email_local: dict[str, list[dict]] = {}
    for p in partners:
        full = _normalize_name(p["full_name"])
        if full:
            by_fullname.setdefault(full, []).append(p)
            first = full.split(" ")[0]
            if first:
                by_firstname.setdefault(first, []).append(p)
        email = (p.get("email") or "").strip().lower()
        if email and "@" in email:
            local = email.split("@", 1)[0]
            by_email_local.setdefault(local, []).append(p)

    counters = {"matched": 0, "ambiguous": 0, "unchanged": 0, "no_match": 0}
    users = db.query(User).filter(User.active.is_(True)).all()
    for u in users:
        if u.hero_partner_id:
            counters["unchanged"] += 1
            continue

        match: dict | None = None
        ambiguous_seen = False

        # 1. E-Mail (username matched local-part)
        u_username_norm = (u.username or "").strip().lower()
        if u_username_norm:
            candidates = by_email_local.get(u_username_norm) or []
            if len(candidates) == 1:
                match = candidates[0]
            elif len(candidates) > 1:
                ambiguous_seen = True

        # 2. Voller Name
        if match is None and not ambiguous_seen:
            full_key = _normalize_name(u.display_name or u.username)
            candidates = by_fullname.get(full_key) or []
            if len(candidates) == 1:
                match = candidates[0]
            elif len(candidates) > 1:
                ambiguous_seen = True

        # 3. Vorname (nur wenn lokaler Name aus genau einem Wort besteht)
        if match is None and not ambiguous_seen:
            local_norm = _normalize_name(u.display_name or u.username)
            if local_norm and " " not in local_norm:
                candidates = by_firstname.get(local_norm) or []
                if len(candidates) == 1:
                    match = candidates[0]
                elif len(candidates) > 1:
                    ambiguous_seen = True

        if match is None:
            if ambiguous_seen:
                counters["ambiguous"] += 1
                logger.warning(
                    "HERO-Partner-Match mehrdeutig für User %s (%r)",
                    u.id, u.display_name,
                )
            else:
                counters["no_match"] += 1
            continue

        u.hero_partner_id = match["id"]
        counters["matched"] += 1
        logger.info(
            "HERO-Partner-Match: User %s (%s) → partner_id=%s (%s)",
            u.id, u.display_name, match["id"], match["full_name"],
        )
    db.commit()
    logger.info("Partner-Sync abgeschlossen: %s", counters)
    return counters


# ─── Tracking-Time ──────────────────────────────────────────────────────────


def get_tracking_time_categories() -> list[dict[str, Any]]:
    """Kategorien aus HERO. Wir merken uns die ``is_working_time=true``
    Kategorie als Default für unsere Push-Operationen."""
    data = _client().execute(Q.TRACKING_TIMES_CATEGORIES)
    return data.get("tracking_times_categories") or []


def push_tracking_time(
    *,
    partner_id: int,
    project_match_id: int | None,
    start_iso: str,
    end_iso: str | None = None,
    duration_seconds: int | None = None,
    category_id: int | None = None,
    comment: str | None = None,
    existing_id: int | None = None,
) -> dict[str, Any]:
    """Sendet einen Tracking-Time-Eintrag zu HERO.

    Args:
        partner_id: HERO-partner_id des Mitarbeiters.
        project_match_id: HERO-projekt-id. Wenn ``None``, landet die Buchung
            ohne Projekt-Zuordnung (z.B. interne Zeit).
        start_iso: Start-Zeit (ISO 8601, timezone-aware).
        end_iso: End-Zeit. Entweder dieses oder ``duration_seconds`` geben.
        duration_seconds: alternativ zu ``end_iso``.
        category_id: HERO ``tracking_times_categories.id``. Wenn ``None``,
            nutzt HERO die Default-Kategorie.
        comment: Notiz-Feld.
        existing_id: Wenn gesetzt → Update statt Create.

    Returns: Response-Dict der Mutation (enthält ``id``, ``uuid``, etc.).
    """
    tt: dict[str, Any] = {
        "partner_id": int(partner_id),
        "start": start_iso,
    }
    if existing_id is not None:
        tt["id"] = int(existing_id)
    if project_match_id is not None:
        tt["project_match_id"] = int(project_match_id)
    if end_iso is not None:
        tt["end"] = end_iso
    if duration_seconds is not None:
        tt["duration_in_seconds"] = int(duration_seconds)
    if category_id is not None:
        tt["tracking_times_category_id"] = int(category_id)
    if comment:
        tt["comment"] = comment[:1000]
    data = _client().execute(Q.UPDATE_TRACKING_TIME, {"tt": tt})
    return data.get("update_tracking_time") or {}


# ─── Project-Match Suche ────────────────────────────────────────────────────


def search_project_matches(term: str, first: int = 10) -> list[dict[str, Any]]:
    """Globale Suche nach ProjectMatches in HERO — Admin nutzt das beim
    Mapping ``Project.hero_project_match_id``."""
    data = _client().execute(Q.GLOBAL_SEARCH_PROJECTS, {"term": term, "first": first})
    return data.get("global_search") or []
