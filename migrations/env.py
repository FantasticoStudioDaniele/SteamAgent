"""Alembic migration environment for SteamAgent.

The database URL and target schema come from the application itself
(`settings.database_url` + `Base.metadata`), so migrations always match the
running app and a single `alembic upgrade head` works against SQLite or Postgres.
`render_as_batch` is enabled for SQLite, whose limited ALTER TABLE needs Alembic's
table-rebuild (batch) mode.

We deliberately do NOT call logging.fileConfig here: the app configures its own
logging (Rich), and reconfiguring it from alembic.ini would clobber that.
"""
from __future__ import annotations

from sqlalchemy import engine_from_config, pool

from alembic import context
from steam_agent.settings import settings
from steam_agent.storage.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite(url or ""),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
