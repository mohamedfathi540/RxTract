#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────
# RxTract — Stop Development Environment
# ─────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="/tmp/rxtract"
LOG_DIR="/tmp/rxtract/logs"

step() {
    echo -e "\n${CYAN}${BOLD}▸ $1${NC}"
}

success() {
    echo -e "  ${GREEN}+${NC} $1"
}

warn() {
    echo -e "  ${YELLOW}!${NC} $1"
}

info() {
    echo -e "  ${DIM}$1${NC}"
}

echo ""
echo -e "${RED}${BOLD}  ╔═══════════════════════════════════════════════╗${NC}"
echo -e "${RED}${BOLD}  ║                                               ║${NC}"
echo -e "${RED}${BOLD}  ║   Stopping RxTract Development Environment    ║${NC}"
echo -e "${RED}${BOLD}  ║                                               ║${NC}"
echo -e "${RED}${BOLD}  ╚═══════════════════════════════════════════════╝${NC}"
echo ""

# ─────────────────────────────────────────────────────────
# 1. Kill frontend
# ─────────────────────────────────────────────────────────
step "Stopping frontend..."
if [ -f "$PID_DIR/frontend.pid" ]; then
    fpid=$(cat "$PID_DIR/frontend.pid" 2>/dev/null || true)
    if [ -n "$fpid" ] && kill -0 "$fpid" 2>/dev/null; then
        kill "$fpid" 2>/dev/null || true
        kill -- -"$fpid" 2>/dev/null || true
        success "Frontend stopped (PID: $fpid)"
    else
        info "Frontend was not running"
    fi
    rm -f "$PID_DIR/frontend.pid"
else
    info "No frontend PID file found"
fi

# ─────────────────────────────────────────────────────────
# 2. Kill backend
# ─────────────────────────────────────────────────────────
step "Stopping backend..."
if [ -f "$PID_DIR/backend.pid" ]; then
    bpid=$(cat "$PID_DIR/backend.pid" 2>/dev/null || true)
    if [ -n "$bpid" ] && kill -0 "$bpid" 2>/dev/null; then
        kill "$bpid" 2>/dev/null || true
        kill -- -"$bpid" 2>/dev/null || true
        success "Backend stopped (PID: $bpid)"
    else
        info "Backend was not running"
    fi
    rm -f "$PID_DIR/backend.pid"
else
    info "No backend PID file found"
fi

# ─────────────────────────────────────────────────────────
# 3. Stop Cloudflare tunnel
# ─────────────────────────────────────────────────────────
step "Stopping Cloudflare tunnel..."
if [ -f "$PID_DIR/cloudflared.pid" ]; then
    cpid=$(cat "$PID_DIR/cloudflared.pid" 2>/dev/null || true)
    if [ -n "$cpid" ] && kill -0 "$cpid" 2>/dev/null; then
        kill "$cpid" 2>/dev/null || true
        kill -- -"$cpid" 2>/dev/null || true
        success "Cloudflare tunnel stopped (PID: $cpid)"
    else
        info "Cloudflare tunnel was not running"
    fi
    rm -f "$PID_DIR/cloudflared.pid"
else
    info "No cloudflared PID file found"
fi

# ─────────────────────────────────────────────────────────
# 4. Stop Docker infrastructure
# ─────────────────────────────────────────────────────────
step "Stopping Docker infrastructure..."

if command -v docker &>/dev/null && docker info &>/dev/null; then
    # Stop dev compose
    if [ -f "$SCRIPT_DIR/Docker/docker-compose.dev.yml" ]; then
        docker compose -f "$SCRIPT_DIR/Docker/docker-compose.dev.yml" down 2>&1 | while read -r line; do
            info "$line"
        done
        success "Dev Docker containers stopped"
    fi

    # Also stop full compose if running
    if [ -f "$SCRIPT_DIR/Docker/docker-compose.yml" ]; then
        docker compose -f "$SCRIPT_DIR/Docker/docker-compose.yml" down 2>&1 | while read -r line; do
            info "$line"
        done
        success "Full Docker containers stopped"
    fi
else
    info "Docker not found — skipping Docker shutdown"
fi

# ─────────────────────────────────────────────────────────
# 5. Cleanup
# ─────────────────────────────────────────────────────────
step "Cleaning up..."
rm -rf "$LOG_DIR" 2>/dev/null || true
rm -f "$PID_DIR"/*.pid 2>/dev/null || true
success "PID files and logs cleaned"

echo ""
echo -e "${GREEN}${BOLD}  ╔═══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}  ║           RxTract stopped. Goodbye!           ║${NC}"
echo -e "${GREEN}${BOLD}  ╚═══════════════════════════════════════════════╝${NC}"
echo ""
