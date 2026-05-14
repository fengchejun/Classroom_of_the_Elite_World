from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.core.persona_graph.character import CharacterManager

router = APIRouter(prefix="/api/characters", tags=["characters"])


@router.get("/{role_id}")
async def get_character(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    observer_id: str = "player",
):
    """Get character info from the observer's perspective (respects secret locks)."""
    mgr = CharacterManager(db)
    char = await mgr.get_character(role_id, observer_id)
    if char is None:
        raise HTTPException(status_code=404, detail="Character not found")
    return char


@router.get("/")
async def list_characters(
    db: AsyncSession = Depends(get_db),
):
    """Get brief list of all characters."""
    mgr = CharacterManager(db)
    return await mgr.get_all_characters_brief()
