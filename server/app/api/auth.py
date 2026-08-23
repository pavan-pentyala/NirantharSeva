"""Auth against the real user table. See docs/decisions/ADR-006.md.

login and get_current_user resolve `sub` against app_user on every
request — no caching. After ADR-005, org membership is the confidentiality
boundary; a cached row would let a moved or disabled user keep their old
scope until the process restarts (docs/PHASE2_PLAN.md trap 11).

The JWT claim shape (`sub`, `role`, `org_unit_id`, `iat`, `exp`) is
unchanged from Phase 0. The claims are still set at login time to satisfy
that contract, but get_current_user never reads role/org_unit_id back off
the token — it re-resolves both from app_user on every request, because a
token is an up-to-8-hour-stale snapshot of a value that is now
security-relevant.

Expiry is checked against the injected Clock, not PyJWT's own internal
check. PyJWT's jwt.decode() validates both `exp` and `iat` against the
real system clock internally (it has no way to accept an injected one) —
under CLOCK_MODE=simulated this breaks in *both* directions as the
simulated clock moves through real "now": before it, a token's `exp`
(SimulatedClock-based, from `_create_token`) looks pre-expired to PyJWT's
real-time exp check; after it, the same token's `iat` looks like it was
issued in the future, and PyJWT raises ImmatureSignatureError instead.
Found by Phase 8's experiment harness (docs/PHASE8_PLAN.md, ADR-016) — the
first caller to combine CLOCK_MODE=simulated with a real login+push round
trip long enough for the simulated clock to cross real "now"; every
earlier phase's simulated-clock use (P5's sweep tests) never went through
auth at all, and the exp half alone was found and "fixed" first, only for
the iat half to surface as soon as a run went on long enough to cross the
line from the other side. A genuine, previously-latent bug, not a Phase 8
API change — CLOCK_MODE=real (production) is unaffected, since
RealClock.now() already agrees with PyJWT's own real-time checks on both.
"""

from datetime import timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, get_clock
from app.config import Settings, get_settings
from app.db import async_session_factory, get_session
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)


def _create_token(
    username: str, role: str, org_unit_id: UUID, settings: Settings, clock: Clock
) -> str:
    now = clock.now()
    payload = {
        "sub": username,
        "role": role,
        "org_unit_id": str(org_unit_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
) -> TokenResponse:
    result = await session.execute(
        text("SELECT role, org_unit_id, password_hash FROM app_user WHERE name = :name"),
        {"name": body.username},
    )
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    try:
        _hasher.verify(row.password_hash, body.password)
    except VerifyMismatchError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials") from exc

    token = _create_token(body.username, row.role, row.org_unit_id, settings, clock)
    return TokenResponse(access_token=token)


async def _resolve_user(token: str, settings: Settings, clock: Clock) -> CurrentUser:
    try:
        # verify_exp/verify_iat=False: PyJWT's own exp AND iat checks both
        # compare against the real system clock, which it has no way to
        # accept an injected Clock for — see module docstring. exp is
        # checked by hand, against clock.now(), immediately below.
        # iat has no equivalent manual check: this app never treats "issued
        # in the future" as meaningful on its own (exp already governs the
        # token's valid window), so it is simply not verified — PyJWT's
        # own iat check raised ImmatureSignatureError on real, working
        # tokens the moment a simulated clock's current value passed real
        # wall-clock "now" (P8.1's own first affected run — half of the
        # same bug the exp fix above addresses, found the same way).
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False, "verify_iat": False},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc

    if payload["exp"] < clock.now().timestamp():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired")

    username = payload["sub"]
    # A short-lived session, not the request-scoped Depends(get_session) —
    # this runs on every authenticated request (ADR-006's "third cost"), and
    # holding a connection open for the whole request instead of just this
    # one lookup starves the pool under concurrency (see
    # tests/integration/test_pull_cursor.py's 20-way concurrent push).
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT id, role, org_unit_id FROM app_user WHERE name = :name"),
            {"name": username},
        )
        row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")

    return CurrentUser(id=row.id, username=username, role=row.role, org_unit_id=row.org_unit_id)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return await _resolve_user(credentials.credentials, settings, clock)


async def get_current_user_from_query_token(
    token: str,
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
) -> CurrentUser:
    """GET /dashboard/stream only (docs/decisions/ADR-012.md) — EventSource
    cannot set an Authorization header, so this one route accepts the
    credential as a query parameter instead. Same validation as
    get_current_user — same signature check, same app_user re-resolution —
    only the transport differs; no other route wires this in, and
    get_current_user's own signature is untouched."""
    return await _resolve_user(token, settings, clock)
