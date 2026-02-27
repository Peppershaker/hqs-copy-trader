"""System management routes (start, stop, status)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException

from app.engine.replication_engine import ReplicationEngine
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
        raise HTTPException(status_code=503, detail="Server not initialized")

    das = _get_das_service()
    engine = _get_engine()

    from sqlalchemy import select as sa_select

    from app.config import apply_env_text, get_config
    from app.database import get_session_factory
    from app.models.env_config import EnvConfig
    from app.models.follower import Follower
    from app.models.master import MasterConfig

    factory = get_session_factory()
    async with factory() as session:
        # Re-apply env config from DB
        env_result = await session.execute(sa_select(EnvConfig).where(EnvConfig.id == 1))
        env_row = env_result.scalar_one_or_none()
        if env_row and env_row.content.strip():
            apply_env_text(env_row.content)

        # Build broker_id → server config lookup from DAS_SERVERS
        das_server_map = {s.broker_id.lower(): s for s in get_config().parsed_das_servers}

        # Load master
        result = await session.execute(sa_select(MasterConfig).where(MasterConfig.id == 1))
        master = result.scalar_one_or_none()
        if not master:
            raise HTTPException(status_code=400, detail="Master account not configured")

        server = das_server_map.get(master.broker_id.lower())
        await das.configure_master(
            {
                "broker_id": master.broker_id,
                "host": server.host if server else master.host,
                "port": server.port if server else master.port,
                "username": server.username if server else master.username,
                "password": server.password if server else master.password,
                "account_id": master.account_id,
            }
        )

        # Load followers
        result = await session.execute(sa_select(Follower).where(Follower.enabled.is_(True)))
        follower_configs: dict[str, dict[str, Any]] = {}
        for f in result.scalars():
            fserver = das_server_map.get(f.broker_id.lower())
            await das.configure_follower(
                f.id,
                {
                    "broker_id": f.broker_id,
                    "host": fserver.host if fserver else f.host,
                    "port": fserver.port if fserver else f.port,
                    "username": fserver.username if fserver else f.username,
                    "password": fserver.password if fserver else f.password,
                    "account_id": f.account_id,
                },
            )
            follower_configs[f.id] = {
                "max_locate_price_delta": f.max_locate_price_delta,
                "locate_retry_timeout": f.locate_retry_timeout,
                "auto_accept_locates": f.auto_accept_locates,
            }

    try:
        await das.start()
        await engine.start(follower_configs=follower_configs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "started", **das.get_status()}


@router.post("/stop")
async def stop_system() -> dict[str, str]:
    """Stop all connections and the replication engine."""
    if _get_das_service is None or _get_engine is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    engine = _get_engine()
    das = _get_das_service()

    await engine.stop()
    await das.stop()

    return {"status": "stopped"}
