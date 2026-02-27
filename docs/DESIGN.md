# DAS Copy Trader — Design Document

## Overview

A semi-automatic copy trading system for DAS Trader Pro. One **master account** drives N **follower accounts** — orders, cancels, replacements, and short locates are replicated automatically with configurable position size multipliers.

**Target users**: Traders on Windows desktops (not engineers).  
**Deployment**: Single `.exe` via PyInstaller — double-click to run, opens in browser.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                Web Browser (localhost:3000)                │
│   Next.js static app  •  Radix UI  •  Tailwind CSS       │
│   WebSocket ← real-time state    REST → actions/config    │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP + WS
┌──────────────────────▼───────────────────────────────────┐
│                FastAPI Application Server                  │
│                                                           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │                 Replication Engine                     │ │
│  │                                                       │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │ │
│  │  │ Order        │  │ Locate       │  │ Position   │  │ │
│  │  │ Replicator   │  │ Replicator   │  │ Tracker    │  │ │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬─────┘  │ │
│  │         │                 │                  │        │ │
│  │  ┌──────▼─────────────────▼──────────────────▼─────┐  │ │
│  │  │           Multiplier Manager                    │  │ │
│  │  │  (per-follower base × per-symbol auto-adjust)   │  │ │
│  │  └─────────────────────────────────────────────────┘  │ │
│  └──────────────────────────┬────────────────────────────┘ │
│                             │                              │
│  ┌──────────────────────────▼────────────────────────────┐ │
│  │              DAS Bridge Layer                          │ │
│  │                                                       │ │
│  │   master_client (DASClient)                           │ │
│  │   follower_clients: dict[str, DASClient]              │ │
│  │                                                       │ │
│  │   Event subscriptions on master → replication engine   │ │
│  │   Each client has its own TCP connection to DAS        │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌───────────────────────────────────────────────────────┐ │
│  │   SQLite (config, blacklists, order map, audit log)   │ │
│  └───────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer      | Technology                                     | Notes                                 |
| ---------- | ---------------------------------------------- | ------------------------------------- |
| Backend    | Python 3.10+, FastAPI, uvicorn                 | Async-native, matches das-bridge      |
| Frontend   | Next.js 14 (static export), Radix UI, Tailwind | Rich SPA, real-time via WebSocket     |
| Database   | SQLite via aiosqlite + SQLAlchemy async        | Zero setup, persistent config         |
| Real-time  | WebSocket (FastAPI native)                     | Push state changes to UI              |
| Packaging  | PyInstaller                                    | Single `.exe`, serves static frontend |
| Shared lib | das-bridge (local dependency)                  | TCP to DAS Trader CMD API             |

---

## Features

### 1. Account Configuration

- **Master account**: exactly one, configured via settings UI
- **Follower accounts**: 1–N, each with:
  - DAS connection credentials (host, port, username, password, account ID)
  - **Base multiplier** (default 1.0) — UI editable at any time
  - **Per-symbol override multiplier** — auto-computed or user-set
  - Enabled/disabled toggle
  - Locate routes configuration

### 2. Order Replication (Automatic)

**Trigger**: Any order event on the master account.

| Master Event                      | Follower Action                                      |
| --------------------------------- | ---------------------------------------------------- |
| Order submitted (Market)          | Submit market order, qty × multiplier                |
| Order submitted (Limit)           | Submit limit order, same price, qty × multiplier     |
| Order submitted (Stop)            | Submit stop order, same stop price, qty × multiplier |
| Order submitted (StopLimit)       | Submit stop-limit, same prices, qty × multiplier     |
| Order cancelled                   | Cancel corresponding follower order                  |
| Order replaced (qty/price change) | Replace follower order with proportional adjustment  |

**Preserved fields**: Order type, side (BUY/SELL/SHORT), price, stop price, time-in-force.  
**Scaled fields**: Quantity (rounded to nearest integer).  
**Route**: Use follower's default route (may differ from master's broker route).

**Order Mapping**: Maintained in-memory and persisted to SQLite:

```
master_order_token → {
    follower_id_1: follower_order_token_1,
    follower_id_2: follower_order_token_2,
    ...
}
```

**Edge Cases**:

- If follower is disconnected → queue the action, replay on reconnect (or alert user)
- If follower order submission fails → log error, show alert in UI, do NOT retry automatically
- If master order is for a blacklisted ticker on a follower → skip that follower silently
- Buying power check before submission → if insufficient, alert user instead of submitting

### 3. Short Locate Replication

**Trigger**: Master successfully locates shares (LocateOrderUpdatedEvent with filled status).

**Flow**:

```
Master locates 1000 shares of XYZ at $0.02/share
    │
    ▼
For each follower (not blacklisted for XYZ):
    │
    ├─ Calculate target: 1000 × follower_multiplier
    │
    ├─ Scan locate prices on follower's routes
    │   └─ scan_locate_prices(symbol, target_qty)
    │
    ├─ Compare prices:
    │   │
    │   ├─ If cheapest offer ≤ master_price + max_price_delta → Auto-accept
    │   │   └─ smart_locate(symbol, target_qty, max_price)
    │   │
    │   └─ If cheapest offer > master_price + max_price_delta → Alert user
    │       └─ UI shows: "Locate for XYZ on [follower]: $0.05/sh (master: $0.02). Accept?"
    │
    └─ If NO locates available → Start background SmartLocateManager retry loop
        │
        ├─ On locates found → Prompt user in UI
        │   ├─ Accept → Accept locates, tell user to manually enter position
        │   └─ Reject → Blacklist XYZ on this follower (no further replication)
        │
        └─ On timeout (configurable, e.g., 5 min) → Alert user, stop trying
```

**Settings (per follower)**:

- `max_locate_price_delta`: max $/share above master price to auto-accept (default: $0.01)
- `locate_retry_timeout_seconds`: how long to keep retrying (default: 300s)
- `auto_accept_locates`: if true, accept within price delta without prompting

### 4. Dynamic Multiplier Inference

When a follower gets locates and the user manually enters a position:

1. System detects the new position via `PositionOpenedEvent` on the follower
2. Compares: `follower_position_qty / master_position_qty` → inferred multiplier
3. **UI shows**: "Auto-adjusted multiplier for [follower] on XYZ: 1.5× (was 2.0×)"
4. User can **accept** (use for subsequent orders on this symbol) or **override** with a custom value
5. This per-symbol multiplier takes precedence over the base multiplier for that symbol

**Multiplier resolution order**:

1. Per-symbol user override (if set)
2. Per-symbol auto-inferred (if positions exist in both accounts)
3. Base follower multiplier (default)

### 5. Blacklist Management

- **Per-follower, per-symbol** blacklist
- When a ticker is blacklisted on a follower:
  - No order replication for that symbol
  - No locate replication for that symbol
  - Existing open orders are NOT cancelled (user decides)
- **Sources of blacklist entries**:
  - User manually adds via UI
  - Auto-added when user rejects a locate offer
- **Removal**: User can un-blacklist from the management page

### 6. Management Overview Page

A dashboard showing at-a-glance state of the entire system:

| Column              | Data                                |
| ------------------- | ----------------------------------- |
| Follower name       | Account identifier                  |
| Status              | Connected / Disconnected / Error    |
| Base multiplier     | Current setting                     |
| Active replications | Count of symbols being replicated   |
| Pending locates     | Count of locate retries in progress |
| Blacklisted tickers | List with remove buttons            |
| P&L                 | Today's realized + unrealized       |
| Buying power        | Current available                   |

### 7. Dashboard (Home Page)

Real-time view:

- **Master positions table**: Symbol, Side, Qty, Avg Cost, P&L, Last Price
- **Follower positions tables** (one per follower, or merged): Same columns + multiplier info
- **Recent order replications**: Timestamp, Symbol, Master Order, Follower Orders, Status
- **Active alerts**: Locate prompts, errors, buying power warnings
- **Pending locates**: Symbol, follower, status, time elapsed

### 8. Settings Page

- Master account connection config
- Add/edit/remove follower accounts
- Per-follower settings:
  - Connection details (host, port, user, pass, account)
  - Base multiplier
  - Locate routes
  - Max locate price delta
  - Locate retry timeout
  - Auto-accept locates toggle
  - Enabled/disabled toggle
- Global settings:
  - UI refresh rate
  - Sound alerts on/off
  - Log level

---

## Data Models

### SQLite Tables

```sql
-- Follower account configuration
CREATE TABLE followers (
    id TEXT PRIMARY KEY,           -- unique follower identifier
    name TEXT NOT NULL,            -- display name
    broker_id TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,        -- encrypted at rest
    account_id TEXT NOT NULL,
    base_multiplier REAL NOT NULL DEFAULT 1.0,
    max_locate_price_delta REAL NOT NULL DEFAULT 0.01,
    locate_retry_timeout INTEGER NOT NULL DEFAULT 300,
    auto_accept_locates BOOLEAN NOT NULL DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    locate_routes TEXT,            -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Master account configuration (single row)
CREATE TABLE master_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    broker_id TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    account_id TEXT NOT NULL,
    locate_routes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Per-follower, per-symbol blacklist
CREATE TABLE blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    follower_id TEXT NOT NULL REFERENCES followers(id),
    symbol TEXT NOT NULL,
    reason TEXT,                   -- 'manual' | 'locate_rejected' | 'auto'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(follower_id, symbol)
);

-- Per-symbol multiplier overrides
CREATE TABLE symbol_multipliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    follower_id TEXT NOT NULL REFERENCES followers(id),
    symbol TEXT NOT NULL,
    multiplier REAL NOT NULL,
    source TEXT NOT NULL,          -- 'auto_inferred' | 'user_override'
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(follower_id, symbol)
);

-- Order replication mapping (persisted for crash recovery)
CREATE TABLE order_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    master_order_token INTEGER NOT NULL,
    master_order_id INTEGER,
    follower_id TEXT NOT NULL REFERENCES followers(id),
    follower_order_token INTEGER NOT NULL,
    follower_order_id INTEGER,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL,          -- 'pending' | 'active' | 'filled' | 'cancelled' | 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Locate replication tracking
CREATE TABLE locate_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    master_locate_id INTEGER,
    follower_id TEXT NOT NULL REFERENCES followers(id),
    symbol TEXT NOT NULL,
    master_qty INTEGER NOT NULL,
    target_qty INTEGER NOT NULL,
    master_price REAL,
    follower_price REAL,
    status TEXT NOT NULL,          -- 'scanning' | 'retrying' | 'prompted' | 'accepted' | 'rejected' | 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit log for debugging and review
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    level TEXT NOT NULL,           -- 'INFO' | 'WARN' | 'ERROR'
    category TEXT NOT NULL,        -- 'order' | 'locate' | 'position' | 'connection' | 'config'
    follower_id TEXT,
    symbol TEXT,
    message TEXT NOT NULL,
    details TEXT                   -- JSON blob for extra context
);
```

---

## API Endpoints

### REST (FastAPI)

```
# Accounts
GET    /api/master                         → master config
PUT    /api/master                         → update master config
GET    /api/followers                      → list all followers
POST   /api/followers                      → add follower
PUT    /api/followers/{id}                 → update follower
DELETE /api/followers/{id}                 → remove follower
PATCH  /api/followers/{id}/multiplier      → update base multiplier
PATCH  /api/followers/{id}/toggle          → enable/disable

# Blacklist
GET    /api/blacklist                      → all blacklist entries (optionally ?follower_id=X)
POST   /api/blacklist                      → add blacklist entry
DELETE /api/blacklist/{id}                 → remove blacklist entry

# Symbol Multipliers
GET    /api/multipliers/{follower_id}      → all symbol multipliers for a follower
PUT    /api/multipliers/{follower_id}/{symbol} → set/override multiplier
DELETE /api/multipliers/{follower_id}/{symbol} → remove override (revert to auto/base)

# Locate Actions
POST   /api/locates/{locate_map_id}/accept → accept a prompted locate offer
POST   /api/locates/{locate_map_id}/reject → reject (auto-blacklists)

# System
GET    /api/status                         → system health, connection states
POST   /api/start                          → start all DAS connections
POST   /api/stop                           → stop all connections
GET    /api/audit-log                      → paginated audit log
```

### WebSocket

```
WS /ws → bidirectional channel

Server → Client messages (JSON):
{
    "type": "state_update",
    "data": {
        "master": {
            "connected": true,
            "positions": [...],
            "orders": [...],
            "locates": [...],
            "pnl": { "realized": 0, "unrealized": 0 }
        },
        "followers": {
            "follower_1": {
                "connected": true,
                "positions": [...],
                "orders": [...],
                "locates": [...],
                "pnl": {...}
            }
        }
    }
}

{ "type": "order_replicated", "data": { "symbol": "AAPL", "master_order": {...}, "follower_results": {...} } }
{ "type": "locate_prompt", "data": { "locate_map_id": 5, "follower_id": "f1", "symbol": "XYZ", "price": 0.05, "master_price": 0.02, "qty": 2000 } }
{ "type": "locate_found", "data": { "locate_map_id": 5, "follower_id": "f1", "symbol": "XYZ", ... } }
{ "type": "multiplier_inferred", "data": { "follower_id": "f1", "symbol": "XYZ", "old": 2.0, "new": 1.5 } }
{ "type": "alert", "data": { "level": "error", "message": "..." } }
{ "type": "buying_power_warning", "data": { "follower_id": "f1", "available": 5000, "required": 8000 } }

Client → Server messages:
{ "action": "accept_locate", "locate_map_id": 5 }
{ "action": "reject_locate", "locate_map_id": 5 }
{ "action": "override_multiplier", "follower_id": "f1", "symbol": "XYZ", "multiplier": 1.75 }
```

---

## Replication Engine — State Machine

### Order Replication States

```
                    ┌──────────┐
                    │  IDLE    │
                    └────┬─────┘
                         │ master order detected
                    ┌────▼─────┐
                    │ CHECKING │ ← blacklist check, buying power check
                    └────┬─────┘
                    ┌────▼─────┐
         ┌──────── │ SENDING  │ ── failure ──► FAILED (alert)
         │         └────┬─────┘
         │         ┌────▼─────┐
         │         │  ACTIVE  │ ← follower order accepted
         │         └────┬─────┘
         │              │
         │    ┌─────────┼──────────┐
         │    ▼         ▼          ▼
         │  FILLED   CANCELLED  REPLACED
         │                         │
         │                    ┌────▼─────┐
         │                    │  ACTIVE  │ (new version)
         │                    └──────────┘
         │
         └── SKIPPED (blacklisted / disabled)
```

### Locate Replication States

```
Master locate filled
         │
    ┌────▼──────┐
    │  SCANNING │ ← scan_locate_prices on follower
    └────┬──────┘
         │
    ┌────▼──────────────┐
    │ Price acceptable?  │
    │    YES → ACCEPTING │──► FILLED (done)
    │    NO  → PROMPTED  │──► User decides
    │    NONE → RETRYING │──► SmartLocateManager loop
    └───────────────────┘
         │
    RETRYING ──► found → PROMPTED ──► accept → ACCEPTED (manual entry)
                                   ──► reject → BLACKLISTED
              ──► timeout → TIMED_OUT (alert user)
```

---

## Project Structure

```
das_auto_order/
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app, lifespan, static serving
│   │   ├── config.py                  # App configuration
│   │   ├── database.py                # SQLite setup, async session
│   │   │
│   │   ├── models/                    # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── master.py
│   │   │   ├── follower.py
│   │   │   ├── blacklist.py
│   │   │   ├── order_map.py
│   │   │   ├── locate_map.py
│   │   │   ├── symbol_multiplier.py
│   │   │   └── audit_log.py
│   │   │
│   │   ├── schemas/                   # Pydantic request/response models
│   │   │   ├── __init__.py
│   │   │   ├── accounts.py
│   │   │   ├── orders.py
│   │   │   ├── locates.py
│   │   │   ├── blacklist.py
│   │   │   └── multipliers.py
│   │   │
│   │   ├── api/                       # FastAPI route handlers
│   │   │   ├── __init__.py
│   │   │   ├── master.py
│   │   │   ├── followers.py
│   │   │   ├── blacklist.py
│   │   │   ├── multipliers.py
│   │   │   ├── locates.py
│   │   │   ├── system.py
│   │   │   └── websocket.py
│   │   │
│   │   ├── engine/                    # Core replication logic
│   │   │   ├── __init__.py
│   │   │   ├── replication_engine.py  # Orchestrator — starts/stops, subscribes to master
│   │   │   ├── order_replicator.py    # Order submit/cancel/replace logic
│   │   │   ├── locate_replicator.py   # Locate scan/accept/retry logic
│   │   │   ├── position_tracker.py    # Watches positions for multiplier inference
│   │   │   ├── multiplier_manager.py  # Resolves effective multiplier
│   │   │   └── blacklist_manager.py   # In-memory blacklist cache
│   │   │
│   │   └── services/                  # Supporting services
│   │       ├── __init__.py
│   │       ├── das_service.py         # Manages DASClient instances
│   │       ├── notification_service.py # WS push to frontend
│   │       └── audit_service.py       # Structured logging to DB
│   │
│   └── tests/
│       ├── conftest.py
│       ├── test_order_replicator.py
│       ├── test_locate_replicator.py
│       ├── test_multiplier_manager.py
│       └── test_blacklist_manager.py
│
├── frontend/
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── postcss.config.mjs
│   │
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx             # Root layout (sidebar nav)
│   │   │   ├── page.tsx               # Dashboard (home)
│   │   │   ├── settings/
│   │   │   │   └── page.tsx           # Account config
│   │   │   ├── blacklist/
│   │   │   │   └── page.tsx           # Ticker blacklist management
│   │   │   └── management/
│   │   │       └── page.tsx           # Follower overview
│   │   │
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── sidebar.tsx
│   │   │   │   └── header.tsx
│   │   │   ├── dashboard/
│   │   │   │   ├── positions-table.tsx
│   │   │   │   ├── order-log.tsx
│   │   │   │   ├── alerts-panel.tsx
│   │   │   │   └── connection-status.tsx
│   │   │   ├── settings/
│   │   │   │   ├── master-form.tsx
│   │   │   │   └── follower-form.tsx
│   │   │   ├── blacklist/
│   │   │   │   └── blacklist-table.tsx
│   │   │   └── management/
│   │   │       └── follower-cards.tsx
│   │   │
│   │   ├── hooks/
│   │   │   ├── use-websocket.ts       # WS connection + reconnect
│   │   │   ├── use-api.ts             # REST API helpers
│   │   │   └── use-store.ts           # Zustand global state
│   │   │
│   │   ├── lib/
│   │   │   ├── api-client.ts          # Fetch wrapper
│   │   │   ├── ws-client.ts           # WebSocket manager
│   │   │   └── types.ts              # TypeScript types matching backend schemas
│   │   │
│   │   └── stores/
│   │       └── app-store.ts           # Zustand store
│   │
│   └── public/
│       └── favicon.ico
│
├── scripts/
│   ├── dev.sh                         # Start backend + frontend in dev mode
│   ├── build.sh                       # Build frontend → bundle with PyInstaller
│   └── build.py                       # PyInstaller spec generator
│
├── DESIGN.md                          # This file
└── README.md
```

---

## UI Pages (Wireframes)

### Dashboard (/)

```
┌─────────────────────────────────────────────────────────────┐
│ ☰  DAS Copy Trader          [● Master: Connected]  [⚙]     │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                   │
│ Dashboard│  MASTER POSITIONS                                 │
│          │  ┌──────┬──────┬─────┬────────┬────────┬───────┐ │
│ Manage   │  │Symbol│ Side │ Qty │Avg Cost│  P&L   │ Last  │ │
│          │  ├──────┼──────┼─────┼────────┼────────┼───────┤ │
│ Blacklist│  │ AAPL │ LONG │ 100 │ 185.50 │ +$250  │186.00 │ │
│          │  │ TSLA │SHORT │ 200 │ 245.00 │ -$100  │245.50 │ │
│ Settings │  └──────┴──────┴─────┴────────┴────────┴───────┘ │
│          │                                                   │
│          │  FOLLOWER: Account-A (2.0×) [●]                   │
│          │  ┌──────┬──────┬─────┬────────┬──────┬─────────┐ │
│          │  │Symbol│ Side │ Qty │Avg Cost│ P&L  │Eff. Mult│ │
│          │  ├──────┼──────┼─────┼────────┼──────┼─────────┤ │
│          │  │ AAPL │ LONG │ 200 │ 185.50 │+$500 │ 2.0×    │ │
│          │  │ TSLA │SHORT │ 400 │ 245.00 │-$200 │ 2.0×    │ │
│          │  └──────┴──────┴─────┴────────┴──────┴─────────┘ │
│          │                                                   │
│          │  ┌─ ALERTS ──────────────────────────────────┐    │
│          │  │ ⚠ Locate found for XYZ on Account-B      │    │
│          │  │   $0.04/sh (master: $0.02) — 500 shares   │    │
│          │  │   [Accept] [Reject]                        │    │
│          │  │                                            │    │
│          │  │ ℹ Multiplier auto-adjusted: Account-A     │    │
│          │  │   TSLA: 2.0× → 1.5× [Accept] [Override]  │    │
│          │  └────────────────────────────────────────────┘    │
│          │                                                   │
│          │  RECENT REPLICATIONS                              │
│          │  ┌──────┬──────┬────────────┬──────────┬───────┐  │
│          │  │ Time │Symbol│  Master    │ Followers│Status │  │
│          │  ├──────┼──────┼────────────┼──────────┼───────┤  │
│          │  │09:31 │ AAPL │BUY 100 MKT│A:200 ✓  │  OK   │  │
│          │  │09:32 │ TSLA │SHORT 200 LM│A:400 ✓  │  OK   │  │
│          │  └──────┴──────┴────────────┴──────────┴───────┘  │
└──────────┴──────────────────────────────────────────────────┘
```

### Management (/management)

Per-follower cards showing status, multiplier, blacklisted tickers, P&L, buying power.

### Blacklist (/blacklist)

Table: Follower | Symbol | Reason | Date Added | [Remove]  
Add form: Select follower, enter symbol, add.

### Settings (/settings)

Forms for master and follower connection details. Expandable cards per follower with all settings.

---

## Key Implementation Details

### Event Flow: Master Order → Follower Replication

```python
# In replication_engine.py — subscribes to master client events

@on(OrderAcceptedEvent)
async def on_master_order_accepted(self, event: OrderAcceptedEvent):
    """Master order was accepted by exchange — replicate to followers."""
    order = self.master_client.get_order(event.order_id)
    if not order:
        return

    for follower_id, follower_client in self.followers.items():
        if self.blacklist.is_blacklisted(follower_id, order.symbol):
            continue
        if not follower_client.is_running:
            self.audit("WARN", f"Follower {follower_id} offline, skipping")
            continue

        multiplier = self.multiplier_mgr.get_effective(follower_id, order.symbol)
        scaled_qty = round(order.quantity * multiplier)

        try:
            result = await self.order_replicator.replicate(
                follower_client, order, scaled_qty
            )
            await self.save_order_mapping(event.token, follower_id, result.token)
            self.notify("order_replicated", {...})
        except Exception as e:
            self.audit("ERROR", f"Failed to replicate to {follower_id}: {e}")
            self.notify("alert", {"level": "error", "message": str(e)})
```

### Multiplier Inference

```python
# In position_tracker.py

@on(PositionOpenedEvent)  # on follower client
async def on_follower_position_opened(self, event: PositionOpenedEvent):
    master_pos = self.master_client.get_position(event.symbol)
    if not master_pos:
        return

    inferred = abs(event.quantity) / abs(master_pos.quantity)
    current = self.multiplier_mgr.get_effective(event.account_id, event.symbol)

    if abs(inferred - current) > 0.01:  # meaningful difference
        await self.multiplier_mgr.set_auto_inferred(
            event.account_id, event.symbol, inferred
        )
        self.notify("multiplier_inferred", {
            "follower_id": event.account_id,
            "symbol": event.symbol,
            "old": current,
            "new": inferred,
        })
```

---

## Packaging Strategy

1. **Build frontend**: `cd frontend && npm run build` → static files in `frontend/out/`
2. **Copy to backend**: `cp -r frontend/out backend/app/static/`
3. **PyInstaller**: Bundle `backend/app/main.py` with:
   - `das-bridge` source as data files
   - `static/` directory as data files
   - All Python dependencies
4. **Output**: Single `DASCopyTrader.exe`
5. **Runtime**: On launch, starts uvicorn → opens browser to `http://localhost:8787`

---

## Configuration File

The app uses a `.env` file alongside the exe (auto-created on first run with defaults):

```env
# DAS Copy Trader Configuration
APP_PORT=8787
DB_PATH=./das_copy_trader.db
LOG_LEVEL=INFO
```

All account/connection configuration lives in SQLite, managed through the settings UI — no manual `.env` editing for account setup.
