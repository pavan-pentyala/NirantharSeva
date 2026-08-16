from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentUser, get_current_user
from app.clock import Clock, get_clock
from app.config import Settings, get_settings
from app.db import async_session_factory, get_session
from app.schemas.sync import PullResponse, PushRequest, PushResponse
from app.sync.pull import handle_pull
from app.sync.push import handle_push

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/push", response_model=PushResponse)
async def push(
    body: PushRequest,
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
    _user: CurrentUser = Depends(get_current_user),
) -> PushResponse:
    results, server_lamport = await handle_push(
        async_session_factory, body.device_id, body.ops, clock, settings.run_id
    )
    return PushResponse(results=results, server_lamport=server_lamport)


@router.get("/pull", response_model=PullResponse)
async def pull(
    since: int = 0,
    limit: int = 500,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> PullResponse:
    return await handle_pull(session, since, limit)
