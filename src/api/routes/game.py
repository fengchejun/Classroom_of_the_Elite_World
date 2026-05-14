from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.services.game_service import GameService
from src.utils.logger import get_logger

router = APIRouter(prefix="/api/game", tags=["game"])
logger = get_logger(__name__)


class PlayerInputRequest(BaseModel):
    session_slug: str
    user_input: str
    choice_id: str | None = None
    trigger_event: str | None = None


class GameStateResponse(BaseModel):
    session_slug: str
    player_state: dict
    time_display: str
    location: dict


@router.post("/input")
async def handle_input(
    req: PlayerInputRequest,
    db: AsyncSession = Depends(get_db),
):
    """Main game input endpoint. Player types something or clicks a choice."""
    service = GameService(db)
    try:
        response = await service.handle_player_input(
            session_slug=req.session_slug,
            user_input=req.user_input,
            choice_id=req.choice_id,
            trigger_event=req.trigger_event,
        )
        return response
    except Exception as e:
        logger.error(f"Game input error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/state/{session_slug}")
async def get_game_state(
    session_slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Get current game state for a session."""
    from sqlalchemy import select
    from src.models import GameSession

    result = await db.execute(
        select(GameSession).where(GameSession.session_slug == session_slug)
    )
    sess = result.scalar_one_or_none()
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return GameStateResponse(
        session_slug=sess.session_slug,
        player_state={
            "location_id": sess.player_location_id,
            "class_points": sess.class_points,
            "private_points": sess.private_points,
        },
        time_display=f"{sess.game_date} {sess.time_slot}",
        location={"location_id": sess.player_location_id},
    )


@router.post("/session/create")
async def create_session(
    db: AsyncSession = Depends(get_db),
    slug: str = "default",
):
    """Create a new game session."""
    from src.models import GameSession

    session = GameSession(session_slug=slug)
    db.add(session)
    await db.flush()
    return {"session_slug": session.session_slug, "status": "created"}
