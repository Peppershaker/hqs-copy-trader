"""Environment variable configuration routes."""

from __future__ import annotations

import json
from typing import NotRequired, TypedDict, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DasServerConfig, apply_env_text, parse_env_text
from app.database import get_db
from app.models.env_config import EnvConfig


class _DasServerRaw(TypedDict):
    broker_id: str
    host: str
    port: int
    username: str
    password: str
    accounts: list[str]
    smart_routes: NotRequired[list[str]]
    locate_routes: dict[str, int]


router = APIRouter(prefix="/api", tags=["env-config"])


class EnvConfigSave(BaseModel):
    """Request body for saving .env content."""

    content: str


class EnvConfigResponse(BaseModel):
    """Response body containing .env content and metadata."""

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
        parsed_keys=list(parse_env_text(row.content).keys()),
    )


@router.put("/env-config", response_model=EnvConfigResponse)
async def save_env_config(
    body: EnvConfigSave, db: AsyncSession = Depends(get_db)
) -> EnvConfigResponse:
    """Validate, persist .env content, and apply all vars to the running process."""
    _validate_env_content(body.content)

    result = await db.execute(select(EnvConfig).where(EnvConfig.id == 1))
    row = result.scalar_one_or_none()

    if row:
        row.content = body.content
    else:
        row = EnvConfig(id=1, content=body.content)
        db.add(row)

    await db.flush()
    await db.refresh(row)

    parsed = apply_env_text(body.content)

    return EnvConfigResponse(
        content=row.content,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        parsed_keys=list(parsed.keys()),
    )


def _validate_env_content(content: str) -> None:
    """Validate .env content. Raises HTTPException(400) on errors."""
    try:
        parsed = parse_env_text(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid .env syntax: {e}")

    das_servers_raw = parsed.get("DAS_SERVERS")
    if das_servers_raw is None:
        return

    try:
        servers = json.loads(das_servers_raw)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400, detail=f"DAS_SERVERS is not valid JSON: {e}"
        )

    if not isinstance(servers, list):
        raise HTTPException(status_code=400, detail="DAS_SERVERS must be a JSON array")

    entries = cast(list[_DasServerRaw], servers)
    for i, entry in enumerate(entries):
        try:
            DasServerConfig(**entry)
        except (ValidationError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"DAS_SERVERS[{i}]: {e}")
