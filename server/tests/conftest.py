import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_headers(client):
    """Requires DEV_USERS to include asha1:dev:ASHA:1 (the default in
    .env.example and in CI's server job env)."""
    resp = await client.post("/auth/login", json={"username": "asha1", "password": "dev"})
    token = resp.json()["access_token"]
    return {"authorization": f"Bearer {token}"}
