from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, gen_uuid


class Secret(Base, TimestampMixin):
    """A piece of hidden information about the world or a character."""

    __tablename__ = "secrets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    info_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # If this secret is about a specific character
    subject_char_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("characters.id"), default=None
    )

    # Whether this secret has become public knowledge
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    # Explicit list of who knows this secret (can extend beyond known_by relationships)
    known_by: Mapped[list[SecretKnowledge]] = relationship(
        "SecretKnowledge", back_populates="secret"
    )


class SecretKnowledge(Base, TimestampMixin):
    """Tracks which character knows which secret."""

    __tablename__ = "secret_knowledge"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    secret_id: Mapped[str] = mapped_column(String(64), ForeignKey("secrets.id"))
    character_id: Mapped[str] = mapped_column(String(64), ForeignKey("characters.id"))

    # How they learned it (narrative reference)
    unlocked_reason: Mapped[str | None] = mapped_column(Text, default=None)

    secret: Mapped[Secret] = relationship("Secret", back_populates="known_by")
    character: Mapped["Character"] = relationship(
        "Character", back_populates="secrets_known", foreign_keys=[character_id]
    )
