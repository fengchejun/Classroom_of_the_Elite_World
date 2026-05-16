from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, gen_uuid


class EventType(str, enum.Enum):
    AI_GUIDED_CHOICE = "ai_guided_choice"
    SILENT_FIXED = "silent_fixed"
    FIXED_STORY = "fixed_story"


class EventPhase(str, enum.Enum):
    PENDING = "pending"
    FORESHADOWING = "foreshadowing"
    TRANSITION = "transition"
    ACTIVE = "active"
    EXPIRED = "expired"


class Event(Base, TimestampMixin):
    """A live event instance in the game world."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    template_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="event_type_enum", native_enum=False), nullable=False
    )

    # Trigger conditions
    required_date: Mapped[str | None] = mapped_column(String(10), default=None)
    required_time_slot: Mapped[str | None] = mapped_column(String(24), default=None)
    required_location: Mapped[str | None] = mapped_column(String(128), default=None)
    required_player_char: Mapped[str | None] = mapped_column(String(64), default=None)
    prerequisite_events: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Phase tracking
    phase: Mapped[EventPhase] = mapped_column(
        Enum(EventPhase, name="event_phase_enum", native_enum=False),
        default=EventPhase.PENDING,
    )
    foreshadow_start_date: Mapped[str | None] = mapped_column(String(10), default=None)
    transition_date: Mapped[str | None] = mapped_column(String(10), default=None)
    active_start_date: Mapped[str | None] = mapped_column(String(10), default=None)
    active_end_date: Mapped[str | None] = mapped_column(String(10), default=None)

    # Foreshadowing
    foreshadow_probability: Mapped[float] = mapped_column(Float, default=0.3)
    foreshadow_prompt: Mapped[str | None] = mapped_column(Text, default=None)

    # Content
    ai_setup_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    active_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    options: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Rulebook appendix (exam rules)
    rules_appendix: Mapped[str | None] = mapped_column(Text, default=None)

    # Silent fixed effects
    silent_effects: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Whether this event is currently active
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class DynamicEvent(Base, TimestampMixin):
    """AI-generated event sitting in the dynamic pool."""

    __tablename__ = "dynamic_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="dynamic_event_type_enum", native_enum=False),
        default=EventType.AI_GUIDED_CHOICE,
    )

    # Trigger
    trigger_location: Mapped[str | None] = mapped_column(String(128), default=None)
    trigger_date_start: Mapped[str | None] = mapped_column(String(10), default=None)
    trigger_date_end: Mapped[str | None] = mapped_column(String(10), default=None)

    # Content
    ai_setup_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    options: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Expiry
    expires_at: Mapped[str | None] = mapped_column(String(10), default=None)
    is_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False)
