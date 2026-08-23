"""Per-cell database create/drop. docs/decisions/ADR-016.md.

A raw asyncpg connection to the `postgres` maintenance database — CREATE
DATABASE / DROP DATABASE cannot run inside a transaction block, and the
application's own engine (app/db.py) is bound to one database name for its
whole process lifetime, never the maintenance one. This module is the only
place in the codebase that connects to `postgres` rather than the app's own
database, and the only privilege the harness needs beyond what the app
itself uses (ADR-016's "second cost").

Database names are built only from this module's own alphanumeric/
underscore cell/seed identifiers (experiments/grid.py, experiments/
runner.py) — never from anything a config file or a user supplies — so
double-quoting is enough; no separate identifier-escaping step is needed
or attempted here.
"""

from urllib.parse import urlsplit, urlunsplit

import asyncpg


def _maintenance_dsn(database_url: str) -> str:
    """The app's own DATABASE_URL uses SQLAlchemy's asyncpg dialect prefix
    (postgresql+asyncpg://...); asyncpg's own connect() wants a bare
    postgresql:// URL, pointed at the `postgres` maintenance database
    rather than whichever database the app's own URL names."""
    bare = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parts = urlsplit(bare)
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))


def database_url_for(database_url: str, db_name: str) -> str:
    """The app-style DATABASE_URL a cell's child process should be given —
    same credentials and host as `database_url`, pointed at `db_name`."""
    parts = urlsplit(database_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{db_name}", "", ""))


async def create_database(database_url: str, db_name: str) -> None:
    """Drops any stale database of the same name first — a cell id is
    reused across runs (a re-run, a --cell retry), and a leftover database
    from a crashed prior run must not silently seed the new one."""
    conn = await asyncpg.connect(_maintenance_dsn(database_url))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


async def drop_database(database_url: str, db_name: str) -> None:
    conn = await asyncpg.connect(_maintenance_dsn(database_url))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
    finally:
        await conn.close()
