#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# dev.sh – Start backend + frontend in dev mode (side-by-side)
# Usage:  ./scripts/dev.sh
# ──────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "==> Starting backend (uvicorn) on :8787 ..."
cd "$ROOT_DIR/backend"
source .venv/bin/activate
uvicorn app.main:app --reload --port 8787 &
BACKEND_PID=$!

echo "==> Starting frontend (next dev) on :3000 ..."
cd "$ROOT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

cleanup() {
    echo ""
    echo "==> Stopping dev servers..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    echo "==> Done."
}
trap cleanup EXIT INT TERM

wait
