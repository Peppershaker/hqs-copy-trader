"""Per-follower, per-symbol blacklist model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BlacklistEntry(Base):
    """Blacklisted ticker for a specific follower account."""

    __tablename__ = "blacklist"
    __table_args__ = (UniqueConstraint("follower_id", "symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    follower_id: Mapped[str] = mapped_column(
        String, ForeignKey("followers.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
