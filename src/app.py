from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: init DB pool, Redis, etc.
    from src.utils.database import engine

    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title="实教AI模拟器",
    description="《实力至上主义的教室》混合驱动AI互动引擎",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
from src.api.routes.game import router as game_router
from src.api.routes.character import router as character_router
from src.api.routes.admin import router as admin_router

app.include_router(game_router)
app.include_router(character_router)
app.include_router(admin_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
