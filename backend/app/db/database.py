import time
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.settings import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _alembic_config():
    """Build an Alembic Config object pointing at the backend project layout."""
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_root / "alembic.ini"
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def run_migrations() -> None:
    """Apply all pending Alembic migrations against the configured database."""
    from alembic import command

    command.upgrade(_alembic_config(), "head")


def init_db() -> None:
    """Wait for the database, apply migrations, and seed the initial admin."""
    from app.db import orm_models  # noqa: F401  (ensure ORM is imported)
    from app.services.auth import seed_initial_admin

    last_error: OperationalError | None = None

    for _ in range(30):
        try:
            run_migrations()
            with SessionLocal() as db:
                seed_initial_admin(db)
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(2)

    if last_error is not None:
        raise last_error
