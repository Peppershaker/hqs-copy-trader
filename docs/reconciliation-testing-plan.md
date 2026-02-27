# Manual Testing Plan — Unpause Reconciliation

## Test 1: Cold start with no master positions

**Purpose:** Verify the system skips reconciliation when there's nothing to reconcile.

1. Ensure master account has zero open positions
2. Click **Start**
3. **Expected:** Button shows "Connecting..." → "Checking positions..." → "Starting replication..." → system transitions to running with replication active. No modal appears.

## Test 2: Same-direction positions show inferred multiplier

**Purpose:** Verify the modal appears with "common_same_dir" entries and correct inferred multipliers.

1. Manually open positions on both master and a follower before starting (e.g., master LONG 1000 AAPL, follower LONG 3000 AAPL)
2. Click **Start**
3. **Expected:** Modal appears. AAPL row shows scenario "Same direction", inferred multiplier = 3.0x, "Use Inferred" radio is pre-selected, blacklist checkbox is unchecked.

## Test 3: Master-only positions default to blacklisted

**Purpose:** Verify master-only positions default to blacklisted.

1. Master has LONG 500 TSLA, follower has no TSLA position
2. Click **Start**
3. **Expected:** Modal shows TSLA with scenario "Master only", inferred multiplier shows "n/a" (Use Inferred radio disabled), "Use Default" radio is selected, blacklist checkbox is **checked**.

## Test 4: Opposite-direction positions default to blacklisted

**Purpose:** Verify direction mismatch defaults to blacklist.

1. Master LONG 1000 NVDA, follower SHORT 2000 NVDA
2. Click **Start**
3. **Expected:** NVDA row shows "Opposite direction", inferred = n/a, Use Inferred radio disabled, blacklist checkbox is checked.

## Test 5: Apply reconciliation with mixed decisions

**Purpose:** Verify the apply endpoint correctly persists multiplier overrides and blacklist entries, then starts replication.

1. Start the system so the modal appears with multiple symbols
2. For one symbol: select "Use Inferred"
3. For another: select "Manual", enter `2.5`
4. For another: check blacklist
5. Click **Apply & Start Replication**
6. **Expected:** Modal closes, alert says "Reconciliation applied — replication started", system shows replication active. Verify via the multipliers page that user_override entries were created. Verify via the blacklist page that blacklisted symbols appear.

## Test 6: Cancel leaves system connected but not replicating

**Purpose:** Verify "Cancel" leaves the system in connected-but-not-replicating state.

1. Start system so modal appears
2. Click **Cancel**
3. **Expected:** Modal closes. System is connected (`running: true`) but replication is **not** active (`replication_active: false`). DAS clients remain connected. Clicking Start again re-triggers the connect → reconcile flow.

## Test 7: Connection failure

**Purpose:** Verify error handling when DAS clients fail to connect.

1. Configure an invalid master host/port
2. Click **Start**
3. **Expected:** Button shows "Connecting..." then an error message appears below the button. System stays in stopped state. No modal appears.

## Test 8: Multiple followers

**Purpose:** Verify each follower gets its own section in the modal with independent decisions.

1. Configure two enabled followers, both with different positions relative to master
2. Click **Start**
3. **Expected:** Modal shows two follower sections, each with their own name, base multiplier, and entry rows. Decisions are independent per follower.

## Test 9: Stop and restart cycle

**Purpose:** Verify the full lifecycle — start with reconciliation, trade, stop, restart with updated positions.

1. Start system via reconciliation modal (apply decisions)
2. Let some trades replicate
3. Click **Stop**
4. Manually adjust a follower position
5. Click **Start** again
6. **Expected:** New reconciliation modal appears reflecting current position state (including changes from step 4). Previous multiplier overrides show as `current_multiplier` / `current_source` values.

## Test 10: Daily scheduler restart (regression)

**Purpose:** Verify the automated daily restart still works since it calls Python methods directly, not HTTP endpoints.

1. Set scheduler to trigger shortly (or call the restart method manually)
2. **Expected:** Scheduler calls `das_service.stop()` → `das_service.start()` → `engine.start()` directly. No reconciliation modal involved — server-side automated restart bypasses the frontend flow entirely.
