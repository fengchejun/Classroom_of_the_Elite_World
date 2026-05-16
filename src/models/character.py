from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, gen_uuid

if TYPE_CHECKING:
    from src.models.secret import SecretKnowledge
    from src.models.social_relation import SocialRelation


class Character(Base, TimestampMixin):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    role_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # Location
    current_location_id: Mapped[str | None] = mapped_column(String(128), default=None)

    # Status tags: ["normal", "injured", "absent", ...]
    status_tags: Mapped[dict] = mapped_column(JSON, default=list)

    # Multi-layer persona
    public_info: Mapped[dict] = mapped_column(JSON, default=list)
    # Public info items, each item: {"label": "外貌", "content": "..."}

    # Behaviour weights: {time_slot: {location_id: probability}}
    # e.g. {"noon": {"classroom": 0.7, "cafeteria": 0.3}}
    schedule_weights: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Class: "A" | "B" | "C" | "D"
    class_name: Mapped[str | None] = mapped_column(String(8), default=None)

    # Personal points (in-game currency)
    private_points: Mapped[int] = mapped_column(Integer, default=100000)

    # Spending behavior: "frugal" | "socialite" | "gamer/otaku" | "normal"
    spending_habit: Mapped[str | None] = mapped_column(String(32), default="normal")

    # Relationships
    secrets_known: Mapped[list[SecretKnowledge]] = relationship(
        "SecretKnowledge", back_populates="character", foreign_keys="SecretKnowledge.character_id"
    )
    relations_from: Mapped[list[SocialRelation]] = relationship(
        "SocialRelation",
        back_populates="from_char",
        foreign_keys="SocialRelation.src_char_id",
    )
    relations_to: Mapped[list[SocialRelation]] = relationship(
        "SocialRelation",
        back_populates="to_char",
        foreign_keys="SocialRelation.dst_char_id",
    )
