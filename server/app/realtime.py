"""Postgres LISTEN/NOTIFY fan-out for the dashboard stream. ADR-011 — the
scheduler and the API are separate processes (plan §2.3, E4's fault
injection depends on that separation), so an in-process pub/sub in the API
can never see an escalation the scheduler wrote. LISTEN/NOTIFY is the
transport between them; this module is the API-side half of it.

A notification is a signal that something changed, never the changed data
(ADR-011) — every subscriber re-runs its own org-scoped query in response
(app/api/dashboard.py). This module only wakes subscribers; it holds no
escalation data itself.

The LISTEN connection is a single asyncpg connection held outside
SQLAlchemy's pool for the API process's lifetime (ADR-011's "second cost")
— started and stopped from app/main.py's lifespan, not per-request.
"""

import asyncio

import asyncpg

from app.config import get_settings
from app.instrumentation.logging import get_logger

ESCALATION_CHANNEL = "nirantharseva_escalation"

_logger = get_logger(__name__)

_listen_connection: asyncpg.Connection | None = None
_subscribers: set[asyncio.Queue] = set()


def _asyncpg_dsn(database_url: str) -> str:
    """asyncpg.connect() doesn't understand SQLAlchemy's "+asyncpg" driver
    suffix — only the plain postgresql:// scheme."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _on_notify(_connection: object, _pid: int, _channel: str, _payload: str) -> None:
    for queue in _subscribers:
        try:
            queue.put_nowait(None)
        except asyncio.QueueFull:
            pass  # a wake is already pending for this subscriber; one is enough


async def start_listening() -> None:
    global _listen_connection
    dsn = _asyncpg_dsn(get_settings().database_url)
    _listen_connection = await asyncpg.connect(dsn)
    await _listen_connection.add_listener(ESCALATION_CHANNEL, _on_notify)
    _logger.info("listening for escalation notifications", extra={"run_id": get_settings().run_id})


async def stop_listening() -> None:
    global _listen_connection
    if _listen_connection is not None:
        await _listen_connection.close()
        _listen_connection = None


def subscribe() -> asyncio.Queue:
    """One wake-up queue per open SSE connection. maxsize=1: a pending wake
    already means "re-query soon" — a second notification before that
    re-query runs adds nothing, so it's dropped rather than queued."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    _subscribers.discard(queue)
