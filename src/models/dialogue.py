from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, gen_uuid


class DialogueLog(Base, TimestampMixin):
    __tablename__ = "dialogue_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("game_sessions.id"), index=True
    )
    sequence_num: Mapped[int] = mapped_column(Integer, nullable=False)

    # Content
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    llm_response: Mapped[str] = mapped_column(Text, nullable=False)

    # Structured LLM response data (state changes, etc.)
    response_data: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Metadata
    event_id: Mapped[str | None] = mapped_column(String(64), default=None)
    choice_id: Mapped[str | None] = mapped_column(String(64), default=None)
    location_at_time: Mapped[str | None] = mapped_column(String(128), default=None)


class StorySummary(Base, TimestampMixin):
    """Compressed summaries of dialogue blocks (every 10 dialogues)."""

    __tablename__ = "story_summaries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("game_sessions.id"), index=True
    )

    # Range covered
    dialogue_start_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    dialogue_end_seq: Mapped[int] = mapped_column(Integer, nullable=False)

    summary_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Whether this summary has been incorporated into later summaries
    is_consolidated: Mapped[bool] = mapped_column(Boolean, default=False)
