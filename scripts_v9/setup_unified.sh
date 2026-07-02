#!/usr/bin/env bash
# SAHOOL v9.1 — Unified Production Setup Script
# One-command deployment of ALL services (Edge + AI/GIS + Odoo + Market + AgriAI)
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }
hdr()  { echo -e "\n${CYAN}${BOLD}── $1 ──${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE="docker compose -f $PROJECT_DIR/docker-compose.unified.yml"
ENV_FILE="$PROJECT_DIR/.env"

echo -e "${GREEN}${BOLD}"
echo "  ╔═══════════════════════════════════════════════════════════════════╗"
echo "  ║  🌿 SAHOOL v9.1 — UNIFIED PRODUCTION SETUP                        ║"
echo "  ║  Edge + AI/GIS + Odoo ERP + Market + AgriAI Engine              ║"
echo "  ║  20+ Services | 5 Layers | One Command                          ║"
echo -e "  ╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ─── Check Dependencies ──────────────────────────────────────
hdr "Checking Dependencies"
command -v docker &>/dev/null || err "Docker not installed"
command -v docker compose &>/dev/null || err "docker compose (v2) not installed"
command -v openssl &>/dev/null || warn "openssl not found — secrets will use /dev/urandom"
log "Docker OK"

# ─── Generate .env ─────────────────────────────────────────
hdr "Environment Configuration"
if [[ ! -f "$ENV_FILE" ]]; then
    warn ".env not found — generating with secure secrets"

    gen_secret() {
        if command -v openssl &>/dev/null; then
            openssl rand -hex 32
        else
            head -c 64 /dev/urandom | xxd -p | tr -d '\n' | head -c 64
        fi
    }

    JWT_SECRET=$(gen_secret)
    DB_PASS=$(openssl rand -base64 24 2>/dev/null || head -c 32 /dev/urandom | base64 | tr -d '=+/\n')
    AGENT_TOKEN=$(gen_secret)
    EDGE_TOKEN=$(gen_secret)
    MINIO_PASS=$(openssl rand -base64 24 2>/dev/null || head -c 32 /dev/urandom | base64 | tr -d '=+/\n')
    WEBHOOK_SECRET=$(gen_secret)

    cat > "$ENV_FILE" << EOF
# ═══════════════════════════════════════════════════════════════════════════════
# SAHOOL v9.1 — Unified Environment Variables
# Generated: $(date -Iseconds)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Core ──
POSTGRES_PASSWORD=$DB_PASS
JWT_SECRET=$JWT_SECRET
SAHOOL_AGENT_TOKEN=$AGENT_TOKEN
EDGE_SYNC_TOKEN=$EDGE_TOKEN

# ── MinIO ──
MINIO_ROOT_USER=sahool
MINIO_ROOT_PASSWORD=$MINIO_PASS

# ── Sentinel Hub ──
SH_CLIENT_ID=your_sentinel_hub_client_id
SH_CLIENT_SECRET=your_sentinel_hub_client_secret
SH_INSTANCE_ID=your_instance_id

# ── Telegram ──
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_from_botfather

# ── Mapbox ──
MAPBOX_TOKEN=your_mapbox_token

# ── Odoo ERP ──
ODOO_URL=http://odoo:8069
ODOO_DB=sahool_erp
ODOO_USER=admin
ODOO_PASSWORD=admin
ODOO_API_KEY=your-odoo-api-key-here
WEBHOOK_SECRET=$WEBHOOK_SECRET

# ── Ollama AI ──
LLM_MODEL=qwen3:32b
EMBED_MODEL=nomic-embed-text
NUM_CTX=8192

# ── Edge Device ──
EDGE_DEVICE=rpi5
OFFLINE_MODE=false

# ── Domain ──
DOMAIN=localhost
EOF
    log ".env generated — EDIT SECRETS before production!"
    echo -e "${YELLOW}⚠️  Required manual edits:${NC}"
    echo "   - SH_CLIENT_ID / SH_CLIENT_SECRET (Sentinel Hub)"
    echo "   - TELEGRAM_BOT_TOKEN (BotFather)"
    echo "   - MAPBOX_TOKEN"
    echo "   - ODOO_API_KEY"
else
    log ".env exists"
fi

# ─── Create data dirs ──────────────────────────────────────
hdr "Creating Data Directories"
mkdir -p "$PROJECT_DIR"/{models,logs,uploads,frontend}
mkdir -p "$PROJECT_DIR"/firmware/esp32_mesh_gateway
mkdir -p "$PROJECT_DIR"/nginx/ssl
log "Directories OK"

# ─── Self-signed SSL (dev) ─────────────────────────────────
if [[ ! -f "$PROJECT_DIR/nginx/ssl/fullchain.pem" ]]; then
    warn "SSL certificates not found — generating self-signed (DEV ONLY)"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048         -keyout "$PROJECT_DIR/nginx/ssl/privkey.pem"         -out "$PROJECT_DIR/nginx/ssl/fullchain.pem"         -subj "/C=AE/ST=Abu Dhabi/L=Abu Dhabi/O=SAHOOL/OU=Dev/CN=localhost"         2>/dev/null || warn "openssl cert generation failed"
fi

# ─── Pull base images ──────────────────────────────────────
hdr "Pulling Base Images"
$COMPOSE pull --quiet 2>/dev/null || true
log "Images pulled"

# ─── Build custom services ─────────────────────────────────
hdr "Building Custom Services"
$COMPOSE build --parallel
log "Build complete"

# ─── Start Infrastructure ────────────────────────────────────
hdr "Layer 1: Starting Infrastructure (PostGIS + Redis + NATS + MinIO + Qdrant)"
$COMPOSE up -d postgis redis nats minio qdrant
sleep 15

echo -n "  ⏳ Waiting for PostgreSQL"
for i in $(seq 1 30); do
    $COMPOSE exec -T postgis pg_isready -U postgres &>/dev/null && { echo -e " ${GREEN}✓${NC}"; break; }
    echo -n "."; sleep 2
done

# ─── Run ALL Migrations ─────────────────────────────────────
hdr "Layer 2: Running Database Migrations"

MIGRATIONS=(
    "v9_new_tables.sql"
    "v9_automation.sql"
    "v9_market.sql"
    "v9_odoo_bridge.sql"
    "v9_agriai.sql"
)

for mig in "${MIGRATIONS[@]}"; do
    if [[ -f "$PROJECT_DIR/migrations/$mig" ]]; then
        echo -n "  Applying $mig ..."
        $COMPOSE exec -T postgis psql -U postgres -d sahool -f "/docker-entrypoint-initdb.d/$mig" &>/dev/null && echo -e " ${GREEN}✓${NC}" || echo -e " ${YELLOW}⚠${NC} (may already exist)"
    else
        warn "$mig not found — skipping"
    fi
done
log "Migrations applied"

# ─── Start Core Services ─────────────────────────────────────
hdr "Layer 3: Starting Core Services (Auth + Supervisor + Guardrails + MCPs)"
$COMPOSE up -d auth-service sentinel-hub-mcp weather-mcp wofost-mcp market-mcp guardrails
sleep 20

# ─── Start AI & RAG ──────────────────────────────────────────
hdr "Layer 4: Starting AI & RAG (Ollama + Local AI + Qdrant)"
$COMPOSE up -d ollama local-ai-rag
sleep 10

# ─── Start AgriAI Engine ─────────────────────────────────────
hdr "Layer 5: Starting AgriAI Engine (Soil + Crops + Irrigation + Pest + Yield)"
$COMPOSE up -d agriai-engine
sleep 10

# ─── Start Edge & IoT ────────────────────────────────────────
hdr "Layer 6: Starting Edge & IoT (Inference + Video + Actuator + FastBee + ZLMediaKit)"
$COMPOSE up -d edge-inference video-processor actuator-service fastbee zlmediakit
sleep 10

# ─── Start Odoo Bridge ───────────────────────────────────────
hdr "Layer 7: Starting Odoo ERP Bridge"
$COMPOSE up -d erp-bridge
sleep 5

# ─── Start Frontend & Bots ──────────────────────────────────
hdr "Layer 8: Starting Frontend & Notifications"
$COMPOSE up -d frontend telegram-bot

# ─── Health Check ───────────────────────────────────────────
hdr "Layer 9: Health Check"
ENDPOINTS=(
    "8120:auth"
    "8096:supervisor"
    "8091:sentinel-mcp"
    "8092:weather-mcp"
    "8093:wofost-mcp"
    "8094:market-mcp"
    "8097:guardrails"
    "8100:edge-inference"
    "8110:video-processor"
    "8111:actuator"
    "8081:fastbee"
    "8082:zlmediakit"
    "8125:local-ai-rag"
    "8126:erp-bridge"
    "8127:agriai-engine"
)

FAILED=0
for ep in "${ENDPOINTS[@]}"; do
    IFS=':' read -r port name <<< "$ep"
    if curl -sf "http://localhost:${port}/healthz" &>/dev/null || curl -sf "http://localhost:${port}/health" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $name (:$port)"
    else
        echo -e "  ${YELLOW}⚠${NC} $name (:$port) — check logs: $COMPOSE logs $name | tail -20"
        ((FAILED++))
    fi
done

# ─── Summary ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  SAHOOL v9.1 UNIFIED is running!${NC}"
echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${CYAN}Web UI:${NC}       https://localhost (Nginx → Frontend)"
echo -e "  ${CYAN}API Gateway:${NC}  https://localhost/auth/ (Auth Service)"
echo -e "  ${CYAN}Agent:${NC}        https://localhost/api/agent/ (Supervisor)"
echo -e "  ${CYAN}AgriAI:${NC}       https://localhost/api/agriai/ (5 Models)"
echo -e "  ${CYAN}RAG AI:${NC}        https://localhost/api/rag/ (Qwen3 + Qdrant)"
echo -e "  ${CYAN}Market:${NC}        https://localhost/api/market/ (B2B Marketplace)"
echo -e "  ${CYAN}ERP Bridge:${NC}  https://localhost/api/odoo/ (ERP Sync)"
echo -e "  ${CYAN}Video:${NC}        https://localhost/api/video/ (RTSP/FLV)"
echo -e "  ${CYAN}Actuator:${NC}     https://localhost/api/actuator/ (Scene Linkage)"
echo -e "  ${CYAN}FastBee MQTT:${NC}  mqtt://localhost:1883 (IoT Broker)"
echo -e "  ${CYAN}ZLMediaKit:${NC}  https://localhost/live/ (WebRTC/FLV)"
echo -e "  ${CYAN}MinIO Console:${NC} http://localhost:9001 (Object Storage)"
echo -e "  ${CYAN}Ollama API:${NC}   http://localhost:11434 (Local LLM)"
echo ""
echo -e "  ${CYAN}Commands:${NC}"
echo "    $COMPOSE ps                    # List all services"
echo "    $COMPOSE logs -f agriai-engine # Watch AgriAI logs"
echo "    $COMPOSE logs -f supervisor    # Watch Agent logs"
echo "    $COMPOSE logs -f erp-bridge # Watch ERP sync"
echo ""
echo -e "  ${YELLOW}⚠️  Next steps:${NC}"
echo "    1. Edit .env and add Sentinel Hub + Telegram + Odoo tokens"
echo "    2. Pull Ollama models: docker exec sahool-ollama ollama pull qwen3:32b"
echo "    3. Flash firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino"
echo "    4. Add RTSP cameras: POST https://localhost/api/video/streams"
echo "    5. Upload agri KB: POST https://localhost/api/rag/ingest"
echo "    6. Create automation rules in automation_rules table"
echo "    7. Connect Odoo: configure ODOO_URL + ODOO_API_KEY"
echo ""

if [[ $FAILED -gt 0 ]]; then
    warn "$FAILED services not ready — check logs above"
    exit 0
fi

log "All systems operational! 🌿"
