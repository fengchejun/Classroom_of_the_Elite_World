from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, gen_uuid


class TransactionLog(Base, TimestampMixin):
    __tablename__ = "transaction_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    char_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    char_role_id: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # negative = deduction
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    game_date: Mapped[str] = mapped_column(String(10), nullable=False)
