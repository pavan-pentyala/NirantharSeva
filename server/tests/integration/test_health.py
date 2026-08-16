"""Requires a real Postgres — this is what proves the DB round trip, not
just that the process started."""


async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["clock_mode"] in ("real", "simulated")
    assert "server_time" in body
