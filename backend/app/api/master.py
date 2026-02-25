"""Master account configuration routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.master import MasterConfig
from app.schemas.accounts import MasterConfigCreate, MasterConfigResponse

router = APIRouter(prefix="/api/master", tags=["master"])


@router.get("", response_model=MasterConfigResponse | None)
async def get_master(db: AsyncSession = Depends(get_db)):
    """Get the current master account configuration."""
    result = await db.execute(select(MasterConfig).where(MasterConfig.id == 1))
    master = result.scalar_one_or_none()
    if not master:
        return None
    return master


@router.put("", response_model=MasterConfigResponse)
async def update_master(
    config: MasterConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create or update the master account configuration."""
    result = await db.execute(select(MasterConfig).where(MasterConfig.id == 1))
    master = result.scalar_one_or_none()

    if master:
        for field, value in config.model_dump().items():
            setattr(master, field, value)
    else:
        master = MasterConfig(id=1, **config.model_dump())
        db.add(master)

    await db.flush()
    await db.refresh(master)
    return master
