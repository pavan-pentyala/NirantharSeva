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

from app.config import get_settings
from app.db import async_session_factory

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
