# Unpause Reconciliation Modal + Auto-Inference Removal + Locate Cleanup

## Context

When a user resumes replication after a pause (during which they may have manually traded on follower accounts), the system has no way to reconcile position differences. The existing auto-inference feature (`PositionOpenedEvent` → compute multiplier ratio) is fragile — it only fires once on the first fill, misses partial fills, and silently sets multipliers that may surprise the user.

**New approach:** Replace automatic inference with an explicit reconciliation step at resume time. When the user starts the system, a modal shows all overlapping/master-only positions and lets the user choose multipliers and blacklist entries before replication begins. This provides a clear mental model: "multiplier is what I set, period."

Additionally, the old locate replication code (`locate_replicator.py`, `locate_map.py`, `api/locates.py`) is dead — unreachable after the short sale manager refactor. Clean it up.

## Design

### Two-Phase Start

Replace `POST /api/start` with two distinct endpoints:

1. **Connect** (`POST /api/connect`) — connects DAS clients, loads multiplier/blacklist state from DB
2. **Reconcile** (`GET /api/reconcile`) — computes position comparison. If `has_entries: true`, frontend shows modal
3. **Apply + Start** (`POST /api/reconcile/apply`) — applies user's multiplier/blacklist decisions, then starts replication engine

If no positions to reconcile → frontend calls `POST /api/start-replication` directly (skipping modal).

The daily restart scheduler (`scheduler.py`) calls Python methods directly (`das_service.start()`, `engine.start()`), not HTTP endpoints — it is unaffected by this API change.

### REST vs WebSocket Separation

**REST** handles: system lifecycle (`connect`, `start-replication`, `stop`), configuration CRUD (followers, multipliers, blacklist), reconciliation (query + apply). These are request-response operations.

**WebSocket** handles: real-time server→client pushes (`state_update`, `order_replicated`, `short_sale_task_update`, alerts) and latency-sensitive interactive actions during active trading (`cancel_short_sale_task`, `override_multiplier`, `replay_actions`, `discard_actions`).

The reconciliation feature is REST-only — it's a one-time setup flow before trading begins.

### Reconciliation Modal

Shows a table per follower. Each row is a symbol from master positions:

| Scenario | Default Action |
|----------|---------------|
| Common, same direction (both LONG or both SHORT) | Use inferred multiplier (`abs(follower_qty)/abs(master_qty)`) |
| Common, different direction (master LONG, follower SHORT or vice versa) | Blacklist |
| Master-only (follower has no position) | Blacklist |

Per row, user can:
- **Radio group**: Use Inferred / Manual Override (text input) / Use Default (base multiplier)
- **Blacklist checkbox**: add/remove from blacklist (blacklist only — no 0x multiplier override)

Footer buttons: "Apply & Start Replication" (primary), "Skip & Start" (no changes), "Cancel" (stay in connected-only state)

### Follower-only positions

Positions that exist only on the follower (master has no position) are excluded — the master won't take actions on those symbols, so no reconciliation needed.

## Files

### New Files

| File | Purpose |
|------|---------|
| `backend/app/api/reconcile.py` | `GET /api/reconcile`, `POST /api/reconcile/apply` endpoints |
| `backend/app/schemas/reconcile.py` | Pydantic request/response models |
| `frontend/src/components/dashboard/reconcile-dialog.tsx` | Reconciliation modal (follows `replay-dialog.tsx` pattern) |

### Modified Files

| File | Changes |
|------|---------|
| `backend/app/api/system.py` | Remove `POST /api/start`; add `POST /api/connect` and `POST /api/start-replication` |
| `backend/app/main.py` | Register `reconcile` router, inject dependencies |
| `backend/app/engine/replication_engine.py` | Remove `_subscribe_to_followers()`, `_on_follower_position_opened()`, `PositionOpenedEvent` import |
| `backend/app/engine/position_tracker.py` | Remove `on_follower_position_opened()` method, update docstrings |
| `backend/app/engine/multiplier_manager.py` | Remove `set_auto_inferred()`, add one-time migration to delete existing `auto_inferred` rows |
| `backend/app/models/__init__.py` | Remove `LocateMap` import/export |
| `frontend/src/lib/types.ts` | Add reconciliation types, update `SystemStatus` with `replication_active`, remove `LocatePrompt` |
| `frontend/src/lib/api-client.ts` | Replace `startSystem` with `connectSystem` + `startReplication`; add reconciliation methods; remove locate methods |
| `frontend/src/stores/app-store.ts` | Add reconcile state; remove `locatePrompts`, locate WS handlers, `multiplier_inferred` handler |
| `frontend/src/components/dashboard/connection-status.tsx` | Two-phase start flow in the Start button handler |
| `frontend/src/components/dashboard/alerts-panel.tsx` | Remove locate prompt UI (accept/reject buttons) |
| `frontend/src/app/layout.tsx` | Mount `<ReconcileDialog />` |

### Deleted Files

| File | Reason |
|------|--------|
| `backend/app/engine/locate_replicator.py` | Dead code — `LocateReplicator` no longer instantiated |
| `backend/app/models/locate_map.py` | Dead code — only used by locate_replicator |
| `backend/app/api/locates.py` | Dead code — router already removed from main.py |
| `backend/app/schemas/locates.py` | Dead code — schemas for removed locate endpoints |

## Implementation Steps

### Phase 1: Backend — System API Refactor

**Step 1.1: Refactor `system.py`**
File: `backend/app/api/system.py`

- Extract config loading + DAS client setup (current lines 96-165) into `_load_and_connect()` helper
- Replace `POST /api/start` with:
  - `POST /api/connect` — calls `_load_and_connect()`, loads multiplier/blacklist from DB. Returns `{"status": "connected", ...connection_info}`
  - `POST /api/start-replication` — calls `engine.start(follower_configs=...)`. Returns `{"status": "started"}`
- Keep `POST /api/stop` as-is (stops engine + DAS clients)
- Update `GET /api/status` to include `replication_active: bool` from engine's `_running` flag

**Step 1.2: Update scheduler**
File: `backend/app/engine/scheduler.py`

- Scheduler already calls Python methods directly (`das_service.start()`, `engine.start()`), not HTTP endpoints. No change needed — just verify it still works after `POST /api/start` is removed.

### Phase 2: Backend — Reconciliation API

**Step 2.1: Pydantic schemas**
New file: `backend/app/schemas/reconcile.py`
```python
class ReconcilePositionEntry(BaseModel):
    symbol: str
    master_qty: int           # signed
    master_side: str          # "LONG" | "SHORT"
    follower_qty: int         # 0 if no position
    follower_side: str | None
    scenario: str             # "common_same_dir" | "common_diff_dir" | "master_only"
    inferred_multiplier: float | None
    current_multiplier: float
    current_source: str       # "base" | "user_override"
    is_blacklisted: bool
    default_action: str       # "use_inferred" | "blacklist"

class ReconcileFollowerData(BaseModel):
    follower_id: str
    follower_name: str
    base_multiplier: float
    entries: list[ReconcilePositionEntry]

class ReconcileResponse(BaseModel):
    followers: list[ReconcileFollowerData]
    has_entries: bool

class ReconcileDecision(BaseModel):
    symbol: str
    action: str               # "use_inferred" | "manual" | "use_default"
    multiplier: float | None  # required for use_inferred and manual
    blacklist: bool

class ReconcileApplyFollower(BaseModel):
    follower_id: str
    decisions: list[ReconcileDecision]

class ReconcileApplyRequest(BaseModel):
    followers: list[ReconcileApplyFollower]
```

**Step 2.2: Reconcile API router**
New file: `backend/app/api/reconcile.py`

`GET /api/reconcile?follower_ids=f1,f2` — Requires DAS clients to be connected. For each follower:
- Build master position map from `master_client.positions`
- Build follower position map from `follower_client.positions`
- For each symbol in master positions (skip follower-only):
  - Classify: `common_same_dir`, `common_diff_dir`, or `master_only`
  - Compute `inferred_multiplier = abs(f_qty) / abs(m_qty)` for same-direction
  - Look up current multiplier/source via `multiplier_mgr.get_effective()` / `get_source()`
  - Look up blacklist state via `blacklist_mgr.is_blacklisted()`
  - Set `default_action`: `"use_inferred"` for same-dir, `"blacklist"` otherwise

`POST /api/reconcile/apply` — For each decision:
- `use_inferred` / `manual`: call `multiplier_mgr.set_symbol_override(fid, symbol, multiplier, source="user_override")`
- `use_default`: call `multiplier_mgr.remove_symbol_override(fid, symbol)`
- `blacklist=true`: call `blacklist_mgr.add(fid, symbol, reason="reconciliation")`
- `blacklist=false`: call `blacklist_mgr.remove(fid, symbol)`
- After applying all decisions: call `engine.start(follower_configs=...)` to start replication

Uses same dependency injection pattern as `system.py` (`set_service_getters()`).

**Step 2.3: Register in main.py**
- Import `reconcile` module
- Add dependency injection
- Add `app.include_router(reconcile.router)`

### Phase 3: Backend — Deprecation & Cleanup

**Step 3.1: Remove auto-inference**
- `replication_engine.py`: Remove `PositionOpenedEvent` import, remove `_subscribe_to_followers()` method, remove its call in `start()`, remove `_on_follower_position_opened()` handler
- `position_tracker.py`: Remove `on_follower_position_opened()` method, update module/class docstrings to reflect new responsibility (dashboard snapshot only). Keep `get_positions_snapshot()` and `_serialize_position()`.
- `multiplier_manager.py`: Remove `set_auto_inferred()`. Delete any existing `source="auto_inferred"` rows from DB during `load_from_db()` as a one-time migration (after this change, nothing creates `auto_inferred` entries so it's self-cleaning).

**Step 3.2: Delete dead locate files**
- Delete `backend/app/engine/locate_replicator.py`
- Delete `backend/app/models/locate_map.py`
- Delete `backend/app/api/locates.py`
- Delete `backend/app/schemas/locates.py`
- Remove `LocateMap` from `backend/app/models/__init__.py`

### Phase 4: Frontend — Types, API & Store

**Step 4.1: Types** (`frontend/src/lib/types.ts`)
- Add reconciliation interfaces: `ReconcilePositionEntry`, `ReconcileFollowerData`, `ReconcileResponse`, `ReconcileDecision`, `ReconcileApplyFollower`, `ReconcileApplyRequest`
- Add `replication_active: boolean` to `SystemStatus`
- Remove `LocatePrompt` interface

**Step 4.2: API client** (`frontend/src/lib/api-client.ts`)
- Replace `startSystem()` with `connectSystem()` (`POST /api/connect`)
- Add `getReconciliation(followerIds?)` (`GET /api/reconcile`)
- Add `applyReconciliation(data)` (`POST /api/reconcile/apply`)
- Add `startReplication()` (`POST /api/start-replication`)
- Remove `acceptLocate()`, `rejectLocate()`

**Step 4.3: Store** (`frontend/src/stores/app-store.ts`)
- Add: `reconcileData: ReconcileResponse | null`, `reconcileOpen: boolean`, `reconcilePending: boolean` + setters
- Remove: `locatePrompts` state
- Remove WS handlers: `locate_prompt`, `locate_found`, `locate_accepted_manual_entry`, `locate_rejected`, `multiplier_inferred`

### Phase 5: Frontend — Components

**Step 5.1: ReconcileDialog** (new file `frontend/src/components/dashboard/reconcile-dialog.tsx`)
- Follows `replay-dialog.tsx` pattern: fixed overlay with `z-50`, Zustand-controlled visibility via `reconcileOpen`
- Local state: `Record<string, EntryDecision>` keyed by `${followerId}:${symbol}`
  ```typescript
  interface EntryDecision {
    action: "use_inferred" | "manual" | "use_default";
    manualMultiplier: string;
    blacklisted: boolean;
  }
  ```
- Initialize defaults from `reconcileData`: same-dir → use_inferred, diff-dir/master-only → blacklisted
- Each row: symbol info + scenario badge + radio group (Use Inferred / Manual / Use Default) + blacklist checkbox
- "Use Inferred" radio disabled when `inferred_multiplier` is null
- Footer: "Apply & Start Replication" (primary), "Skip & Start" (secondary), "Cancel"
- Submit: builds `ReconcileApplyRequest`, calls `api.applyReconciliation()`, closes modal
- "Skip & Start": calls `api.startReplication()` directly

**Step 5.2: ConnectionStatus** (`frontend/src/components/dashboard/connection-status.tsx`)
Replace the Start button handler with two-phase flow:
```
if isRunning → api.stopSystem()
else:
  1. await api.connectSystem()           // phase 1: connect DAS clients
  2. reconcileData = await api.getReconciliation()
  3. if reconcileData.has_entries → show reconcile modal (modal handles apply + start)
  4. else → await api.startReplication()  // no positions to reconcile
```
Add intermediate loading state ("Connecting...").

Handle the `connected` but not `replication_active` state (e.g. if user refreshed the page during reconciliation): show a button to open the reconcile modal or start replication directly.

**Step 5.3: Mount dialog** (`frontend/src/app/layout.tsx`)
Add `<ReconcileDialog />` alongside `<ReplayDialog />`

**Step 5.4: Cleanup alerts panel** (`frontend/src/components/dashboard/alerts-panel.tsx`)
Remove locate prompt UI (accept/reject buttons, locate-specific rendering)

### Phase 6: Lint & Verify

- Run `ruff check --fix` and `ruff format` on all modified/new backend files
- Run frontend lint
- Manual test: start system → verify modal appears with correct position data → apply → verify replication starts
- Verify daily scheduler restart still works (calls Python methods directly)

## Edge Cases

1. **No positions to reconcile** — `GET /api/reconcile` returns `has_entries: false`, frontend skips modal and calls `POST /api/start-replication` directly
2. **Connection failure** — `POST /api/connect` fails → frontend shows error, stays in stopped state
3. **Partial connection** (some followers fail to connect) — skip disconnected followers in reconciliation; show warning
4. **Browser closed during reconciliation** — system is in `connected` state (DAS clients up, no replication). On next page load, frontend detects `running: true, replication_active: false` → shows option to reconcile or start
5. **Single follower enable at runtime** — deferred to follow-up. Currently toggle only flips DB boolean, takes effect on next system restart
6. **Stale auto_inferred entries** — cleaned up as one-time migration in `load_from_db()`. After this change, nothing creates `auto_inferred` entries.
