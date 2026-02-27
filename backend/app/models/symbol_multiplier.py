"""Per-symbol multiplier override model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SymbolMultiplier(Base):
    """Per-follower, per-symbol multiplier override."""

    __tablename__ = "symbol_multipliers"
    __table_args__ = (UniqueConstraint("follower_id", "symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    follower_id: Mapped[str] = mapped_column(
        String, ForeignKey("followers.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(
        String, nullable=False
    )  # 'auto_inferred' | 'user_override'
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
