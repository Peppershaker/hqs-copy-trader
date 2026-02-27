# DAS Copy Trader

Semi-automatic copy trading system for DAS Trader Pro. Replicates trading activity from one **master account** to multiple **follower accounts** in real-time, with automatic quantity scaling, short sale locate management, and a real-time dashboard.

## Quick Start

1. Configure master and follower accounts via the Settings page
2. Click **Start** to connect all accounts
3. The engine subscribes to master events and replicates to followers automatically

```
POST /api/start   — connect all accounts & begin replication
POST /api/stop    — disconnect & stop replication
GET  /api/status  — connection status
```

---

## Core Flows

### Order Replication

When the master places an order, the engine replicates it to every enabled, connected follower:

```
Master order accepted
  |
  +-- For each follower:
        |-- Blacklisted?  --> skip
        |-- Disconnected? --> queue for later replay
        |-- Short sale?   --> ShortSaleManager (see below)
        |-- Otherwise     --> scale qty, submit matching order
```

**What is preserved:** order type (Market/Limit/Stop/StopLimit/TrailingStop), side (BUY/SELL/SHORT), price, stop price, time-in-force.

**What is scaled:** quantity only, via `master_qty * multiplier` (rounded, minimum 1).

Cancellations and replacements are tracked through an internal order map (`master_order_id -> {follower_id: follower_order_id}`) and forwarded to all followers that received the original order.

### Short Sale Handling (On-Demand Locate)

Master locate events are **not** replicated. Instead, when the master places a `SHORT_SELL` order, the `ShortSaleManager` handles the full workflow per follower:

```
1. Check capacity    client.get_max_sell(symbol)
2. Compute deficit   required_qty - max_sell
3. If deficit > 0    smart_locate(symbol, deficit, max_price, timeout)
4. Place order       replicate_order(master_order, follower)
```

This ensures the follower never attempts a short sale without sufficient locate capacity, and only borrows exactly the shares needed (accounting for existing long positions and prior locates).

**Task lifecycle:**

```
pending --> checking --> locating --> placing_order --> completed
                |            |             |
                +--> failed  +--> failed   +--> failed
                +--> cancelled             +--> cancelled
```

**Concurrency controls:**

- **Per-(follower, symbol) lock** -- serializes multiple shorts on the same ticker so the second task re-checks capacity after the first completes, preventing double-locating.
- **Global semaphore (default 3)** -- caps concurrent `smart_locate()` calls across all followers to respect DAS API rate limits.
- **Master cancellation** -- if the master cancels the order while a task is in-flight, the task is cancelled immediately (no wasted locates).

**Configuration (per follower):**

| Setting | Default | Description |
|---------|---------|-------------|
| `max_locate_price` | $0.10 | Absolute max price per share for auto-locate |
| `locate_retry_timeout` | 120s | How long `smart_locate` retries before giving up |

### Multiplier System

Quantity scaling is resolved per `(follower, symbol)` with this priority:

1. **User override** -- explicit per-symbol multiplier set via UI/API
2. **Auto-inferred** -- detected from position ratios when the follower opens a position
3. **Base multiplier** -- the follower's default (configured in settings)

Auto-inference only fires when the difference from the current effective multiplier exceeds 1%, and never overwrites a user override.

### Blacklist

Per-follower, per-symbol exclusion. When a symbol is blacklisted on a follower:
- No orders are replicated for that symbol
- No short sale tasks are created for that symbol

Entries are added manually via UI or automatically when a user rejects a locate offer. Persisted in SQLite.

### Offline Follower Queue

When a follower is disconnected at replication time, the action is queued in memory:

| Action Type | Queued Data |
|-------------|-------------|
| `order_submit` | `master_order_id` |
| `order_cancel` | `master_order_id` |
| `order_replace` | `master_order_id`, `new_quantity`, `new_price` |

On reconnect, the UI is notified and the user can **replay** or **discard** queued actions. Replayed short sale orders go through the `ShortSaleManager` flow (capacity check + on-demand locate).

The queue is in-memory only and clears on app restart.

---

## API Reference

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/das-servers` | Configured DAS servers from env |
| GET | `/api/status` | Connection status for all accounts |
| GET | `/api/health` | Detailed health diagnostics per account |
| POST | `/api/start` | Start connections and replication engine |
| POST | `/api/stop` | Stop everything |

### Master

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/master` | Get master config |
| PUT | `/api/master` | Create/update master config |

### Followers

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/followers` | List all followers |
| POST | `/api/followers` | Add a follower |
| GET | `/api/followers/{id}` | Get follower details |
| PUT | `/api/followers/{id}` | Update follower |
| DELETE | `/api/followers/{id}` | Remove follower |
| PATCH | `/api/followers/{id}/multiplier` | Update base multiplier |
| PATCH | `/api/followers/{id}/toggle` | Enable/disable |

### Blacklist

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/blacklist` | List entries (optional `?follower_id=` filter) |
| POST | `/api/blacklist` | Add entry |
| DELETE | `/api/blacklist/{id}` | Remove entry |

### Multipliers

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/multipliers/{follower_id}` | Get all symbol overrides |
| PUT | `/api/multipliers/{follower_id}/{symbol}` | Set/override multiplier |
| DELETE | `/api/multipliers/{follower_id}/{symbol}` | Remove override |

### Short Sales

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/short-sales/tasks` | List active short sale tasks |
| GET | `/api/short-sales/tasks/all` | All tasks (including terminal) |
| POST | `/api/short-sales/tasks/{task_id}/cancel` | Cancel a task |

### Queued Actions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/queued-actions` | All pending actions by follower |
| GET | `/api/queued-actions/{follower_id}` | Pending for one follower |
| POST | `/api/queued-actions/{follower_id}/replay` | Replay selected actions |
| POST | `/api/queued-actions/{follower_id}/discard` | Discard selected actions |

### Environment Config

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/env-config` | Get stored `.env` content |
| PUT | `/api/env-config` | Save and apply `.env` content |

### WebSocket

`WS /ws` -- bidirectional real-time channel. The server broadcasts state updates at 1 Hz plus event-driven notifications.

---

## WebSocket Events

### Server to Client

| Event | When | Key Data |
|-------|------|----------|
| `state_update` | Every 1s | Full system state (positions, orders, connection status, active short sale tasks) |
| `order_replicated` | Master order accepted | symbol, side, qty, per-follower results |
| `order_cancelled` | Master order cancelled | master_order_id, per-follower results |
| `order_replaced` | Master order replaced | master_order_id, per-follower results |
| `short_sale_task_update` | Task state change | task_id, status, symbol, follower, deficit, error |
| `action_queued` | Follower offline at replication time | follower_id, action_type, symbol |
| `queued_actions_available` | Follower reconnects with pending queue | follower_id, actions list |
| `actions_replayed` | User replays queued actions | follower_id, per-action results |
| `multiplier_inferred` | Position-based auto-inference | follower_id, symbol, old/new multiplier |
| `alert` | Error or warning condition | level (error/warn/info), message |
| `log_entries` | Every 2s (if new logs) | Recent log entries |

### Client to Server

| Action | Data | Description |
|--------|------|-------------|
| `cancel_short_sale_task` | `task_id` | Cancel an in-flight short sale task |
| `override_multiplier` | `follower_id`, `symbol`, `multiplier` | Set per-symbol multiplier |
| `replay_actions` | `follower_id`, `action_ids` | Replay queued actions |
| `discard_actions` | `follower_id`, `action_ids` | Discard queued actions |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_HOST` | `127.0.0.1` | Server bind address |
| `APP_PORT` | `8787` | Server port |
| `DB_PATH` | `./das_copy_trader.db` | SQLite database path |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `STATIC_DIR` | Auto-detected | Frontend static files directory |
| `DAS_SERVERS` | `[]` | JSON array of DAS broker configs |

### DAS_SERVERS Format

```json
[
  {
    "broker_id": "BROKER_NAME",
    "host": "127.0.0.1",
    "port": 9000,
    "username": "user",
    "password": "pass",
    "accounts": ["ACCT1", "ACCT2"],
    "smart_routes": ["ROUTE1"],
    "locate_routes": {"ROUTE1": 0, "ROUTE2": 1}
  }
]
```

When `DAS_SERVERS` is set, the host/port/username/password from a matching `broker_id` entry override the per-account values stored in the database. This allows separating credentials from account configuration.

---

## Architecture

```
Browser (Next.js 14 / React 19 / Radix UI / Tailwind / Zustand)
         |
         | HTTP + WebSocket
         v
FastAPI Backend (:8787)
  +-- ReplicationEngine (orchestrator)
  |     +-- OrderReplicator        order submit / cancel / replace
  |     +-- ShortSaleManager       on-demand locate + short workflow
  |     +-- PositionTracker        multiplier auto-inference
  |     +-- MultiplierManager      per-(follower, symbol) resolution
  |     +-- BlacklistManager       per-(follower, symbol) exclusion
  |     +-- ActionQueue            offline follower queue
  +-- DASService                   manages DASClient instances
  +-- NotificationService          WebSocket broadcaster
  +-- SQLite                       persistent config & tracking
         |
         | TCP (das-bridge)
         v
DAS Trader Pro (master + N followers)
```

### Daily Restart

The system automatically restarts at **3:00 AM Eastern** to clear accumulated in-memory state (order maps, retry tasks). All configuration, blacklists, and multiplier overrides are persisted in SQLite and survive restarts.

---

## Project Structure

```
backend/
  app/
    api/            HTTP + WebSocket route handlers
    engine/         Core replication logic
      replication_engine.py    main orchestrator
      order_replicator.py      order submit/cancel/replace
      short_sale_manager.py    on-demand locate + short workflow
      position_tracker.py      multiplier auto-inference
      multiplier_manager.py    quantity scaling resolution
      blacklist_manager.py     symbol exclusion
      action_queue.py          offline follower queue
      scheduler.py             daily restart
    models/         SQLAlchemy models (SQLite)
    services/       DAS connection management, notifications, logging
    main.py         FastAPI app entry point
  logs/             Per-run log directories
frontend/
  src/
    app/            Next.js pages (dashboard, settings, management, etc.)
    components/     React components
    store/          Zustand state management
    lib/            API client, WebSocket client, utilities
docs/
  DESIGN.md                         Architecture design document
  on-demand-short-sale-manager.md   Short sale manager implementation spec
```
