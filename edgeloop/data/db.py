"""Engine and session factory.

One env var, DATABASE_URL, switches SQLite (local default) for Postgres
(Railway). Same shape as the desk-trading service.

SQLite needs two pragmas set on every connection or two of the schema's
guarantees quietly stop holding:

* ``foreign_keys=ON`` -- off by default in SQLite, which would let a resolution
  reference a forecast that does not exist.
* CHECK constraints are enforced natively, so the no-lookahead guarantee holds
  on both engines without dialect-specific code.
"""
from __future__ import annotations

import sqlite3

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings, load_settings
from .models import Base


@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    """Turn on foreign keys for every SQLite connection in the process.

    Registered against the Engine class rather than against one engine
    instance on purpose. SQLite ships with foreign keys OFF, so a referential
    guarantee that depends on remembering to build the engine through
    ``create_db_engine`` is a guarantee that silently disappears the first time
    someone calls ``create_engine`` directly -- in a test, a script, or a
    migration. Attaching it here makes the behaviour a property of the process,
    not of the call site.

    Postgres connections are untouched; it enforces foreign keys natively.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_db_engine(settings: Settings | None = None, echo: bool = False) -> Engine:
    settings = settings or load_settings()
    url = settings.database_url

    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            from pathlib import Path

            Path(path).parent.mkdir(parents=True, exist_ok=True)

    # Foreign keys are handled by the process-wide listener above, so an engine
    # built any other way carries the same guarantee.
    return create_engine(url, echo=echo, future=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_all(engine: Engine) -> None:
    """Create the schema directly.

    Alembic owns migrations for anything deployed. This exists for tests and
    for the phase 1 proof, where a throwaway SQLite file is faster and clearer
    than running a migration chain.
    """
    Base.metadata.create_all(engine)
