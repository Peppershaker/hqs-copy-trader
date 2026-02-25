"""Order replication mapping model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OrderMap(Base):
    """Maps a master order to its corresponding follower order."""

    __tablename__ = "order_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    master_order_token: Mapped[int] = mapped_column(Integer, nullable=False)
    master_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    follower_id: Mapped[str] = mapped_column(String, ForeignKey("followers.id"), nullable=False)
    follower_order_token: Mapped[int] = mapped_column(Integer, nullable=False)
    follower_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
