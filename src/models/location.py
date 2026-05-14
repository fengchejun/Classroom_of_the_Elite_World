from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, gen_uuid


class Location(Base, TimestampMixin):
    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    location_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Parent zone (e.g. "island_zone" for "beach", "forest")
    zone_id: Mapped[str | None] = mapped_column(String(128), default=None)

    # Connected location IDs for navigation
    connected_to: Mapped[dict] = mapped_column(JSON, default=list)

    # Ambient tags for LLM atmosphere: ["indoor", "noisy", "dark"]
    tags: Mapped[dict] = mapped_column(JSON, default=list)
