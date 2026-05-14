from __future__ import annotations

from sqlalchemy import Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, gen_uuid


class GameSession(Base, TimestampMixin):
    __tablename__ = "game_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    session_slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Time state
    game_date: Mapped[str] = mapped_column(String(10), nullable=False, default="2024-04-01")
    time_slot: Mapped[str] = mapped_column(String(24), nullable=False, default="morning")

    # Player state
    player_name: Mapped[str] = mapped_column(String(128), default="玩家")
    player_char_id: Mapped[str | None] = mapped_column(String(64), default=None)
    player_location_id: Mapped[str] = mapped_column(String(128), default="classroom_d")

    # Player stats
    class_points: Mapped[int] = mapped_column(Integer, default=0)
    private_points: Mapped[int] = mapped_column(Integer, default=100000)
    player_stats: Mapped[dict] = mapped_column(JSON, default=dict)

    # Dialogue tracking
    dialogue_count_since_summary: Mapped[int] = mapped_column(Integer, default=0)

    # Global zone override (e.g. during island exam)
    zone_override: Mapped[str | None] = mapped_column(String(128), default=None)

    # Active flag
    is_active: Mapped[bool] = mapped_column(default=True)
