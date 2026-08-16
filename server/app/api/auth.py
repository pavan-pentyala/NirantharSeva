"""Auth stub for Phase 0.

Real JWT + argon2id plumbing against a config-defined user list. There is no
user table yet — it arrives with the Phase 2 schema (plan §6.4), and a
throwaway P0 table would only have to be migrated away. See PROGRESS.md
"Decisions taken by Claude Code without asking".
"""

from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.clock import Clock, get_clock
from app.config import Settings, get_settings
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class DevUser:
    username: str
    password_hash: str
    role: str
    org_unit_id: str


def _parse_dev_users(raw: str) -> dict[str, DevUser]:
    users: dict[str, DevUser] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        username, password, role, org_unit_id = entry.split(":")
        users[username] = DevUser(
            username=username,
            password_hash=_hasher.hash(password),
            role=role,
            org_unit_id=org_unit_id,
        )
    return users


@lru_cache
def _dev_user_store() -> dict[str, DevUser]:
    return _parse_dev_users(get_settings().dev_users)


def _create_token(user: DevUser, settings: Settings, clock: Clock) -> str:
    now = clock.now()
    payload = {
        "sub": user.username,
        "role": user.role,
        "org_unit_id": user.org_unit_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
) -> TokenResponse:
    user = _dev_user_store().get(body.username)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    try:
        _hasher.verify(user.password_hash, body.password)
    except VerifyMismatchError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials") from exc

    token = _create_token(user, settings, clock)
    return TokenResponse(access_token=token)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc

    return CurrentUser(
        username=payload["sub"],
        role=payload["role"],
        org_unit_id=payload["org_unit_id"],
    )
