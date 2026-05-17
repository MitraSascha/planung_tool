"""Cross-document auto-sync — when domain data changes, re-render every
template for the affected project so the static HTMLs under
``storage/projects/<slug>/`` always reflect the current DB state.

Architecture:

- A SQLAlchemy ``after_commit`` listener on the global ``Session`` factory
  observes which projects had domain rows touched (insert/update/delete).
- For each touched project we schedule a debounced re-render via a small
  ``threading.Timer`` map: rapid successive edits collapse into one render
  after the debounce window expires.
- The actual render runs in a worker thread with its own DB session, so
  the originating HTTP request returns immediately and Postgres locks
  release on time.

The whole feature is gated by ``AUTO_RERENDER_ENABLED`` (defaults to True)
so it can be toggled off via env without touching code.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Iterable

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, engine
from app.db.orm_models import (
    Blocker,
    DailyReport,
    FormResponse,
    HeatingCircuit,
    HeatingDesign,
    MaterialIssue,
    MaterialItem,
    Project,
    ProjectMember,
    ProjectSection,
    RiskIssue,
    SectionSchedule,
    TeamStatusEntry,
    WeeklyReport,
)
from app.services import template_publisher

logger = logging.getLogger(__name__)


# Models whose changes should retrigger a re-render. Each one must expose
# either a direct ``project_id`` column or a ``project`` relationship the
# helper below can follow to reach one.
WATCHED_MODELS: tuple[type, ...] = (
    Project,
    ProjectSection,
    ProjectMember,
    SectionSchedule,
    TeamStatusEntry,
    MaterialItem,
    MaterialIssue,
    RiskIssue,
    Blocker,
    HeatingDesign,
    HeatingCircuit,
    DailyReport,
    WeeklyReport,
    FormResponse,
)

# How long to wait after the last write before rendering — collapses
# rapid form-sync POSTs into one render.
_DEBOUNCE_SECONDS = float(os.environ.get("AUTO_RERENDER_DEBOUNCE_SECONDS", "2.0"))

# Master switch.
_ENABLED = os.environ.get("AUTO_RERENDER_ENABLED", "true").lower() not in {
    "0",
    "false",
    "no",
    "off",
}

# project_id -> active Timer. Replaced when a new write arrives within
# the debounce window.
_pending_timers: dict[int, threading.Timer] = {}
_pending_lock = threading.Lock()


def _resolve_project_id(instance: object) -> int | None:
    """Best-effort: pull a project_id out of any watched ORM instance."""
    if isinstance(instance, Project):
        return instance.id
    pid = getattr(instance, "project_id", None)
    if isinstance(pid, int):
        return pid
    # Some indirect rows (HeatingCircuit) reach the project via a parent.
    parent = getattr(instance, "design", None) or getattr(instance, "section", None)
    if parent is not None:
        return getattr(parent, "project_id", None)
    return None


def _collect_touched_project_ids(session: Session) -> set[int]:
    touched: set[int] = set()
    for collection in (session.new, session.dirty, session.deleted):
        for obj in collection:
            if not isinstance(obj, WATCHED_MODELS):
                continue
            pid = _resolve_project_id(obj)
            if pid is not None:
                touched.add(pid)
    return touched


def _render_project_async(project_id: int) -> None:
    """Run inside a worker thread. Resolves slug, then publishes templates."""
    try:
        with SessionLocal() as db:
            project = db.query(Project).filter(Project.id == project_id).one_or_none()
            if project is None:
                return
            template_publisher.publish_templates_to_storage(db, project.slug)
            logger.info("auto-sync: re-rendered project '%s'", project.slug)
    except Exception:  # noqa: BLE001 — never let auto-sync crash the server
        logger.exception("auto-sync: render failed for project_id=%s", project_id)


def _schedule_render(project_id: int) -> None:
    """Cancel any pending timer for this project and start a fresh one."""
    if not _ENABLED:
        return

    def _fire() -> None:
        with _pending_lock:
            _pending_timers.pop(project_id, None)
        thread = threading.Thread(
            target=_render_project_async,
            args=(project_id,),
            name=f"auto-sync-render-{project_id}",
            daemon=True,
        )
        thread.start()

    with _pending_lock:
        existing = _pending_timers.pop(project_id, None)
        if existing is not None:
            existing.cancel()
        timer = threading.Timer(_DEBOUNCE_SECONDS, _fire)
        timer.daemon = True
        _pending_timers[project_id] = timer
        timer.start()


# SQLAlchemy session events. We snapshot project ids in `after_flush_postexec`
# (after autoflush settles, before commit fires) so deleted instances still
# carry their attributes; then we kick off renders only on successful commit.
def _on_before_flush(session: Session, _flush_context, _instances) -> None:
    # session.new / .dirty / .deleted are populated BEFORE flush; after
    # flush the rows are already moved to the identity map and the sets
    # are empty. So we snapshot here and aggregate across multiple
    # flushes of the same transaction in session.info.
    pending = _collect_touched_project_ids(session)
    if pending:
        bag = session.info.setdefault("_auto_sync_pending", set())
        bag.update(pending)


def _on_after_commit(session: Session) -> None:
    pending: Iterable[int] = session.info.pop("_auto_sync_pending", ())
    for pid in pending:
        _schedule_render(pid)


def _on_after_rollback(session: Session) -> None:
    session.info.pop("_auto_sync_pending", None)


def request_render(project_id: int) -> None:
    """Public API for endpoints that want to explicitly trigger a re-render
    (e.g. after a mutation that touches project data). Idempotent within
    the debounce window."""
    _schedule_render(project_id)


def register_listeners() -> None:
    """Wire the session events. Idempotent."""
    if not _ENABLED:
        logger.info("auto-sync: disabled via AUTO_RERENDER_ENABLED env")
        return
    # Register on the base Session class so every session derived from
    # SessionLocal (or any other sessionmaker bound to our engine) gets
    # the hooks. Doing this on the sessionmaker target proved unreliable
    # in some FastAPI/dependency-injection paths.
    event.listen(Session, "before_flush", _on_before_flush)
    event.listen(Session, "after_commit", _on_after_commit)
    event.listen(Session, "after_soft_rollback", _on_after_rollback)
    logger.info(
        "auto-sync: enabled (debounce=%.1fs, watched=%d models)",
        _DEBOUNCE_SECONDS,
        len(WATCHED_MODELS),
    )
