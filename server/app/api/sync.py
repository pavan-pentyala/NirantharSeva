from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentUser, get_current_user
from app.clock import Clock, get_clock
from app.config import Settings, get_settings
from app.db import async_session_factory, get_session
from app.domain.actor import Actor
from app.domain.states import Role
from app.schemas.sync import PullResponse, PushRequest, PushResponse
from app.sync.pull import handle_pull
from app.sync.push import handle_push

router = APIRouter(prefix="/sync", tags=["sync"])


def _actor_from(user: CurrentUser) -> Actor:
    return Actor(user_id=user.id, role=Role(user.role), org_unit_id=user.org_unit_id)


@router.post("/push", response_model=PushResponse)
async def push(
    body: PushRequest,
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
) -> PushResponse:
    # Who is acting (I4, D6/ADR-006) comes from the server-verified,
    # DB-backed identity, never from anything in the op payload — a device
    # cannot be trusted to name its own role, org, or user.
    results, server_lamport = await handle_push(
        async_session_factory,
        body.device_id,
        body.ops,
        clock,
        settings.run_id,
        _actor_from(user),
    )
    return PushResponse(results=results, server_lamport=server_lamport)


@router.get("/pull", response_model=PullResponse)
async def pull(
    since: int = 0,
    limit: int = 500,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    # D7/ADR-005: scoped to the caller's org subtree inside handle_pull.
    return await handle_pull(session, since, limit, user.org_unit_id)
