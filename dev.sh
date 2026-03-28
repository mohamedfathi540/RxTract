#!/usr/bin/env bash

# Re-exec under bash if invoked via sh.
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

set -euo pipefail
export COMPOSE_PROJECT_NAME=rxtract

# Parse arguments (Removed -d as it is now the default behavior)
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            echo "Usage: $0"
            echo "Starts the RxTract development environment in the background."
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# ─────────────────────────────────────────────────────────
# RxTract Development Environment
# Hybrid mode: Docker for infra, local for app
# ─────────────────────────────────────────────────────────

# Colors & formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="/tmp/rxtract"
LOG_DIR="/tmp/rxtract/logs"
BACKEND_PID="$PID_DIR/backend.pid"
FRONTEND_PID="$PID_DIR/frontend.pid"
CLOUDFLARED_PID="$PID_DIR/cloudflared.pid"

# Ports
PORT_POSTGRES=5436
PORT_QDRANT=6337
PORT_BACKEND=8001
PORT_FRONTEND=5777
PORT_NGINX=8899

# Guard against repeated cleanup
CLEANING_UP=false

# ─────────────────────────────────────────────────────────
# ASCII Banner
# ─────────────────────────────────────────────────────────
banner() {
    echo ""
    echo -e "${MAGENTA}${BOLD}"
    echo "  ╔═══════════════════════════════════════════════════════════════════════╗"
    echo "  ║                                                                       ║"
    echo "  ║   ██████╗ ██╗  ██╗████████╗██████╗  █████╗  ██████╗████████╗          ║"
    echo "  ║   ██╔══██╗╚██╗██╔╝╚══██╔══╝██╔══██╗██╔══██╗██╔════╝╚══██╔══╝          ║"
    echo "  ║   ██████╔╝ ╚███╔╝    ██║   ██████╔╝███████║██║        ██║             ║"
    echo "  ║   ██╔══██╗ ██╔██╗    ██║   ██╔══██╗██╔══██║██║        ██║             ║"
    echo "  ║   ██║  ██║██╔╝ ██╗   ██║   ██║  ██║██║  ██║╚██████╗   ██║             ║"
    echo "  ║   ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝   ╚═╝             ║"
    echo "  ║                                                                       ║"
    echo "  ║                  Development Environment                              ║"
    echo "  ╚═══════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
}

# ─────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────
step() {
    echo -e "\n${CYAN}${BOLD}▸ $1${NC}"
}

success() {
    echo -e "  ${GREEN}+${NC} $1"
}

warn() {
    echo -e "  ${YELLOW}!${NC} $1"
}

fail() {
    echo -e "  ${RED}x${NC} $1"
}

info() {
    echo -e "  ${DIM}$1${NC}"
}

# ─────────────────────────────────────────────────────────
# Kill any previous RxTract processes by PID file
# ─────────────────────────────────────────────────────────
kill_previous() {
    step "Cleaning up any previous sessions..."

    if [ -f "$BACKEND_PID" ]; then
        local bpid
        bpid=$(cat "$BACKEND_PID" 2>/dev/null || true)
        if [ -n "$bpid" ] && kill -0 "$bpid" 2>/dev/null; then
            kill "$bpid" 2>/dev/null || true
            kill -- -"$bpid" 2>/dev/null || true
            success "Killed previous backend (PID: $bpid)"
        fi
        rm -f "$BACKEND_PID"
    fi

    if [ -f "$FRONTEND_PID" ]; then
        local fpid
        fpid=$(cat "$FRONTEND_PID" 2>/dev/null || true)
        if [ -n "$fpid" ] && kill -0 "$fpid" 2>/dev/null; then
            kill "$fpid" 2>/dev/null || true
            kill -- -"$fpid" 2>/dev/null || true
            success "Killed previous frontend (PID: $fpid)"
        fi
        rm -f "$FRONTEND_PID"
    fi
    # Forcefully clear the required ports if they are still held
    for port in "$PORT_BACKEND" "$PORT_FRONTEND" "$PORT_NGINX"; do
        if command -v lsof &>/dev/null; then
            pids=$(lsof -t -i:"$port" 2>/dev/null || true)
            if [ -z "$pids" ]; then
                pids=$(sudo -n lsof -t -i:"$port" 2>/dev/null || true)
            fi
            if [ -n "$pids" ]; then
                warn "Port $port is still occupied by PID(s): $pids. Force killing..."
                echo "$pids" | xargs -r kill -9 2>/dev/null || true
                sudo -n kill -9 $pids 2>/dev/null || true
            fi
        fi
    done

    if [ -f "$CLOUDFLARED_PID" ]; then
        local cpid
        cpid=$(cat "$CLOUDFLARED_PID" 2>/dev/null || true)
        if [ -n "$cpid" ] && kill -0 "$cpid" 2>/dev/null; then
            kill "$cpid" 2>/dev/null || true
            kill -- -"$cpid" 2>/dev/null || true
            success "Killed previous cloudflared tunnel (PID: $cpid)"
        fi
        rm -f "$CLOUDFLARED_PID"
    fi

    success "Clean slate ready"
}

# ─────────────────────────────────────────────────────────
# Cleanup handler (Ctrl+C) — runs only ONCE
# ─────────────────────────────────────────────────────────
cleanup() {
    # Guard: only run once
    if $CLEANING_UP; then
        exit 1
    fi
    CLEANING_UP=true

    # Ignore further signals during cleanup
    trap '' SIGINT SIGTERM

    echo ""
    step "Shutting down RxTract..."

    # Kill frontend
    if [ -f "$FRONTEND_PID" ]; then
        local fpid
        fpid=$(cat "$FRONTEND_PID" 2>/dev/null || true)
        if [ -n "$fpid" ] && kill -0 "$fpid" 2>/dev/null; then
            kill "$fpid" 2>/dev/null || true
            kill -- -"$fpid" 2>/dev/null || true
            success "Frontend stopped"
        fi
        rm -f "$FRONTEND_PID"
    fi
    # Force kill leftover ports to prevent orphaned background processes
    for port in "$PORT_BACKEND" "$PORT_FRONTEND"; do
        if command -v lsof &>/dev/null; then
            pids=$(lsof -t -i:"$port" 2>/dev/null || true)
            if [ -z "$pids" ]; then
                pids=$(sudo -n lsof -t -i:"$port" 2>/dev/null || true)
            fi
            if [ -n "$pids" ]; then
                echo "$pids" | xargs -r kill -9 2>/dev/null || true
                sudo -n kill -9 $pids 2>/dev/null || true
            fi
        fi
    done

    # Kill backend
    if [ -f "$BACKEND_PID" ]; then
        local bpid
        bpid=$(cat "$BACKEND_PID" 2>/dev/null || true)
        if [ -n "$bpid" ] && kill -0 "$bpid" 2>/dev/null; then
            kill "$bpid" 2>/dev/null || true
            kill -- -"$bpid" 2>/dev/null || true
            success "Backend stopped"
        fi
        rm -f "$BACKEND_PID"
    fi

    # Kill cloudflared tunnel
    if [ -f "$CLOUDFLARED_PID" ]; then
        local cpid
        cpid=$(cat "$CLOUDFLARED_PID" 2>/dev/null || true)
        if [ -n "$cpid" ] && kill -0 "$cpid" 2>/dev/null; then
            kill "$cpid" 2>/dev/null || true
            kill -- -"$cpid" 2>/dev/null || true
            success "Cloudflare tunnel stopped"
        fi
        rm -f "$CLOUDFLARED_PID"
    fi

    # Stop Docker infra
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        docker compose -f "$SCRIPT_DIR/Docker/docker-compose.dev.yml" down 2>/dev/null || true
        success "Docker infra stopped"
    fi

    # Clean up logs
    rm -rf "$LOG_DIR" 2>/dev/null || true

    echo -e "\n${GREEN}${BOLD}  RxTract shut down cleanly. See you!${NC}\n"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────
banner

# Create dirs
mkdir -p "$PID_DIR" "$LOG_DIR"

# Load Cloudflare token from SRC/.env if not provided in shell env.
if [ -z "${CLOUDFLARE_TUNNEL_TOKEN:-}" ] && [ -f "$SCRIPT_DIR/SRC/.env" ]; then
    token_line=$(grep -E '^[[:space:]]*CLOUDFLARE_TUNNEL_TOKEN[[:space:]]*=' "$SCRIPT_DIR/SRC/.env" | tail -1 || true)
    if [ -n "$token_line" ]; then
        CLOUDFLARE_TUNNEL_TOKEN=$(echo "$token_line" | sed -E 's/^[[:space:]]*CLOUDFLARE_TUNNEL_TOKEN[[:space:]]*=[[:space:]]*//; s/^"//; s/"$//')
        export CLOUDFLARE_TUNNEL_TOKEN
        info "Loaded Cloudflare tunnel token from SRC/.env"
    fi
fi

# 0. Kill previous sessions
kill_previous

# 1. Docker infrastructure
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    COMPOSE_FILE="$SCRIPT_DIR/Docker/docker-compose.dev.yml"
    step "Starting Docker infrastructure (pgvector + qdrant + nginx proxy)..."
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans 2>&1 | while read -r line; do
        info "$line"
    done

    # Wait for PostgreSQL to be healthy
    pg_ready=false
    echo -ne "  ${DIM}Waiting for PostgreSQL to be ready"
    for i in $(seq 1 60); do
        pg_container_id=$(docker compose -f "$COMPOSE_FILE" ps -q pgvector 2>/dev/null || true)
        if [ -n "$pg_container_id" ] && docker exec "$pg_container_id" pg_isready -U postgres &>/dev/null; then
            echo -e "${NC}"
            success "PostgreSQL (pgvector) is ready on port $PORT_POSTGRES"
            pg_ready=true
            break
        fi
        echo -ne "."
        sleep 2
        if [ "$i" -eq 60 ]; then
            echo -e "${NC}"
            warn "PostgreSQL did not become ready"
        fi
    done

    if [ "$pg_ready" != true ]; then
        fail "PostgreSQL is unhealthy. Backend startup cancelled."
        exit 1
    fi

    # Check Qdrant
    for i in $(seq 1 15); do
        if curl -sf --connect-timeout 2 http://localhost:$PORT_QDRANT/healthz &>/dev/null || \
           curl -sf --connect-timeout 2 http://localhost:$PORT_QDRANT/ &>/dev/null; then
            success "Qdrant is ready on port $PORT_QDRANT"
            break
        fi
        sleep 2
    done

    # Check Nginx container state in hybrid mode
    for i in $(seq 1 10); do
        nginx_container_id=$(docker compose -f "$COMPOSE_FILE" ps -q rxtract_nginx_dev 2>/dev/null || true)
        if [ -n "$nginx_container_id" ] && docker inspect -f '{{.State.Running}}' "$nginx_container_id" 2>/dev/null | grep -q true; then
            success "Nginx proxy is running on port $PORT_NGINX"
            break
        fi
        sleep 1
    done
else
    step "Docker not found — skipping infrastructure containers"
    warn "pgvector, qdrant, and nginx proxy will not be started"
fi

# 2. Run database migrations before starting backend
step "Running database migrations..."
export DATABASE_URL="postgresql://postgres:postgres@localhost:5436/minirag"
ALEMBIC_CONFIG="$SCRIPT_DIR/SRC/Models/DB_Schemes/minirag/alembic.ini"

cd "$SCRIPT_DIR/SRC/Models/DB_Schemes/minirag"

if [ -x "$SCRIPT_DIR/SRC/.venv/bin/alembic" ]; then
    "$SCRIPT_DIR/SRC/.venv/bin/alembic" -c "$ALEMBIC_CONFIG" upgrade head
else
    alembic -c "$ALEMBIC_CONFIG" upgrade head
fi

cd "$SCRIPT_DIR/SRC"

# Ensure backend env file exists
ENV_FILE="$SCRIPT_DIR/SRC/.env"
if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$SCRIPT_DIR/SRC/.env.example" ]; then
        cp "$SCRIPT_DIR/SRC/.env.example" "$ENV_FILE"
        PG_ENV_FILE="$SCRIPT_DIR/Docker/env/.env.postgres"
        if [ -f "$PG_ENV_FILE" ]; then
            pg_user=$(grep -E '^POSTGRES_USER=' "$PG_ENV_FILE" | tail -1 | cut -d'=' -f2-)
            pg_pass=$(grep -E '^POSTGRES_PASSWORD=' "$PG_ENV_FILE" | tail -1 | cut -d'=' -f2-)
            pg_db=$(grep -E '^POSTGRES_DB=' "$PG_ENV_FILE" | tail -1 | cut -d'=' -f2-)

            [ -n "$pg_user" ] && sed -i -E "s|^POSTGRES_USER\s*=.*$|POSTGRES_USER = \"$pg_user\"|" "$ENV_FILE"
            [ -n "$pg_pass" ] && sed -i -E "s|^POSTGRES_PASSWORD\s*=.*$|POSTGRES_PASSWORD = \"$pg_pass\"|" "$ENV_FILE"
            [ -n "$pg_db" ] && sed -i -E "s|^POSTGRES_MAIN_DB\s*=.*$|POSTGRES_MAIN_DB = \"$pg_db\"|" "$ENV_FILE"
        fi
        warn "SRC/.env was missing. Created from SRC/.env.example"
    else
        fail "Missing SRC/.env and SRC/.env.example"
        exit 1
    fi
fi

# Fail fast with clear guidance when required keys are absent.
missing_keys=()
for key in APP_NAME APP_VERSION POSTGRES_USER POSTGRES_PASSWORD POSTGRES_MAIN_DB GENRATION_BACKEND EMBEDDING_BACKEND VECTORDB_BACKEND VECTORDB_PATH; do
    if ! grep -Eq "^[[:space:]]*${key}[[:space:]]*=[[:space:]]*.+$" "$ENV_FILE"; then
        missing_keys+=("$key")
    fi
done

if [ ${#missing_keys[@]} -gt 0 ]; then
    fail "SRC/.env is missing required keys: ${missing_keys[*]}"
    exit 1
fi

export POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
export POSTGRES_PORT="${POSTGRES_PORT:-$PORT_POSTGRES}"

# NOTE: </dev/null is added below to stop the processes from dying on terminal exit
if [ -x ".venv/bin/python" ]; then
    nohup .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port "$PORT_BACKEND" --reload --reload-exclude '.venv' \
        </dev/null > "$LOG_DIR/backend.log" 2>&1 &
elif command -v uv &>/dev/null; then
    info "No local .venv found. Syncing backend dependencies with uv..."
    uv sync --no-dev > "$LOG_DIR/backend.log" 2>&1
    nohup uv run --no-sync uvicorn main:app --host 0.0.0.0 --port "$PORT_BACKEND" --reload --reload-exclude '.venv' \
        </dev/null >> "$LOG_DIR/backend.log" 2>&1 &
else
    nohup python -m uvicorn main:app --host 0.0.0.0 --port "$PORT_BACKEND" --reload --reload-exclude '.venv' \
        </dev/null > "$LOG_DIR/backend.log" 2>&1 &
fi
echo $! > "$BACKEND_PID"
success "Backend starting (PID: $(cat "$BACKEND_PID"))"

# Wait for backend
echo -ne "  ${DIM}Waiting for backend"
for i in $(seq 1 120); do
    bpid=$(cat "$BACKEND_PID" 2>/dev/null || true)
    if [ -n "$bpid" ] && ! kill -0 "$bpid" 2>/dev/null; then
        echo -e "${NC}"
        fail "Backend process died! Check log:"
        tail -5 "$LOG_DIR/backend.log" 2>/dev/null | while read -r line; do
            info "$line"
        done
        break
    fi
    if grep -q "Application startup complete" "$LOG_DIR/backend.log" 2>/dev/null; then
        echo -e "${NC}"
        success "Backend is up! → http://localhost:${PORT_BACKEND}/docs"
        break
    fi
    if curl -sf --connect-timeout 2 "http://localhost:${PORT_BACKEND}/docs" >/dev/null 2>&1; then
        echo -e "${NC}"
        success "Backend is up! → http://localhost:${PORT_BACKEND}/docs"
        break
    fi
    echo -ne "."
    sleep 2
done

# 4. Optional Cloudflare tunnel (also with </dev/null added)
if command -v cloudflared &>/dev/null; then
    if [ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
        step "Starting Cloudflare tunnel..."
        nohup cloudflared tunnel run --token "$CLOUDFLARE_TUNNEL_TOKEN" </dev/null > "$LOG_DIR/cloudflared.log" 2>&1 &
        cloudflared_pid="$!"
        echo "$cloudflared_pid" > "$CLOUDFLARED_PID"
        success "Cloudflare tunnel starting (PID: $cloudflared_pid)"
    else
        info "Cloudflare tunnel skipped (set CLOUDFLARE_TUNNEL_TOKEN to enable)"
    fi
fi

# 3. Frontend (Vite)
step "Starting Vite frontend on port $PORT_FRONTEND..."
cd "$SCRIPT_DIR/frontend"

# Install deps if needed
if [ ! -d "node_modules" ]; then
    info "Installing frontend dependencies..."
    pnpm install --frozen-lockfile 2>&1 | tail -1
fi

# Load NVM and run
if [ -s "$HOME/.nvm/nvm.sh" ]; then
    source "$HOME/.nvm/nvm.sh"
    nvm use 22 || nvm install 22
fi

# NOTE: </dev/null added here as well
nohup pnpm dev --host 0.0.0.0 </dev/null > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$FRONTEND_PID"
success "Frontend starting (PID: $(cat "$FRONTEND_PID"))"

# Wait for frontend
echo -ne "  ${DIM}Waiting for frontend"
for i in $(seq 1 60); do
    fpid=$(cat "$FRONTEND_PID" 2>/dev/null || true)
    if [ -n "$fpid" ] && ! kill -0 "$fpid" 2>/dev/null; then
        echo -e "${NC}"
        fail "Frontend process died! Check log:"
        tail -5 "$LOG_DIR/frontend.log" 2>/dev/null | while read -r line; do
            info "$line"
        done
        break
    fi
    if grep -q "Local:" "$LOG_DIR/frontend.log" 2>/dev/null; then
        echo -e "${NC}"
        success "Frontend is up! → http://localhost:${PORT_FRONTEND}"
        break
    fi
    if curl -sf --connect-timeout 2 "http://localhost:${PORT_FRONTEND}" >/dev/null 2>&1; then
        echo -e "${NC}"
        success "Frontend is up! → http://localhost:${PORT_FRONTEND}"
        break
    fi
    echo -ne "."
    sleep 2
done

# ─────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────
# Calculate dynamic padding ensuring exact 47 char inner width
pad_nginx=$(( 47 - 35 - ${#PORT_NGINX} )); (( pad_nginx < 0 )) && pad_nginx=0
pad_front=$(( 47 - 35 - ${#PORT_FRONTEND} )); (( pad_front < 0 )) && pad_front=0
pad_back=$(( 47 - 40 - ${#PORT_BACKEND} )); (( pad_back < 0 )) && pad_back=0
pad_pg=$(( 47 - 28 - ${#PORT_POSTGRES} )); (( pad_pg < 0 )) && pad_pg=0
pad_qd=$(( 47 - 35 - ${#PORT_QDRANT} )); (( pad_qd < 0 )) && pad_qd=0

printf -v sp_nginx '%*s' "$pad_nginx" ''
printf -v sp_front '%*s' "$pad_front" ''
printf -v sp_back '%*s' "$pad_back" ''
printf -v sp_pg '%*s' "$pad_pg" ''
printf -v sp_qd '%*s' "$pad_qd" ''

echo ""
echo -e "${GREEN}${BOLD}  ╔═══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}  ║            RxTract is LIVE!                   ║${NC}"
echo -e "${GREEN}${BOLD}  ╠═══════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}${BOLD}  ║${NC}                                               ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}  ║${NC}  ${CYAN}Nginx Gateway${NC} → ${WHITE}http://localhost:${PORT_NGINX}${NC}${sp_nginx}${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}  ║${NC}  ${CYAN}Frontend     ${NC} → ${WHITE}http://localhost:${PORT_FRONTEND}${NC}${sp_front}${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}  ║${NC}  ${CYAN}Backend API  ${NC} → ${WHITE}http://localhost:${PORT_BACKEND}/docs${NC}${sp_back}${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}  ║${NC}  ${CYAN}PostgreSQL   ${NC} → ${WHITE}localhost:${PORT_POSTGRES}${NC}${sp_pg}${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}  ║${NC}  ${CYAN}Qdrant       ${NC} → ${WHITE}http://localhost:${PORT_QDRANT}${NC}${sp_qd}${GREEN}${BOLD}║${NC}"
if [ -f "$CLOUDFLARED_PID" ]; then
    pad_cf=$(( 47 - 43 )); (( pad_cf < 0 )) && pad_cf=0
    printf -v sp_cf '%*s' "$pad_cf" ''
    echo -e "${GREEN}${BOLD}  ║${NC}  ${CYAN}Cloudflare   ${NC} → ${WHITE}Tunnel enabled (see logs)${NC}${sp_cf}${GREEN}${BOLD}║${NC}"
fi
echo -e "${GREEN}${BOLD}  ║${NC}                                               ${GREEN}${BOLD}║${NC}"
echo -e "${GREEN}${BOLD}  ╚═══════════════════════════════════════════════╝${NC}"
echo ""

# ─────────────────────────────────────────────────────────
# Background mode — completely detach and exit
# ─────────────────────────────────────────────────────────
echo -e "\n${GREEN}${BOLD}  RxTract is now running in the background${NC}"
echo -e "  ${DIM}Logs:${NC}"
echo -e "    ${WHITE}Backend  → $LOG_DIR/backend.log${NC}"
echo -e "    ${WHITE}Frontend → $LOG_DIR/frontend.log${NC}"
if [ -f "$CLOUDFLARED_PID" ]; then
echo -e "    ${WHITE}Tunnel   → $LOG_DIR/cloudflared.log${NC}"
fi
echo -e "\n  ${DIM}To tail logs:${NC}"
echo -e "  ${WHITE}tail -f $LOG_DIR/backend.log $LOG_DIR/frontend.log${NC}"
echo -e "\n  ${DIM}To stop all services manually:${NC}"
echo -e "  ${WHITE}kill \$(cat /tmp/rxtract/backend.pid 2>/dev/null) \$(cat /tmp/rxtract/frontend.pid 2>/dev/null) \$(cat /tmp/rxtract/cloudflared.pid 2>/dev/null) 2>/dev/null || true${NC}\n"

# Disown all background jobs so they survive shell exit/SIGHUP
disown -a 2>/dev/null || true

# Disable the cleanup trap so exiting dev.sh doesn't accidentally kill the processes
trap - SIGINT SIGTERM

echo -e "${GREEN}${BOLD}  Setup complete. You can safely close this terminal.${NC}\n"
exit 0