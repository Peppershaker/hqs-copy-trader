"""System management routes (start, stop, status, audit log)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.replication_engine import ReplicationEngine
from app.models.audit_log import AuditLog
from app.services.das_service import DASService

router = APIRouter(prefix="/api", tags=["system"])

# Injected at startup
_get_das_service: Callable[[], DASService] | None = None
_get_engine: Callable[[], ReplicationEngine] | None = None


def set_service_getters(
    das_getter: Callable[[], DASService],
    engine_getter: Callable[[], ReplicationEngine],
) -> None:
    global _get_das_service, _get_engine
    _get_das_service = das_getter
    _get_engine = engine_getter


@router.get("/das-servers")
async def get_das_servers() -> list[dict[str, Any]]:
    """Return the list of DAS-bridge server configurations from DAS_SERVERS env var."""
    from app.config import get_config

    config = get_config()
    return [s.model_dump() for s in config.parsed_das_servers]


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Get system health and connection state."""
    if _get_das_service is None:
        return {"running": False, "error": "Not initialized"}
    das = _get_das_service()
    return das.get_status()


@router.get("/health")
async def get_health() -> dict[str, Any]:
    """Get detailed health diagnostics for all accounts.

    Returns per-account server status (API, Order, Quote), heartbeat health,
    manager run-states, and key metrics (orders, trades, positions, uptime).
    """
    if _get_das_service is None:
        return {"running": False, "error": "Not initialized"}

    das = _get_das_service()
    result: dict[str, Any] = {
        "running": das.is_running,
        "master": None,
        "followers": {},
    }

    master = das.master_client
    if master:
        try:
            result["master"] = {
                "health": master.get_health_status(),
                "metrics": master.get_metrics(),
            }
        except Exception as e:
            result["master"] = {"error": str(e)}

    for fid, client in das.follower_clients.items():
        try:
            result["followers"][fid] = {
                "health": client.get_health_status(),
                "metrics": client.get_metrics(),
            }
        except Exception as e:
            result["followers"][fid] = {"error": str(e)}

    return result


@router.post("/start")
async def start_system() -> dict[str, Any]:
    """Start all DAS connections and the replication engine."""
    if _get_das_service is None or _get_engine is None:
        return {"error": "Not initialized"}

    das = _get_das_service()
    engine = _get_engine()

    # Load configs from DB
    from sqlalchemy import select as sa_select

    from app.database import get_session_factory
    from app.models.follower import Follower
    from app.models.master import MasterConfig

    factory = get_session_factory()
    async with factory() as session:
        # Load master
        result = await session.execute(sa_select(MasterConfig).where(MasterConfig.id == 1))
        master = result.scalar_one_or_none()
        if not master:
            return {"error": "Master account not configured"}

        await das.configure_master(
            {
                "broker_id": master.broker_id,
                "host": master.host,
                "port": master.port,
                "username": master.username,
                "password": master.password,
                "account_id": master.account_id,
            }
        )

        # Load followers
        result = await session.execute(sa_select(Follower).where(Follower.enabled.is_(True)))
        follower_configs: dict[str, dict[str, Any]] = {}
        for f in result.scalars():
            await das.configure_follower(
                f.id,
                {
                    "broker_id": f.broker_id,
                    "host": f.host,
                    "port": f.port,
                    "username": f.username,
                    "password": f.password,
                    "account_id": f.account_id,
                },
            )
            follower_configs[f.id] = {
                "max_locate_price_delta": f.max_locate_price_delta,
                "locate_retry_timeout": f.locate_retry_timeout,
                "auto_accept_locates": f.auto_accept_locates,
            }

    await das.start()
    await engine.start(follower_configs=follower_configs)

    return {"status": "started", **das.get_status()}


@router.post("/stop")
async def stop_system() -> dict[str, str]:
    """Stop all connections and the replication engine."""
    if _get_das_service is None or _get_engine is None:
        return {"error": "Not initialized"}

    engine = _get_engine()
    das = _get_das_service()

    await engine.stop()
    await das.stop()

    return {"status": "stopped"}


@router.get("/audit-log")
async def get_audit_log(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    category: str | None = Query(None),
    level: str | None = Query(None),
    follower_id: str | None = Query(None),
    symbol: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve paginated audit log entries."""
    query = select(AuditLog).order_by(desc(AuditLog.timestamp))

    if category:
        query = query.where(AuditLog.category == category)
    if level:
        query = query.where(AuditLog.level == level)
    if follower_id:
        query = query.where(AuditLog.follower_id == follower_id)
    if symbol:
        query = query.where(AuditLog.symbol == symbol.upper())

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    entries = result.scalars().all()

    return {
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "level": e.level,
                "category": e.category,
                "follower_id": e.follower_id,
                "symbol": e.symbol,
                "message": e.message,
                "details": e.details,
            }
            for e in entries
        ],
        "limit": limit,
        "offset": offset,
    }
