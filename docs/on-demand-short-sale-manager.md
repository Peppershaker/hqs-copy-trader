# On-Demand Short Sale Manager

## Context

Currently, the replication engine treats locate events and short sale orders as independent streams. When the master locates shares and then shorts, both events fire independently to followers. This creates a race condition: the follower's short sale order can be rejected because their locate hasn't been accepted yet.

The new design eliminates proactive locate replication entirely. Instead, when a master short sale order is detected, we check the follower's current selling capacity via `get_max_sell()`. If there's a deficit, we auto-locate exactly the needed shares via `smart_locate()`, then place the order. This is more cost-efficient (only borrow what's needed), naturally solves the dependency problem, and simplifies the architecture.

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/engine/short_sale_manager.py` | **New file** — core `ShortSaleManager` class |
| `backend/app/engine/replication_engine.py` | Wire in ShortSaleManager, remove locate subscription, add `is_short` branching |
| `backend/app/engine/action_queue.py` | Remove `LOCATE` from `QueuedActionType` |
| `backend/app/models/follower.py` | Add `max_locate_price` column (absolute $/share ceiling) |
| `backend/app/api/system.py` | Pass `max_locate_price` in `follower_configs` |
| `backend/app/api/short_sales.py` | **New file** — API endpoints for viewing/cancelling tasks |
| `backend/app/main.py` | Register new `short_sales` router, inject engine getter |

## Implementation Steps

### Step 1: Add `max_locate_price` to Follower model

**File:** `backend/app/models/follower.py`

Add a new column after `auto_accept_locates`:
```python
max_locate_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)
```

This is the absolute max $/share the user will pay for auto-locates. Replaces the delta-based `max_locate_price_delta` (which required a master reference price we no longer have). Leave `max_locate_price_delta` in place for backward compat.

**File:** `backend/app/api/system.py` (line 157-161)

Add `"max_locate_price": f.max_locate_price` to the `follower_configs` dict. Keep existing fields — `locate_retry_timeout` is reused as the `smart_locate` timeout.

### Step 2: Create `ShortSaleManager`

**New file:** `backend/app/engine/short_sale_manager.py`

**`ShortSaleTask` dataclass:**
- `id: str` — unique ID (e.g. `"sst-{counter}-{ts}"`)
- `follower_id: str`
- `symbol: str`
- `master_order_id: int`
- `required_qty: int` — scaled quantity needed
- `locate_deficit: int` — shares that need locating (0 if sufficient capacity)
- `status: str` — `"pending" | "checking" | "locating" | "placing_order" | "completed" | "failed" | "cancelled"`
- `error: str | None`
- `created_at: float`

**`ShortSaleManager` class:**

Constructor takes: `das_service`, `multiplier_mgr`, `blacklist_mgr`, `order_replicator`, `notifier`

Internal state:
- `_tasks: dict[str, ShortSaleTask]` — all active tasks
- `_task_futures: dict[str, asyncio.Task]` — running asyncio tasks
- `_global_semaphore: asyncio.Semaphore` — limits concurrent `smart_locate` calls (default 3)
- `_symbol_locks: dict[tuple[str, str], asyncio.Lock]` — per `(follower_id, symbol)` serialization
- `_cancelled_master_orders: set[int]` — master orders cancelled while tasks in-flight

**Key methods:**

`async def handle_short_sale(master_order, follower_id, master_order_id, follower_config)`:
1. Scale quantity via `multiplier_mgr.get_effective()`
2. Create `ShortSaleTask` in `"pending"` status
3. Broadcast `"short_sale_task_update"`
4. Start asyncio.Task running `_execute_task()`

`async def _execute_task(task, master_order, follower_config)`:
1. Acquire `_symbol_locks[(follower_id, symbol)]` (create if needed)
2. Check if `master_order_id in _cancelled_master_orders` → cancel if so
3. Status → `"checking"`, get follower client
4. Call `client.get_max_sell(symbol)` to check capacity
5. Compute `deficit = task.required_qty - max_sell`. If deficit <= 0 → skip to step 8
6. Status → `"locating"`, acquire `_global_semaphore`
7. Call `client.smart_locate(symbol, deficit, max_price_per_share=Decimal(config["max_locate_price"]), timeout=config["locate_retry_timeout"])`. Release semaphore.
   - If locate fails/times out → status `"failed"`, broadcast, return
8. Re-check cancellation
9. Status → `"placing_order"`
10. Call `order_replicator.replicate_order(master_order, follower_id, master_order_id)`
11. Status → `"completed"`, broadcast

Error handling: `CancelledError` → `"cancelled"`. Any other exception → `"failed"`. Always broadcast status update.

`async def on_master_order_cancelled(master_order_id)`:
- Add to `_cancelled_master_orders`
- Find and cancel all in-flight tasks matching that master_order_id

`async def cancel_task(task_id) -> bool`:
- User-initiated cancellation from UI/API

`def get_active_tasks() -> list[dict]`:
- Serialized list for UI state

`async def cancel_all()`:
- Shutdown: cancel all in-flight tasks

### Step 3: Modify `ReplicationEngine`

**File:** `backend/app/engine/replication_engine.py`

**`__init__`** — Add after `_locate_replicator` (line ~94):
```python
self._short_sale_mgr = ShortSaleManager(
    das_service, self._multiplier_mgr, self._blacklist_mgr,
    self._order_replicator, notifier,
)
```
Add import for `ShortSaleManager`. Add `short_sale_manager` property.

**`_subscribe_to_master`** — Remove lines 217-221 (the `LocateOrderUpdatedEvent` subscription). Remove unused import.

**`_on_master_order_accepted`** — Replace the direct `replicate_order` call (lines 311-313) with:
```python
if order.is_short:
    config = self._follower_configs.get(fid, {})
    await self._short_sale_mgr.handle_short_sale(
        master_order=order, follower_id=fid,
        master_order_id=master_order_id, follower_config=config,
    )
    results[fid] = None  # reported asynchronously
    continue

follower_oid = await self._order_replicator.replicate_order(...)
```

**`_on_master_order_cancelled`** — After line 384 (existing cancel call), add:
```python
await self._short_sale_mgr.on_master_order_cancelled(master_order_id)
```

**`_on_master_locate_updated`** — Delete the entire method (lines 454-524).

**`stop()`** — Add `await self._short_sale_mgr.cancel_all()` before/instead of `cancel_all_retries()`.

**`_build_full_state()`** — Add `"short_sale_tasks": self._short_sale_mgr.get_active_tasks()` to the returned dict.

**`_replay_single()`** — In the `ORDER_SUBMIT` branch (line 697-703), add short detection:
```python
if master_order.is_short:
    config = self._follower_configs.get(action.follower_id, {})
    await self._short_sale_mgr.handle_short_sale(
        master_order, action.follower_id, master_order_id, config,
    )
    return {"short_sale_task_started": True}
```
Remove the `LOCATE` branch (lines 748-758).

### Step 4: Clean up `ActionQueue`

**File:** `backend/app/engine/action_queue.py`

- Remove `LOCATE = "locate"` from `QueuedActionType` enum (line 23)
- Remove the LOCATE payload comment from `QueuedAction` (lines 41-42)

### Step 5: Create short sales API

**New file:** `backend/app/api/short_sales.py`

```python
router = APIRouter(prefix="/api/short-sales", tags=["short-sales"])
```

Endpoints:
- `GET /api/short-sales/tasks` — returns `engine.short_sale_manager.get_active_tasks()`
- `POST /api/short-sales/tasks/{task_id}/cancel` — calls `engine.short_sale_manager.cancel_task(task_id)`

Pattern follows `queue.py` with `set_engine_getter()` injection.

### Step 6: Register in `main.py`

**File:** `backend/app/main.py`

- Add `short_sales` to the import block (line 19-30)
- Add `short_sales.set_engine_getter(lambda: _engine)` in `lifespan()` (after line 97)
- Add `app.include_router(short_sales.router)` in `create_app()` (after line 147)

### Step 7: Cleanup

- Remove `LocateReplicator` instantiation from `ReplicationEngine.__init__` and the `locate_replicator` property (keep the file for potential future manual locate feature)
- Remove `cancel_all_retries()` call from `stop()`
- Remove unused imports (`LocateOrderUpdatedEvent`, `LocateReplicator`)
- Leave `locate_replicator.py`, `locate_map.py`, and `api/locates.py` files in place (historical data, future reuse)

## Concurrency Design

**Layer 1 — Per-(follower, symbol) `asyncio.Lock`:** When two shorts for the same symbol arrive rapidly, the second task waits for the first to complete, then re-checks `get_max_sell()` (which now reflects the first task's locate). Prevents double-locating.

**Layer 2 — Global `asyncio.Semaphore(N)`:** Limits total concurrent `smart_locate()` calls across all followers/symbols. Default N=3. Respects DAS API rate limits.

## Task Lifecycle
```
pending → checking → locating → placing_order → completed
              │           │           │
              └→cancelled  └→cancelled  └→failed (order rejected)
              └→failed     └→failed (timeout)
```

## Notifications

Single event type `"short_sale_task_update"` with payload:
```json
{
  "task_id": "sst-1-...",
  "follower_id": "f1",
  "symbol": "AAPL",
  "status": "locating",
  "master_order_id": 12345,
  "required_qty": 600,
  "locate_deficit": 200,
  "error": null,
  "created_at": 1709000000.0
}
```

## Verification

1. **Unit test:** Mock `get_max_sell()` to return 0 → verify `smart_locate()` is called with full qty, then `replicate_order()` is called
2. **Unit test:** Mock `get_max_sell()` to return sufficient capacity → verify `smart_locate()` is NOT called, order placed immediately
3. **Unit test:** Two concurrent shorts on same symbol → verify serialization (second re-checks capacity)
4. **Unit test:** Master cancels during locate → verify task is cancelled, no order placed
5. **Integration test:** Start system, submit a short order via master → verify task flow end-to-end via WebSocket events
6. **Manual test:** Check `GET /api/short-sales/tasks` returns active tasks, `POST .../cancel` cancels them
