"""Locate replication tracking model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LocateMap(Base):
    """Tracks replication of short locates from master to a follower."""

    __tablename__ = "locate_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    master_locate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    follower_id: Mapped[str] = mapped_column(
        String, ForeignKey("followers.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    master_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    target_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    master_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    follower_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="scanning")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
