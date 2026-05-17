"""Audit-Log fuer DSGVO-relevante CRUD-Operationen.

Registriert SQLAlchemy-Event-Listener (``after_insert``/``after_update``/
``after_delete``) auf einer kuratierten Menge von "tracked" Entitaeten und
schreibt fuer jede Aenderung einen ``AuditEvent``-Datensatz in dieselbe
Session. Speichert NUR Spaltennamen bei Updates — keine Werte (DSGVO).

Request-Context (``user_id``, ``ip``, ``user_agent``) wird via
``ContextVar`` aus einer FastAPI-Middleware uebergeben. Cron-/Hintergrund-
Jobs koennen die ContextVars leer lassen — der Eintrag bleibt trotzdem
nachvollziehbar.

Hook ist via ``settings.disable_audit_hook`` abschaltbar; in der Test-Suite
wird das per Fixture monkey-patched.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any

from fastapi import Request
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.orm_models import (
    AuditEvent,
    Blocker,
    DailyReport,
    GenerationRun,
    HeatingDesign,
    MaterialIssue,
    Project,
    ProjectMember,
    ProjectSection,
    User,
    WeeklyReport,
)

logger = logging.getLogger(__name__)

# Per-request context — gesetzt durch ``AuditContextMiddleware``.
audit_user_id: ContextVar[int | None] = ContextVar("audit_user_id", default=None)
audit_ip: ContextVar[str | None] = ContextVar("audit_ip", default=None)
audit_user_agent: ContextVar[str | None] = ContextVar("audit_user_agent", default=None)


TRACKED_ENTITIES: tuple[type, ...] = (
    Project,
    ProjectSection,
    User,
    ProjectMember,
    DailyReport,
    WeeklyReport,
    Blocker,
    MaterialIssue,
    GenerationRun,
    HeatingDesign,
)


_listeners_registered = False


def _hook_disabled() -> bool:
    return bool(getattr(settings, "disable_audit_hook", False))


def _entity_id(target: Any) -> str | None:
    """Best-effort Stringifizierung des Primaerschluessels."""
    try:
        pk = inspect(target).identity
    except Exception:  # noqa: BLE001
        pk = None
    if pk is None:
        pk_attr = getattr(target, "id", None)
        if pk_attr is None:
            return None
        return str(pk_attr)
    if isinstance(pk, tuple) and len(pk) == 1:
        return str(pk[0])
    return str(pk)


def _project_slug_from_target(target: Any, connection: Any = None) -> str | None:
    """Versucht, eine ``project_slug``-Referenz aus dem Target zu ermitteln.

    Reihenfolge: eigener slug (bei ``Project`` selbst) -> bereits geladene
    ``project``-Relation -> Lookup ueber ``project_id`` direkt via
    SQL-``Connection`` (Session ist in after_insert/after_update gerade im
    Flush und nicht safe zu benutzen).
    """
    slug = getattr(target, "slug", None)
    if isinstance(target, Project) and slug:
        return str(slug)
    try:
        project_state = getattr(target, "__dict__", {}).get("project")
        if project_state is not None and getattr(project_state, "slug", None):
            return str(project_state.slug)
    except Exception:  # noqa: BLE001
        pass
    project_id = getattr(target, "project_id", None)
    if project_id is not None and connection is not None:
        try:
            from sqlalchemy import select

            row = connection.execute(
                select(Project.__table__.c.slug).where(Project.__table__.c.id == project_id)
            ).first()
            if row is not None:
                return str(row[0])
        except Exception:  # noqa: BLE001
            return None
    return None


def _entity_type_name(target: Any) -> str:
    return type(target).__name__


def log(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: str | None,
    project_slug: str | None = None,
    changes: dict | None = None,
) -> AuditEvent:
    """Schreibt einen ``AuditEvent``-Datensatz und committed NICHT.

    Aufrufer-Code (insbesondere DSGVO-Workflow) ist fuer den Commit
    verantwortlich, damit die Operation atomar bleibt.
    """
    event_row = AuditEvent(
        user_id=audit_user_id.get(),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        project_slug=project_slug,
        changes_json=json.dumps(changes, ensure_ascii=False, sort_keys=True) if changes else None,
        ip_address=audit_ip.get(),
        user_agent=audit_user_agent.get(),
    )
    db.add(event_row)
    return event_row


def _changed_columns(target: Any) -> list[str]:
    """Liefert die Liste der Spalten, deren Wert seit dem letzten Load
    modifiziert wurde. Wir geben NUR die Namen zurueck (keine Werte) — das
    ist explizit DSGVO-konformer Default.
    """
    try:
        insp = inspect(target)
    except Exception:  # noqa: BLE001
        return []
    if insp is None:
        return []

    changed: list[str] = []
    for attr in insp.mapper.column_attrs:
        history = insp.attrs[attr.key].history
        if history.has_changes():
            changed.append(attr.key)
    return changed


def _insert_audit_row(
    connection: Any,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None,
    project_slug: str | None,
    changes: dict | None,
) -> None:
    """Schreibt direkt via ``Connection.execute`` in ``audit_events`` —
    in ``after_insert``/``after_update``/``after_delete`` ist die Session
    bereits im Flush, ein erneutes ``session.add()`` waere unsicher.
    """
    table = AuditEvent.__table__
    payload = {
        "user_id": audit_user_id.get(),
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "project_slug": project_slug,
        "changes_json": (
            json.dumps(changes, ensure_ascii=False, sort_keys=True) if changes else None
        ),
        "ip_address": audit_ip.get(),
        "user_agent": audit_user_agent.get(),
    }
    try:
        connection.execute(table.insert().values(**payload))
    except Exception:  # noqa: BLE001 — Audit darf das Original-Insert nicht killen
        logger.exception(
            "Audit-Log konnte nicht geschrieben werden: action=%s entity=%s",
            action,
            entity_type,
        )


def _after_insert(mapper: Any, connection: Any, target: Any) -> None:
    if _hook_disabled():
        return
    _insert_audit_row(
        connection,
        action="create",
        entity_type=_entity_type_name(target),
        entity_id=_entity_id(target),
        project_slug=_project_slug_from_target(target, connection),
        changes=None,
    )


def _after_update(mapper: Any, connection: Any, target: Any) -> None:
    if _hook_disabled():
        return
    columns = _changed_columns(target)
    if not columns:
        # SQLAlchemy ruft after_update auch bei No-Op-Flushes — dann nichts loggen.
        return
    _insert_audit_row(
        connection,
        action="update",
        entity_type=_entity_type_name(target),
        entity_id=_entity_id(target),
        project_slug=_project_slug_from_target(target, connection),
        changes={"columns": columns},
    )


def _after_delete(mapper: Any, connection: Any, target: Any) -> None:
    if _hook_disabled():
        return
    _insert_audit_row(
        connection,
        action="delete",
        entity_type=_entity_type_name(target),
        entity_id=_entity_id(target),
        project_slug=_project_slug_from_target(target, connection),
        changes=None,
    )


def register_listeners() -> None:
    """Registriere Audit-Hooks fuer alle ``TRACKED_ENTITIES``. Idempotent."""
    global _listeners_registered
    if _listeners_registered:
        return
    if _hook_disabled():
        logger.info("Audit-Hook deaktiviert (disable_audit_hook=True)")
        _listeners_registered = True
        return

    for entity in TRACKED_ENTITIES:
        event.listen(entity, "after_insert", _after_insert)
        event.listen(entity, "after_update", _after_update)
        event.listen(entity, "after_delete", _after_delete)

    _listeners_registered = True
    logger.info(
        "Audit-Hook registriert fuer %d Entitaeten", len(TRACKED_ENTITIES)
    )


def unregister_listeners() -> None:
    """Nuetzlich fuer Tests."""
    global _listeners_registered
    if not _listeners_registered:
        return
    for entity in TRACKED_ENTITIES:
        for hook_name, handler in (
            ("after_insert", _after_insert),
            ("after_update", _after_update),
            ("after_delete", _after_delete),
        ):
            try:
                event.remove(entity, hook_name, handler)
            except Exception:  # noqa: BLE001
                pass
    _listeners_registered = False


# ---------------------------------------------------------------------------
# Request-Context: FastAPI-Middleware setzt IP + UA aus jedem Request.
# user_id wird derzeit nur fuer DSGVO-/Admin-Routes ueber die Dependency
# ``set_audit_user_id`` zusaetzlich gesetzt; alle anderen Routen koennen den
# Dependency-Hook ueberspringen (Audit-Eintrag bleibt mit user_id=NULL gueltig).
# ---------------------------------------------------------------------------

try:
    from starlette.middleware.base import BaseHTTPMiddleware

    class AuditContextMiddleware(BaseHTTPMiddleware):
        """Setzt ``audit_ip`` und ``audit_user_agent`` pro Request."""

        async def dispatch(self, request: Request, call_next):  # type: ignore[override]
            ip_token = audit_ip.set(request.client.host if request.client else None)
            ua_token = audit_user_agent.set(request.headers.get("user-agent"))
            uid_token = audit_user_id.set(None)
            try:
                response = await call_next(request)
            finally:
                audit_user_id.reset(uid_token)
                audit_user_agent.reset(ua_token)
                audit_ip.reset(ip_token)
            return response
except Exception:  # noqa: BLE001 — Starlette ist mit FastAPI immer da, defensive
    AuditContextMiddleware = None  # type: ignore[assignment]


def set_audit_user(user_id: int | None) -> None:
    """Hilfsfunktion, um aus einer Route den aktuellen User in den Audit-
    Context zu setzen. Wird typischerweise nach ``get_current_user``
    aufgerufen.
    """
    audit_user_id.set(user_id)
