import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.seed import seed


@pytest.fixture(scope="session", autouse=True)
async def _seed_district():
    """Same seed() the CLI and CI use (docs/PHASE2_PLAN.md D4/P2.2) — so
    demo data and test data can never drift apart. Session-scoped and
    autouse: every test, sync or async, gets the district seeded before it
    runs, including tests/property/test_referral_replay.py, which never
    requests a fixture explicitly."""
    await seed()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _login(client, username: str, password: str = "dev") -> dict:
    resp = await client.post("/auth/login", json={"username": username, "password": password})
    token = resp.json()["access_token"]
    return {"authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers(client):
    """asha_a — Village A. Seeded by app.seed (D4, docs/PHASE2_PLAN.md)."""
    return await _login(client, "asha_a")


@pytest.fixture
async def asha_b_auth_headers(client):
    """asha_b — Village B. The other village in the org-scoping fixture."""
    return await _login(client, "asha_b")


@pytest.fixture
async def anm_auth_headers(client):
    """anm1 — Sub-centre Kotwali, above both villages."""
    return await _login(client, "anm1")


@pytest.fixture
async def mo_auth_headers(client):
    """mo1 — PHC Ramnagar, above the sub-centre."""
    return await _login(client, "mo1")


@pytest.fixture
async def supervisor_auth_headers(client):
    """supervisor1 — PHC Ramnagar. No GUARDS entry writes as this role in
    Phase 2; it only reads (D5)."""
    return await _login(client, "supervisor1")
