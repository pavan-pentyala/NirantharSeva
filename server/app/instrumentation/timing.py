"""Request timing middleware. See plan §12 — E5 becomes a query against
request_timing instead of a re-run.

Elapsed time is measured with time.perf_counter(), a monotonic interval
counter — this is not a "current time" call in the sense docs/decisions/
ADR-001.md bans; it never produces a stored timestamp value, only a
duration. The "at" column, which is a real timestamp, comes from the
injected Clock.

Never lets a timing-write failure break the actual response.
"""

from time import perf_counter

from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.clock import get_clock
from app.config import get_settings
from app.db import async_session_factory
from app.instrumentation.logging import get_logger

logger = get_logger("instrumentation.timing")


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = perf_counter()
        response = await call_next(request)
        duration_ms = (perf_counter() - start) * 1000

        try:
            clock = get_clock()
            settings = get_settings()
            async with async_session_factory() as session, session.begin():
                await session.execute(
                    text(
                        """INSERT INTO request_timing
                             (endpoint, method, status, duration_ms, run_id, at)
                           VALUES
                             (:endpoint, :method, :status, :duration_ms, :run_id, :at)"""
                    ),
                    {
                        "endpoint": request.url.path,
                        "method": request.method,
                        "status": response.status_code,
                        "duration_ms": duration_ms,
                        "run_id": settings.run_id or None,
                        "at": clock.now(),
                    },
                )
        except Exception:
            logger.exception("failed to record request timing")

        return response
