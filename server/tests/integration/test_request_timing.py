"""Every request appears in request_timing (plan §12) — E5 is then a query,
not a re-run."""

from sqlalchemy import text

from app.db import async_session_factory


async def test_request_is_recorded_in_request_timing(client, auth_headers):
    resp = await client.get("/health")
    assert resp.status_code == 200

    async with async_session_factory() as session:
        result = await session.execute(
            text(
                """SELECT endpoint, method, status, duration_ms
                   FROM request_timing
                   WHERE endpoint = '/health'
                   ORDER BY id DESC
                   LIMIT 1"""
            )
        )
        row = result.mappings().one()

    assert row["method"] == "GET"
    assert row["status"] == 200
    assert row["duration_ms"] is not None
    assert row["duration_ms"] >= 0
