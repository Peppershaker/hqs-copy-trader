#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# build.sh – Build frontend + bundle everything into a single
#            DASCopyTrader.exe via PyInstaller
#
# Usage:  ./scripts/build.sh
# Output: dist/DASCopyTrader/DASCopyTrader.exe  (one-dir mode)
# ──────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

DAS_BRIDGE_DIR="${DAS_BRIDGE_DIR:-/home/victor/code/das-bridge}"

echo "============================================"
echo "  DAS Copy Trader – Production Build"
echo "============================================"

# ── 1. Verify das-bridge source is reachable ──────────────────
if [[ ! -d "$DAS_BRIDGE_DIR/src/das_bridge" ]]; then
    echo "ERROR: das-bridge source not found at $DAS_BRIDGE_DIR"
    echo "Set DAS_BRIDGE_DIR env var to point to the das-bridge repo root."
    exit 1
fi
echo "[1/4] das-bridge source found at $DAS_BRIDGE_DIR"

# ── 2. Build the Next.js frontend as static HTML ─────────────
echo "[2/4] Building frontend (next build --output export)..."
cd "$ROOT_DIR/frontend"

if [[ ! -d node_modules ]]; then
    echo "     Installing npm dependencies..."
    npm ci
fi

npx next build
FRONTEND_OUT="$ROOT_DIR/frontend/out"

if [[ ! -d "$FRONTEND_OUT" ]]; then
    echo "ERROR: Frontend build did not produce out/ directory."
    echo "       Make sure next.config.mjs has output: 'export'."
    exit 1
fi
echo "     Frontend built → $FRONTEND_OUT"

# ── 3. Copy static frontend into backend/app/static ──────────
echo "[3/4] Copying frontend build to backend/app/static/..."
STATIC_DIR="$ROOT_DIR/backend/app/static"
rm -rf "$STATIC_DIR"
cp -r "$FRONTEND_OUT" "$STATIC_DIR"
echo "     Copied to $STATIC_DIR"

# ── 4. Run PyInstaller ────────────────────────────────────────
echo "[4/4] Running PyInstaller..."
cd "$ROOT_DIR/backend"
source .venv/bin/activate

python "$SCRIPT_DIR/build.py" \
    --das-bridge-dir "$DAS_BRIDGE_DIR" \
    --static-dir "$STATIC_DIR"

echo ""
echo "============================================"
echo "  Build complete!"
echo "  Output: $ROOT_DIR/backend/dist/DASCopyTrader/"
echo "============================================"
