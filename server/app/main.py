from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.identity import router as identity_router
from app.api.org_units import router as org_units_router
from app.api.referrals import router as referrals_router
from app.api.sync import router as sync_router
from app.clock import Clock, get_clock
from app.config import get_settings
from app.db import get_session
from app.instrumentation.logging import configure_logging
from app.instrumentation.timing import TimingMiddleware
from app.realtime import start_listening, stop_listening

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ADR-011: one LISTEN connection for the API process's lifetime, held
    # outside SQLAlchemy's pool, not opened per-request.
    await start_listening()
    yield
    await stop_listening()


app = FastAPI(title="NirantharSeva API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_origins == "*" else settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TimingMiddleware)

app.include_router(auth_router)
app.include_router(sync_router)
app.include_router(referrals_router)
app.include_router(org_units_router)
app.include_router(dashboard_router)
app.include_router(identity_router)


@app.get("/health")
async def health(
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> dict:
    await session.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "clock_mode": settings.clock_mode,
        "server_time": clock.now().isoformat(),
        "run_id": settings.run_id,
    }
