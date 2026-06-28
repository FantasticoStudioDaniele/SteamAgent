"""SQLAlchemy engine and session. Storage swappable via DATABASE_URL."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from steam_agent.settings import settings
from steam_agent.storage.models import Base

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, future=True, expire_on_commit=False)


def init_db() -> None:
    """Create the tables if they do not exist (idempotent)."""
    Base.metadata.create_all(engine)
