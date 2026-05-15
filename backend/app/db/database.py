import time
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy import text
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


def init_db() -> None:
    from app.db import orm_models  # noqa: F401
    from app.services.auth import seed_initial_admin

    last_error: OperationalError | None = None

    for _ in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            _ensure_lightweight_schema_updates()
            with SessionLocal() as db:
                seed_initial_admin(db)
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(2)

    if last_error is not None:
        raise last_error


def _ensure_lightweight_schema_updates() -> None:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS project_type VARCHAR(32) DEFAULT 'standard'"))
