"""Bring the database schema up to date with Alembic.

`ensure_schema()` makes any database — empty, an existing pre-Alembic one created
by the old ``create_all()``, or one already managed by Alembic — converge to the
latest schema:

- **empty DB**: ``alembic upgrade head`` creates every table from the baseline.
- **existing pre-Alembic DB** (our tables present, no ``alembic_version``): we
  ``stamp`` it at head so it adopts the baseline *without recreating* tables,
  preserving the user's collected history.
- **already managed**: ``upgrade head`` applies any pending migrations.

This runs once per process (see ``storage.db.init_db``), so the cost is a single
version check, not a per-write one.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from steam_agent.settings import PROJECT_ROOT, settings
from steam_agent.storage.models import Base

log = logging.getLogger(__name__)

MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
# A table that exists iff this DB was already populated by a previous version.
_SENTINEL_TABLE = "game_snapshot"


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def ensure_schema(engine: Engine) -> None:
    """Upgrade (or stamp) the schema to head. Falls back to create_all() if the
    migrations directory is absent (e.g. an installed wheel without it)."""
    if not MIGRATIONS_DIR.exists():
        log.warning("migrations/ not found — falling back to create_all().")
        Base.metadata.create_all(engine)
        return

    from alembic import command

    cfg = _alembic_config()
    insp = inspect(engine)
    has_version = insp.has_table("alembic_version")
    has_tables = insp.has_table(_SENTINEL_TABLE)

    if not has_version and has_tables:
        # Pre-Alembic DB created by create_all(): adopt the baseline in place.
        log.info("Existing database detected — stamping Alembic baseline.")
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")
