"""Async DB engine, session factory, and the sequence-ordering lock.

See docs/decisions/ADR-002.md for why SEQ_LOCK exists: Postgres allocates
BIGSERIAL values at insert time, not commit time, so without this lock the
pull cursor can silently skip events under concurrent writers.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


# Arbitrary constant, documented in ADR-002. Global, not per-referral — the
# pull cursor is a single global sequence, so the ordering guarantee must be
# global too.
SEQ_LOCK = 4711


async def acquire_seq_lock(session: AsyncSession) -> None:
    """Take the transaction-scoped advisory lock before appending an event.

    Held until the enclosing transaction commits or rolls back — Postgres
    releases _xact_ locks automatically. Because this lock is taken inside
    the same transaction as the receipt write and the effect (I1), it is
    held for the whole operation, not just the insert. Keep that transaction
    small.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": SEQ_LOCK})
