"""SQLAlchemy engine and session. Storage swappable via DATABASE_URL."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from steam_agent.settings import settings

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, future=True, expire_on_commit=False)

_schema_ready = False


def init_db() -> None:
    """Ensure the schema is at the latest Alembic revision.

    Runs the migration check once per process (subsequent calls are no-ops), so
    the many `save_*` call sites stay cheap. Existing pre-Alembic databases are
    stamped, not recreated — see `storage.migrate.ensure_schema`.
    """
    global _schema_ready
    if _schema_ready:
        return
    # Lazy import so Alembic is only loaded when the schema is actually managed
    # (tests that monkeypatch init_db never pay for it).
    from steam_agent.storage.migrate import ensure_schema

    ensure_schema(engine)
    _schema_ready = True
