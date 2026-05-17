"""Shared pytest fixtures for the HEZ backend test suite.

The fixtures here keep tests independent from the production Postgres
deployment: each test gets an isolated SQLite in-memory database, and
filesystem-touching services run against per-test ``tmp_path`` roots.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Generator
from pathlib import Path

# Ensure the backend package is importable when pytest is invoked from
# the repository root.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Force a SQLite database BEFORE the application settings module loads,
# so that ``from app.core.settings import settings`` never reaches for
# a Postgres connection during test collection.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db import orm_models  # noqa: F401  (registers tables)


@pytest.fixture()
def db_engine():
    """A SQLite-in-memory engine that lives for one test."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:
    """A SQLAlchemy session bound to the per-test in-memory engine."""
    SessionFactory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``settings.storage_root`` to a per-test directory.

    Both ``project_workspace`` and ``privacy_workspace`` resolve their
    paths through ``settings.workspaces_path`` / ``settings.projects_path``
    at call time, so monkeypatching the attribute is sufficient.
    """
    from app.core.settings import settings

    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    (storage_root / "workspaces").mkdir()
    (storage_root / "projects").mkdir()
    (storage_root / "uploads").mkdir()

    monkeypatch.setattr(settings, "storage_root", storage_root)
    return storage_root
