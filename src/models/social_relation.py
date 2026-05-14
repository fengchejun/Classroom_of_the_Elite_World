from __future__ import annotations

import enum

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, gen_uuid


class RelationType(str, enum.Enum):
    TRUST = "trust"
    HOSTILE = "hostile"
    SUBSERVIENT = "subservient"


class SocialRelation(Base, TimestampMixin):
    __tablename__ = "social_relations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    src_char_id: Mapped[str] = mapped_column(String(64), ForeignKey("characters.id"))
    dst_char_id: Mapped[str] = mapped_column(String(64), ForeignKey("characters.id"))
    relation_type: Mapped[RelationType] = mapped_column(
        Enum(RelationType, name="relation_type_enum", native_enum=False), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, default=None)

    from_char: Mapped["Character"] = relationship(
        "Character", back_populates="relations_from", foreign_keys=[src_char_id]
    )
    to_char: Mapped["Character"] = relationship(
        "Character", back_populates="relations_to", foreign_keys=[dst_char_id]
    )
