"""Follower account configuration model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Follower(Base):
    """Configuration for a follower DAS account."""

    __tablename__ = "followers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    broker_id: Mapped[str] = mapped_column(String, nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    account_id: Mapped[str] = mapped_column(String, nullable=False)
    base_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    locate_retry_timeout: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300
    )
    auto_accept_locates: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    max_locate_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    locate_routes: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
