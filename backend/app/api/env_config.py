"""Environment variable configuration routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import apply_env_text
from app.database import get_db
from app.models.env_config import EnvConfig

router = APIRouter(prefix="/api", tags=["env-config"])


class EnvConfigSave(BaseModel):
    content: str


class EnvConfigResponse(BaseModel):
    content: str
    updated_at: str | None = None
    parsed_keys: list[str] = []


@router.get("/env-config", response_model=EnvConfigResponse)
async def get_env_config(db: AsyncSession = Depends(get_db)) -> EnvConfigResponse:
    """Return the stored .env content."""
    result = await db.execute(select(EnvConfig).where(EnvConfig.id == 1))
    row = result.scalar_one_or_none()
    if not row:
        return EnvConfigResponse(content="", parsed_keys=[])
    return EnvConfigResponse(
        content=row.content,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        parsed_keys=_parse_keys(row.content),
    )


@router.put("/env-config", response_model=EnvConfigResponse)
async def save_env_config(
    body: EnvConfigSave, db: AsyncSession = Depends(get_db)
) -> EnvConfigResponse:
    """Persist .env content, apply all vars to the running process, and reload config."""
    result = await db.execute(select(EnvConfig).where(EnvConfig.id == 1))
    row = result.scalar_one_or_none()

    if row:
        row.content = body.content
    else:
        row = EnvConfig(id=1, content=body.content)
        db.add(row)

    await db.flush()
    await db.refresh(row)

    # Apply to running process
    parsed = apply_env_text(body.content)

    return EnvConfigResponse(
        content=row.content,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        parsed_keys=list(parsed.keys()),
    )


def _parse_keys(content: str) -> list[str]:
    """Return the list of variable names from the content (no values)."""
    import io

    from dotenv import dotenv_values

    return [k for k in dotenv_values(stream=io.StringIO(content)) if k]
