#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# dev.sh — Full development watch mode
#
# Starts three processes simultaneously:
#   [BACKEND]  uvicorn with --reload (watches backend/app/)
#   [FRONTEND] vite dev server       (HMR on http://localhost:5173)
#   [TESTS]    vitest in watch mode  (re-runs on file save)
#
# Usage:
#   ./dev.sh            # backend + frontend + tests
#   ./dev.sh --no-tests # backend + frontend only (faster startup)
#
# Prerequisites:
#   pip install -r backend/requirements.txt
#   cd frontend && npm install
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NO_TESTS=false

for arg in "$@"; do
  [[ "$arg" == "--no-tests" ]] && NO_TESTS=true
done

# ── Colour helpers ────────────────────────────────────────────────────────────
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RESET='\033[0m'

log() { echo -e "${CYAN}[dev.sh]${RESET} $*"; }

# ── Trap: kill all children on exit ──────────────────────────────────────────
PIDS=()
cleanup() {
  log "Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ── Backend ───────────────────────────────────────────────────────────────────
log "${GREEN}Starting backend${RESET} → http://localhost:8000"
(
  cd "$ROOT/backend"
  # Load .env so AUTH_ENABLED / JWT_SECRET_KEY etc. are available
  if [[ -f .env ]]; then
    set -a; source .env; set +a
  fi
  uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --reload-dir app \
    --log-level info \
    2>&1 | sed "s/^/${CYAN}[BACKEND]${RESET} /"
) &
PIDS+=($!)

# Give backend a moment to bind the port
sleep 1

# ── Frontend dev server ───────────────────────────────────────────────────────
log "${GREEN}Starting frontend${RESET} → http://localhost:5173"
(
  cd "$ROOT/frontend"
  npm run dev -- --clearScreen false 2>&1 | sed "s/^/${GREEN}[FRONTEND]${RESET} /"
) &
PIDS+=($!)

# ── Vitest watch (optional) ───────────────────────────────────────────────────
if [[ "$NO_TESTS" == "false" ]]; then
  log "${YELLOW}Starting vitest watch${RESET}"
  (
    cd "$ROOT/frontend"
    npm run test:watch -- --reporter=verbose 2>&1 | sed "s/^/${YELLOW}[TESTS]${RESET} /"
  ) &
  PIDS+=($!)
fi

log "All services running. Press Ctrl+C to stop."
log ""
log "  ${CYAN}Backend ${RESET} http://localhost:8000"
log "  ${GREEN}Frontend${RESET} http://localhost:5173"
[[ "$NO_TESTS" == "false" ]] && log "  ${YELLOW}Tests   ${RESET} vitest watch (saves auto-rerun)"

wait
