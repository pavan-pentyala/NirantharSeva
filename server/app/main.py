from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.api.referrals import router as referrals_router
from app.api.sync import router as sync_router
from app.clock import Clock, get_clock
from app.config import get_settings
from app.db import get_session
from app.instrumentation.logging import configure_logging
from app.instrumentation.timing import TimingMiddleware

configure_logging()
settings = get_settings()

app = FastAPI(title="NirantharSeva API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TimingMiddleware)

app.include_router(auth_router)
app.include_router(sync_router)
app.include_router(referrals_router)


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
