import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


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
    """Requires DEV_USERS to include asha1:dev:ASHA:1 (the default in
    .env.example and in CI's server job env)."""
    return await _login(client, "asha1")


@pytest.fixture
async def anm_auth_headers(client):
    """Requires DEV_USERS to include anm1:dev:ANM:1."""
    return await _login(client, "anm1")


@pytest.fixture
async def mo_auth_headers(client):
    """Requires DEV_USERS to include mo1:dev:MO:1."""
    return await _login(client, "mo1")
