#!/bin/bash
# SAHOOL v9.0 — run_all.sh (نهائي مُصلَح)
set -euo pipefail
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }
hdr()  { echo -e "\n${CYAN}${BOLD}── $1 ──${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_DIR="$SCRIPT_DIR"
# الفرونت مدمج داخل المشروع (frontend/) — لا حاجة لمجلّد مجاور
FRONTEND_DIR="$PROD_DIR/frontend"
ENV_FILE="$PROD_DIR/.env"
COMPOSE="docker-compose -f $PROD_DIR/docker-compose.v9.yml"
[[ -f "$ENV_FILE" ]] && COMPOSE="$COMPOSE --env-file $ENV_FILE"

echo -e "${GREEN}${BOLD}"
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║  🌿 SAHOOL v9.0 — الزراعة الذكية اليمنية v9    ║"
echo "  ║  10 إصلاحات حرجة + Supervisor + Guardrails + Edge║"
echo -e "  ╚═══════════════════════════════════════════════════╝${NC}"

setup() {
    hdr "إعداد البيئة"
    for cmd in docker docker-compose; do
        command -v "$cmd" &>/dev/null || err "$cmd مطلوب"
    done
    if [[ ! -f "$ENV_FILE" ]]; then
        cp "$PROD_DIR/.env.example" "$ENV_FILE"
        warn "تم إنشاء .env — عدّل JWT_SECRET: openssl rand -hex 32"
    else
    log ".env موجود ✓"
fi
    # الفرونت مدمج في frontend/ — لا symlink لازم
    if [[ -d "$PROD_DIR/frontend/src" ]]; then
        log "frontend مدمج ✓"
    fi
    mkdir -p "$PROD_DIR"/{certs,models/rl,grafana/provisioning/{dashboards,datasources}}
    # Grafana datasource
    cat > "$PROD_DIR/grafana/provisioning/datasources/prometheus.yml" << 'GFDS'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://sahool-prometheus:9090
    isDefault: true
GFDS
    log "✅ إعداد مكتمل — شغّل: ./run_all.sh"
}

check_jwt() {
    # M20 fix: use set -a / set +a for env files with spaces
set -a; source "$ENV_FILE"; set +a 2>/dev/null || true
    [[ -z "${JWT_SECRET:-}" ]] || [[ "$JWT_SECRET" == *"CHANGE_THIS"* ]] && \
        err "JWT_SECRET غير محدد!\nشغّل: openssl rand -hex 32"
    [[ ${#JWT_SECRET} -lt 32 ]] && warn "JWT_SECRET قصير — يُنصح بـ 64 حرف"
    log "JWT_SECRET ✓"
}

wait_for() {
    local url=$1 name=$2 max=${3:-80}
    echo -n "  ⏳ $name"
    for i in $(seq 1 $max); do
        curl -sf "$url" &>/dev/null && { echo -e " ${GREEN}✓${NC}"; return 0; }
        echo -n "."; sleep 3
    done
    echo -e " ${YELLOW}⚠ timeout${NC}"; return 1
}

start_backend() {
    hdr "تشغيل Docker Compose (v9)"
    cd "$PROD_DIR"
    $COMPOSE pull --quiet 2>/dev/null || true
    $COMPOSE up -d --build
    sleep 20
    hdr "فحص الجاهزية"
    wait_for "http://localhost:8120/readyz" "auth (:8120)"       40 || true
    wait_for "http://localhost:8091/readyz" "indicators (:8091)" 40 || true
    wait_for "http://localhost:8092/readyz" "weather (:8092)"    30 || true
    wait_for "http://localhost:8094/readyz" "soil (:8094)"       30 || true
    wait_for "http://localhost:8090/readyz" "vegetation (:8090)" 30 || true
    wait_for "http://localhost:8123/health" "notification (:8123)"30 || true
    wait_for "http://localhost:8096/health" "supervisor (:8096)" 40 || true
    log "✅ الخدمات جاهزة"
}

start_frontend_dev() {
    hdr "الواجهة الأمامية"
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "sahool-frontend"; then
        log "Frontend يعمل على http://localhost:3000 (Docker)"
        return
    fi
    if [[ -d "$FRONTEND_DIR" ]] && command -v npm &>/dev/null; then
        cd "$FRONTEND_DIR"
        [[ ! -d node_modules ]] && npm install --legacy-peer-deps
        cat > .env.local << 'FE'
VITE_API_URL=http://localhost:8000
VITE_INDICATORS_URL=http://localhost:8091
VITE_VEGETATION_URL=http://localhost:8090
VITE_WEATHER_URL=http://localhost:8092
VITE_SOIL_URL=http://localhost:8094
VITE_AUTH_URL=http://localhost:8120
VITE_WS_URL=ws://localhost:8123/ws/notifications
VITE_MOCK_MODE=false
FE
        nohup npm run dev & echo "$!" > /tmp/sahool_fe.pid
        sleep 3; log "Frontend Dev: http://localhost:5173"
    fi
}

show_status() {
    hdr "حالة SAHOOL v9"
    $COMPOSE ps 2>/dev/null || true
    echo ""
    for chk in \
        "8120:/readyz:auth" \
        "8091:/readyz:indicators" \
        "8090:/readyz:vegetation" \
        "8092:/readyz:weather" \
        "8094:/readyz:soil" \
        "8096:/health:supervisor-agent" \
        "8097:/health:guardrails-engine" \
        "8123:/health:notification" \
        "3000:/index.html:frontend" \
        "9090:/-/healthy:prometheus"; do
        IFS=':' read -r port path name <<< "$chk"
        curl -sf "http://localhost:${port}${path}" &>/dev/null \
            && echo -e "  ${GREEN}✓${NC} $name (:$port)" \
            || echo -e "  ${RED}✗${NC} $name (:$port)"
    done
}

stop_all() {
    hdr "إيقاف"
    [[ -f /tmp/sahool_fe.pid ]] && { kill "$(cat /tmp/sahool_fe.pid)" 2>/dev/null; rm /tmp/sahool_fe.pid; }
    cd "$PROD_DIR" && $COMPOSE down && log "✅ متوقف"
}

print_summary() {
    hdr "SAHOOL v9 جاهز ✅"
    echo ""
    echo -e "  ${CYAN}الواجهة:${NC}   http://localhost:3000 | http://localhost:5173"
    echo -e "  ${CYAN}الدخول:${NC}    admin@sahool.ye / <password from environment or seeded setup>"
    echo ""
    echo -e "  ${CYAN}APIs v8:${NC}   :8120 auth | :8091 indicators | :8090 vegetation"
    echo    "            :8092 weather | :8094 soil"
    echo -e "  ${CYAN}APIs v9:${NC}   :8096 supervisor-agent | :8097 guardrails"
    echo    "            :8123 notifications (WebSocket)"
    echo -e "  ${CYAN}Monitor:${NC}   :9090 prometheus | :3001 grafana | :8222 nats"
    echo ""
    echo -e "  ${CYAN}أوامر:${NC}"
    echo    "    ./run_all.sh --status"
    echo    "    ./run_all.sh --stop"
    echo    "    ./scripts/test_all_agents.sh"
    echo    "    ./scripts/test_events.sh"
    echo ""
}

case "${1:-start}" in
    --setup)      setup ;;
    --stop|stop)  stop_all ;;
    --status)     show_status ;;
    start|*)
        [[ -f "$ENV_FILE" ]] || { warn ".env غير موجود"; setup; }
        check_jwt
        start_backend
        start_frontend_dev
        print_summary
        ;;
esac
