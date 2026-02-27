"""Reconciliation routes for the two-phase start flow.

After DAS clients are connected (POST /api/connect), these endpoints let
the frontend compare master vs follower positions and apply multiplier /
blacklist decisions before replication begins.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select as sa_select

from app.database import get_session_factory
from app.engine.replication_engine import ReplicationEngine
from app.models.follower import Follower
from app.schemas.reconcile import (
    ReconcileApplyRequest,
    ReconcileFollowerData,
    ReconcilePositionEntry,
    ReconcileResponse,
)
from app.services.das_service import DASService

router = APIRouter(prefix="/api/reconcile", tags=["reconcile"])
logger = logging.getLogger(__name__)

# Injected at startup
_get_das_service: Callable[[], DASService] | None = None
_get_engine: Callable[[], ReplicationEngine] | None = None
_get_follower_configs: Callable[[], dict[str, dict[str, Any]]] | None = None


def set_service_getters(
    das_getter: Callable[[], DASService],
    engine_getter: Callable[[], ReplicationEngine],
    follower_configs_getter: Callable[[], dict[str, dict[str, Any]]],
) -> None:
    """Inject dependency getters used by reconcile endpoints."""
    global _get_das_service, _get_engine, _get_follower_configs
    _get_das_service = das_getter
    _get_engine = engine_getter
    _get_follower_configs = follower_configs_getter


async def _load_follower_names() -> dict[str, str]:
    """Load follower_id → name mapping from the database."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(sa_select(Follower.id, Follower.name))
        return {row.id: row.name for row in result}


def _classify_position(
    master_qty: int,
    master_side: str,
    follower_qty: int,
    follower_side: str | None,
) -> tuple[str, float | None]:
    """Determine scenario and inferred multiplier for a symbol.

    Returns (scenario, inferred_multiplier).
    """
    if follower_qty == 0 or follower_side is None:
        return "master_only", None

    same_dir = (
        (master_side == follower_side)
        or (master_qty > 0 and follower_qty > 0)
        or (master_qty < 0 and follower_qty < 0)
    )

    if same_dir:
        inferred = round(abs(follower_qty) / abs(master_qty), 4)
        return "common_same_dir", inferred

    return "common_diff_dir", None


@router.get("", response_model=ReconcileResponse)
async def get_reconciliation(
    follower_ids: str | None = Query(
        default=None,
        description="Comma-separated follower IDs to reconcile. "
        "Omit to reconcile all connected followers.",
    ),
) -> ReconcileResponse:
    """Compare master vs follower positions for reconciliation.

    Requires DAS clients to be connected (POST /api/connect).
    """
    if _get_das_service is None or _get_engine is None:
        raise HTTPException(503, "Server not initialized")

    das = _get_das_service()
    engine = _get_engine()

    if not das.is_running:
        raise HTTPException(
            409, "DAS clients not connected. Call POST /api/connect first."
        )

    master = das.master_client
    if not master or not master.is_running:
        return ReconcileResponse(followers=[], has_entries=False)

    # Build master position map
    master_positions = {pos.symbol: pos for pos in master.positions}
    if not master_positions:
        return ReconcileResponse(followers=[], has_entries=False)

    # Parse follower filter
    filter_ids: set[str] | None = None
    if follower_ids:
        filter_ids = {fid.strip() for fid in follower_ids.split(",")}

    # Load follower names for display
    follower_names = await _load_follower_names()

    multiplier_mgr = engine.multiplier_manager
    blacklist_mgr = engine.blacklist_manager

    followers_data: list[ReconcileFollowerData] = []

    for fid, client in das.follower_clients.items():
        if filter_ids and fid not in filter_ids:
            continue
        if not client.is_running:
            continue

        follower_positions = {pos.symbol: pos for pos in client.positions}

        entries: list[ReconcilePositionEntry] = []
        for symbol in sorted(master_positions):
            m_pos = master_positions[symbol]
            f_pos = follower_positions.get(symbol)

            m_qty = m_pos.quantity
            m_side = m_pos.position_type.name
            f_qty = f_pos.quantity if f_pos else 0
            f_side = f_pos.position_type.name if f_pos else None

            scenario, inferred = _classify_position(m_qty, m_side, f_qty, f_side)

            default_action = (
                "use_inferred" if scenario == "common_same_dir" else "blacklist"
            )

            entries.append(
                ReconcilePositionEntry(
                    symbol=symbol,
                    master_qty=m_qty,
                    master_side=m_side,
                    follower_qty=f_qty,
                    follower_side=f_side,
                    scenario=scenario,
                    inferred_multiplier=inferred,
                    current_multiplier=multiplier_mgr.get_effective(fid, symbol),
                    current_source=multiplier_mgr.get_source(fid, symbol),
                    is_blacklisted=blacklist_mgr.is_blacklisted(fid, symbol),
                    default_action=default_action,
                )
            )

        if entries:
            followers_data.append(
                ReconcileFollowerData(
                    follower_id=fid,
                    follower_name=follower_names.get(fid, fid),
                    base_multiplier=multiplier_mgr.get_effective(fid, ""),
                    entries=entries,
                )
            )

    return ReconcileResponse(
        followers=followers_data,
        has_entries=any(f.entries for f in followers_data),
    )


@router.post("/apply")
async def apply_reconciliation(
    body: ReconcileApplyRequest,
) -> dict[str, Any]:
    """Apply reconciliation decisions and start replication.

    For each follower + symbol decision:
    - ``use_inferred`` / ``manual``: set a ``user_override`` multiplier
    - ``use_default``: remove any existing symbol override
    - ``blacklist=true``: add to blacklist
    - ``blacklist=false``: remove from blacklist

    After applying all decisions, starts the replication engine.
    """
    if _get_engine is None or _get_follower_configs is None:
        raise HTTPException(503, "Server not initialized")

    engine = _get_engine()
    if engine.is_running:
        raise HTTPException(409, "Replication already active")

    multiplier_mgr = engine.multiplier_manager
    blacklist_mgr = engine.blacklist_manager

    stats = {
        "multiplier_overrides_set": 0,
        "multiplier_overrides_removed": 0,
        "blacklist_added": 0,
        "blacklist_removed": 0,
    }

    for follower in body.followers:
        fid = follower.follower_id
        for decision in follower.decisions:
            symbol = decision.symbol.upper()

            # Multiplier action
            if decision.action in ("use_inferred", "manual"):
                if decision.multiplier is None:
                    raise HTTPException(
                        422,
                        f"multiplier required for action "
                        f"'{decision.action}' on {symbol}",
                    )
                await multiplier_mgr.set_symbol_override(
                    fid, symbol, decision.multiplier, source="user_override"
                )
                stats["multiplier_overrides_set"] += 1
            elif decision.action == "use_default":
                await multiplier_mgr.remove_symbol_override(fid, symbol)
                stats["multiplier_overrides_removed"] += 1

            # Blacklist action
            if decision.blacklist:
                added = await blacklist_mgr.add(fid, symbol, reason="reconciliation")
                if added:
                    stats["blacklist_added"] += 1
            else:
                removed = await blacklist_mgr.remove(fid, symbol)
                if removed:
                    stats["blacklist_removed"] += 1

    # Start replication engine
    follower_configs = _get_follower_configs()
    await engine.start(
        follower_configs=follower_configs,
        load_persistent_state=False,
    )

    logger.info("Reconciliation applied: %s", stats)
    return {"applied": stats, "replication_started": True}
