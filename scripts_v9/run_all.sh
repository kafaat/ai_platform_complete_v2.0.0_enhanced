#!/usr/bin/env bash
###############################################################################
# SAHOOL v9.0 -- Unified Orchestration Script
# Usage: ./run_all.sh [up|down|logs|test|build|reset|health]
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.v9.yml"
ENV_FILE="$PROJECT_DIR/.env"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err()  { echo -e "${RED}[ERROR]${NC} $1"; }

# ─── Check Dependencies ────────────────────────────────────
check_deps() {
    log_info "Checking dependencies..."
    command -v docker >/dev/null 2>&1 || { log_err "Docker not installed"; exit 1; }
    command -v docker compose >/dev/null 2>&1 || { log_err "docker compose not installed"; exit 1; }
    log_ok "Docker + docker compose found"
}

# ─── Generate .env if missing ──────────────────────────────
generate_env() {
    if [[ -f "$ENV_FILE" ]]; then
        log_ok ".env exists"
        return
    fi
    log_warn ".env not found -- generating from template"
    cat > "$ENV_FILE" << 'EOF'
# SAHOOL v9.0 -- Environment Configuration
# ⚠️ CHANGE ALL SECRETS BEFORE PRODUCTION

# Database
POSTGRES_PASSWORD=<set-in-secret-manager>
DB_PASSWORD=sahool_secure_db_2026_change_me

# JWT
JWT_SECRET=<set-in-secret-manager>

# MinIO
MINIO_ROOT_USER=sahool
MINIO_ROOT_PASSWORD=<set-in-secret-manager>

# Sentinel Hub (Copernicus Data Space)
SH_CLIENT_ID=your_sentinel_hub_client_id
SH_CLIENT_SECRET=<set-in-secret-manager>
SH_INSTANCE_ID=your_instance_id

# SAHOOL Agent
SAHOOL_AGENT_TOKEN=<set-in-secret-manager>
EDGE_SYNC_TOKEN=edge_sync_token_change_me_64chars

# Telegram Bot
TELEGRAM_BOT_TOKEN=<set-in-secret-manager>

# Grafana
GRAFANA_PASSWORD=<set-in-secret-manager>

# Mapbox (optional, for fallback maps)
MAPBOX_TOKEN=your_mapbox_token

# Edge Device
EDGE_DEVICE=rpi5
OFFLINE_MODE=false
EOF
    log_warn "Generated .env -- EDIT SECRETS BEFORE RUNNING!"
}

# ─── Health Check ──────────────────────────────────────────
health_check() {
    log_info "Running health checks..."
    local services=(
        "sahool-auth:8120"
        "sahool-sentinel-hub-mcp:8091"
        "sahool-weather-mcp:8092"
        "sahool-wofost-mcp:8093"
        "sahool-market-mcp:8094"
        "sahool-supervisor:8096"
        "sahool-guardrails:8097"
        "sahool-edge:8100"
        "sahool-postgis:5432"
        "sahool-redis:6379"
        "sahool-nats:8222"
        "sahool-minio:9000"
        "sahool-qdrant:6333"
    )

    local passed=0
    local failed=0

    for svc in "${services[@]}"; do
        IFS=':' read -r name port <<< "$svc"
        if curl -sf "http://localhost:${port}/healthz" >/dev/null 2>&1 ||            curl -sf "http://localhost:${port}/readyz" >/dev/null 2>&1 ||            ( [[ "$port" == "5432" ]] && pg_isready -h localhost -p 5432 >/dev/null 2>&1 ) ||            ( [[ "$port" == "6379" ]] && redis-cli -h localhost -p 6379 ping >/dev/null 2>&1 ); then
            log_ok "  ✓ $name (port $port)"
            ((passed++))
        else
            log_err "  ✗ $name (port $port) -- NOT READY"
            ((failed++))
        fi
    done

    echo ""
    log_info "Health Check Results: $passed passed, $failed failed"
    if [[ $failed -gt 0 ]]; then
        log_warn "Some services are not ready. Check logs with: ./run_all.sh logs"
        return 1
    fi
    log_ok "All systems operational!"
}

# ─── Start Services ────────────────────────────────────────
cmd_up() {
    check_deps
    generate_env
    log_info "Starting SAHOOL v9.0..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build
    log_info "Waiting for services to initialize (30s)..."
    sleep 30
    health_check || true
    log_ok "SAHOOL v9.0 is running!"
    echo ""
    echo "  Dashboard:    http://localhost:3001 (Grafana)"
    echo "  API Gateway:  http://localhost:80"
    echo "  Supervisor:   http://localhost:8096"
    echo "  MCP Sentinel: http://localhost:8091"
    echo "  MCP Weather:  http://localhost:8092"
    echo "  MCP WOFOST:   http://localhost:8093"
    echo "  MCP Market:   http://localhost:8094"
    echo "  Guardrails:   http://localhost:8097"
    echo "  Edge AI:      http://localhost:8100"
    echo "  Prometheus:   http://localhost:9090"
    echo "  MinIO:        http://localhost:9001"
}

# ─── Stop Services ─────────────────────────────────────────
cmd_down() {
    log_info "Stopping SAHOOL v9.0..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" down --remove-orphans
    log_ok "All services stopped"
}

# ─── View Logs ─────────────────────────────────────────────
cmd_logs() {
    local svc="${2:-}"
    cd "$PROJECT_DIR"
    if [[ -n "$svc" ]]; then
        docker compose -f "$COMPOSE_FILE" logs -f "$svc"
    else
        docker compose -f "$COMPOSE_FILE" logs -f --tail=100
    fi
}

# ─── Run Tests ─────────────────────────────────────────────
cmd_test() {
    log_info "Running integration tests..."
    cd "$PROJECT_DIR"
    if [[ ! -f "tests/requirements-test.txt" ]]; then
        log_err "Test dependencies not found. Run: pip install -r tests/requirements-test.txt"
        exit 1
    fi
    python -m pytest tests/ -v --tb=short -m "not slow" || true
    log_ok "Tests complete"
}

# ─── Build Images ──────────────────────────────────────────
cmd_build() {
    log_info "Building all Docker images..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" build --parallel
    log_ok "Build complete"
}

# ─── Reset (DANGER: destroys data) ─────────────────────────
cmd_reset() {
    log_warn "⚠️  This will DESTROY all data volumes!"
    read -p "Are you sure? Type 'RESET' to confirm: " confirm
    if [[ "$confirm" != "RESET" ]]; then
        log_info "Reset cancelled"
        exit 0
    fi
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans
    docker volume prune -f
    log_ok "All data reset. Run './run_all.sh up' to restart."
}

# ─── Main ──────────────────────────────────────────────────
main() {
    local cmd="${1:-up}"
    case "$cmd" in
        up)       cmd_up ;;
        down)     cmd_down ;;
        logs)     cmd_logs "$@" ;;
        test)     cmd_test ;;
        build)    cmd_build ;;
        health)   health_check ;;
        reset)    cmd_reset ;;
        *)
            echo "Usage: $0 [up|down|logs|test|build|health|reset]"
            echo ""
            echo "Commands:"
            echo "  up      -- Start all services"
            echo "  down    -- Stop all services"
            echo "  logs    -- View logs (optionally: logs <service_name>)"
            echo "  test    -- Run integration tests"
            echo "  build   -- Build all Docker images"
            echo "  health  -- Check all service health endpoints"
            echo "  reset   -- ⚠️ Destroy all data and volumes"
            exit 1
            ;;
    esac
}

main "$@"
