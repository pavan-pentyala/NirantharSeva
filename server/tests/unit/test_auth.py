"""Auth against the real user table (app_user). See docs/decisions/ADR-006.md.

server/tests/conftest.py's session-scoped autouse fixture seeds the
district (server/app/seed.py) once per test session, so these tests need
no monkeypatching — DEV_USERS is gone.
"""

import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import text

from app.clock import SimulatedClock, get_clock
from app.config import get_settings
from app.db import async_session_factory
from app.main import app

FIXED_TIME = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


def _tamper_payload_role(token: str) -> str:
    """Decode the payload, change a claim, re-encode it, and reassemble
    with the ORIGINAL signature — a signature that no longer matches its
    payload. Flipping a single character of the token string is not a
    reliable way to do this: base64url's final character of a segment can
    carry unused padding bits, and a flip that only touches those bits
    leaves the decoded bytes — and therefore the signature check —
    unchanged by coincidence."""
    header_b64, payload_b64, sig_b64 = token.split(".")
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))
    payload["role"] = "MO"
    new_payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header_b64}.{new_payload_b64}.{sig_b64}"


async def test_login_issues_token_for_valid_credentials(client):
    resp = await client.post("/auth/login", json={"username": "asha_a", "password": "dev"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_rejects_wrong_password(client):
    resp = await client.post("/auth/login", json={"username": "asha_a", "password": "wrong"})
    assert resp.status_code == 401


async def test_login_rejects_unknown_user(client):
    resp = await client.post("/auth/login", json={"username": "nobody", "password": "dev"})
    assert resp.status_code == 401


async def test_token_claims_match_the_real_app_user_row(client):
    resp = await client.post("/auth/login", json={"username": "asha_a", "password": "dev"})
    token = resp.json()["access_token"]

    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == "asha_a"
    assert payload["role"] == "ASHA"

    async with async_session_factory() as session:
        row = (
            await session.execute(
                text("SELECT org_unit_id FROM app_user WHERE name = :name"), {"name": "asha_a"}
            )
        ).one()
    assert payload["org_unit_id"] == str(row.org_unit_id)


async def test_tampered_token_is_rejected(client):
    resp = await client.post("/auth/login", json={"username": "asha_a", "password": "dev"})
    token = resp.json()["access_token"]
    tampered = _tamper_payload_role(token)

    pull_resp = await client.get(
        "/sync/pull?since=0", headers={"authorization": f"Bearer {tampered}"}
    )
    assert pull_resp.status_code == 401


async def test_a_validly_signed_token_for_a_nonexistent_user_is_rejected(client):
    """The token is well-formed and correctly signed, but names a user
    app_user has no row for (e.g. one that was removed after the token was
    issued). get_current_user must still reject it — the database, not the
    token, is authoritative (ADR-006)."""
    settings = get_settings()
    payload = {
        "sub": "nobody",
        "role": "ASHA",
        "org_unit_id": "00000000-0000-0000-0000-000000000000",
        "iat": FIXED_TIME,
        "exp": FIXED_TIME + timedelta(minutes=settings.jwt_expire_minutes),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    resp = await client.get("/sync/pull?since=0", headers={"authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_token_stays_valid_under_a_simulated_clock_in_the_real_past(client):
    """docs/PHASE8_PLAN.md / ADR-016: under CLOCK_MODE=simulated with
    SIM_START behind the real wall clock (true for essentially every
    experiment run), a token's exp claim is computed from the injected
    Clock and lands in what the *real* clock would call the past. PyJWT's
    own jwt.decode() validates exp against the real system clock — it has
    no way to accept an injected one — so before this fix, get_current_user
    rejected every token as expired the instant it checked. Expiry must be
    checked against the same injected Clock login used to mint the token,
    not against PyJWT's own real-time check."""
    sim_clock = SimulatedClock(datetime(2020, 1, 1, tzinfo=UTC))  # well behind real "now"
    app.dependency_overrides[get_clock] = lambda: sim_clock
    try:
        login_resp = await client.post(
            "/auth/login", json={"username": "asha_a", "password": "dev"}
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        # Still within the simulated clock's own validity window — must be
        # accepted, even though a real-time check would call it expired.
        pull_resp = await client.get(
            "/sync/pull?since=0", headers={"authorization": f"Bearer {token}"}
        )
        assert pull_resp.status_code == 200

        # Advance the same simulated clock past the token's own (simulated)
        # expiry — now it really is expired, on the clock that minted it.
        settings = get_settings()
        sim_clock.advance(minutes=settings.jwt_expire_minutes + 1)
        expired_resp = await client.get(
            "/sync/pull?since=0", headers={"authorization": f"Bearer {token}"}
        )
        assert expired_resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_clock, None)


async def test_token_stays_valid_once_the_simulated_clock_passes_real_wall_clock_time(client):
    """The other half of the same bug (see app/api/auth.py's module
    docstring): PyJWT's own iat check rejects a token whose `iat` looks
    like it was issued in the *future* relative to the real system clock
    — which is exactly what happens once a simulated clock, advancing
    through an experiment's stepped loop, crosses real wall-clock "now"
    and keeps going. A token minted and used entirely on one side of that
    line was already covered by the test above; this one straddles it."""
    sim_clock = SimulatedClock(datetime.now(UTC) + timedelta(days=30))
    app.dependency_overrides[get_clock] = lambda: sim_clock
    try:
        login_resp = await client.post(
            "/auth/login", json={"username": "asha_a", "password": "dev"}
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        pull_resp = await client.get(
            "/sync/pull?since=0", headers={"authorization": f"Bearer {token}"}
        )
        assert pull_resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_clock, None)
