"""Auth stub tests. No database needed — dev users come from config (P0 only,
see PROGRESS.md). Hermetic: each test clears the lru_cache'd stores it
touches so DEV_USERS changes in one test never leak into another.
"""

import jwt
import pytest

from app.api import auth as auth_module
from app.clock import RealClock
from app.config import Settings


@pytest.fixture(autouse=True)
def _clear_caches():
    auth_module._dev_user_store.cache_clear()
    yield
    auth_module._dev_user_store.cache_clear()


def _settings(dev_users: str) -> Settings:
    return Settings(dev_users=dev_users, jwt_secret="test-secret-at-least-32-bytes-long!!")


async def test_login_issues_token_for_valid_credentials(client, monkeypatch):
    monkeypatch.setenv("DEV_USERS", "asha1:dev:ASHA:1")
    from app.config import get_settings

    get_settings.cache_clear()

    resp = await client.post("/auth/login", json={"username": "asha1", "password": "dev"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    get_settings.cache_clear()


async def test_login_rejects_wrong_password(client, monkeypatch):
    monkeypatch.setenv("DEV_USERS", "asha1:dev:ASHA:1")
    from app.config import get_settings

    get_settings.cache_clear()

    resp = await client.post("/auth/login", json={"username": "asha1", "password": "wrong"})
    assert resp.status_code == 401

    get_settings.cache_clear()


async def test_login_rejects_unknown_user(client, monkeypatch):
    monkeypatch.setenv("DEV_USERS", "asha1:dev:ASHA:1")
    from app.config import get_settings

    get_settings.cache_clear()

    resp = await client.post("/auth/login", json={"username": "nobody", "password": "dev"})
    assert resp.status_code == 401

    get_settings.cache_clear()


def test_create_token_roundtrip():
    settings = _settings("asha1:dev:ASHA:1")
    user = auth_module._parse_dev_users(settings.dev_users)["asha1"]
    token = auth_module._create_token(user, settings, RealClock())

    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == "asha1"
    assert payload["role"] == "ASHA"
    assert payload["org_unit_id"] == "1"


def test_tampered_token_is_rejected():
    settings = _settings("asha1:dev:ASHA:1")
    user = auth_module._parse_dev_users(settings.dev_users)["asha1"]
    token = auth_module._create_token(user, settings, RealClock())

    other_settings = _settings("asha1:dev:ASHA:1")
    other_settings.jwt_secret = "a-different-secret-at-least-32-bytes!!"

    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(token, other_settings.jwt_secret, algorithms=[other_settings.jwt_algorithm])
