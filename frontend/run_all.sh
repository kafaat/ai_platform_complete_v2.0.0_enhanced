#!/bin/bash
# ══════════════════════════════════════════════════════════════
# SAHOOL v8.0 — سكريبت التشغيل الشامل
# يبني ويشغّل الخلفية + الواجهة الأمامية معاً
#
# الاستخدام:
#   chmod +x run_all.sh
#   ./run_all.sh                    # تشغيل كامل
#   ./run_all.sh --backend-only     # الخلفية فقط
#   ./run_all.sh --frontend-only    # الواجهة فقط
#   ./run_all.sh --stop             # إيقاف كل شيء
#   ./run_all.sh --status           # حالة الخدمات
# ══════════════════════════════════════════════════════════════

set -euo pipefail

# ── الألوان ──────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'

log()     { echo -e "${GREEN}[SAHOOL]${NC} $1"; }
warn()    { echo -e "${YELLOW}[⚠]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
section() { echo -e "\n${BLUE}${BOLD}══════════════════════════════════════${NC}"; echo -e "${CYAN}${BOLD}  $1${NC}"; echo -e "${BLUE}${BOLD}══════════════════════════════════════${NC}"; }

# ── المتغيرات ─────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}"            # الخلفية (docker-compose.yml)
FRONTEND_DIR="${SCRIPT_DIR}/frontend"  # الواجهة (package.json)
ENV_FILE="${SCRIPT_DIR}/.env"

MODE="all"
[[ "${1:-}" == "--backend-only"  ]] && MODE="backend"
[[ "${1:-}" == "--frontend-only" ]] && MODE="frontend"
[[ "${1:-}" == "--stop"          ]] && MODE="stop"
[[ "${1:-}" == "--status"        ]] && MODE="status"

# ══════════════════════════════════════════════════════════════
# وظائف مساعدة
# ══════════════════════════════════════════════════════════════

check_deps() {
    section "فحص الأدوات المطلوبة"
    local missing=()
    for cmd in docker docker-compose node npm curl; do
        if command -v "$cmd" &>/dev/null; then
            log "✓ $cmd متاح"
        else
            missing+=("$cmd")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        error "أدوات ناقصة: ${missing[*]}\nثبّت Docker وNode.js أولاً."
    fi
}

setup_env() {
    section "إعداد متغيرات البيئة"
    if [[ ! -f "$ENV_FILE" ]]; then
        warn "ملف .env غير موجود — إنشاء نسخة افتراضية..."
        cat > "$ENV_FILE" << 'ENVEOF'
# SAHOOL v8.0 — Environment Variables
# عدّل هذه القيم قبل النشر!

POSTGRES_PASSWORD=sahool_secure_pass_2026
REDIS_PASSWORD=redis_secure_pass_2026
MINIO_ROOT_USER=sahool
MINIO_ROOT_PASSWORD=minio_secure_pass_2026
GRAFANA_PASSWORD=grafana_pass_2026

# JWT (أنشئ بـ: openssl rand -hex 32)
JWT_SECRET=change_this_to_a_256bit_random_string_before_deployment

# Copernicus (اختياري - للصور الحقيقية)
COPERNICUS_USER=
COPERNICUS_PASSWORD=

# Claude API (للشات بوت)
VITE_CLAUDE_API_KEY=
ENVEOF
        warn "⚠️  عدّل .env قبل النشر — خاصةً JWT_SECRET وكلمات المرور!"
    else
        log "✓ ملف .env موجود"
    fi
}

wait_for_service() {
    local url=$1 name=$2 max=${3:-60}
    echo -n "  انتظار $name"
    for i in $(seq 1 $max); do
        if curl -sf "$url" &>/dev/null; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 2
    done
    echo -e " ${RED}✗ timeout${NC}"
    return 1
}

# ══════════════════════════════════════════════════════════════
# الوظائف الرئيسية
# ══════════════════════════════════════════════════════════════

start_backend() {
    section "تشغيل الخدمات الخلفية (Docker Compose)"
    cd "$BACKEND_DIR"

    # تطبيق مخطط قاعدة البيانات v8
    if [[ -f "migrations/init_v8.sql" ]]; then
        log "سيتم تطبيق init_v8.sql تلقائياً عند أول تشغيل"
    fi

    log "بناء وتشغيل الحاويات..."
    docker-compose pull --quiet 2>/dev/null || true
    docker-compose up -d --build

    section "انتظار جاهزية الخدمات"
    local services=(
        "http://localhost:5432 PostgreSQL"       # سيُتحقق عبر healthcheck
        "http://localhost:8091/health indicators-service"
        "http://localhost:8090/health vegetation-service"
        "http://localhost:8092/health weather-service"
        "http://localhost:8094/health soil-service"
        "http://localhost:8000/health kong-gateway"
    )

    sleep 10  # انتظار أولي
    for svc in "${services[@]}"; do
        read -r url name <<< "$svc"
        wait_for_service "$url" "$name" 30 || warn "الخدمة $name لم تبدأ — تحقق من logs"
    done

    log "✅ الخدمات الخلفية تعمل"
    echo ""
    echo -e "  ${CYAN}Kong Gateway:${NC}   http://localhost:8000"
    echo -e "  ${CYAN}Indicators:${NC}     http://localhost:8091/docs"
    echo -e "  ${CYAN}Weather:${NC}        http://localhost:8092/docs"
    echo -e "  ${CYAN}Soil:${NC}           http://localhost:8094/docs"
    echo -e "  ${CYAN}Prometheus:${NC}     http://localhost:9090"
    echo -e "  ${CYAN}Grafana:${NC}        http://localhost:3001"
    echo -e "  ${CYAN}NATS Monitor:${NC}   http://localhost:8222"
}

start_frontend_dev() {
    section "تشغيل الواجهة الأمامية (Development)"
    cd "$FRONTEND_DIR"

    if [[ ! -d "node_modules" ]]; then
        log "تثبيت الاعتماديات..."
        npm install --legacy-peer-deps
    fi

    # نسخ .env للواجهة
    if [[ -f "${BACKEND_DIR}/.env" ]]; then
        cp "${BACKEND_DIR}/.env" "${FRONTEND_DIR}/.env.local" 2>/dev/null || true
    fi

    cat > "${FRONTEND_DIR}/.env.local" << 'FEEOF'
VITE_API_URL=http://localhost:8000
VITE_INDICATORS_URL=http://localhost:8091
VITE_VEGETATION_URL=http://localhost:8090
VITE_WEATHER_URL=http://localhost:8092
VITE_SOIL_URL=http://localhost:8094
VITE_AUTH_URL=http://localhost:8120
VITE_MOCK_MODE=false
FEEOF

    log "تشغيل Vite Dev Server..."
    npm run dev &
    FRONTEND_PID=$!
    echo "$FRONTEND_PID" > /tmp/sahool_frontend.pid

    sleep 3
    log "✅ الواجهة الأمامية تعمل على:"
    echo -e "  ${CYAN}http://localhost:5173${NC}"
}

start_frontend_prod() {
    section "بناء ونشر الواجهة (Production)"
    cd "$FRONTEND_DIR"

    if [[ ! -d "node_modules" ]]; then
        log "تثبيت الاعتماديات..."
        npm install --legacy-peer-deps
    fi

    log "بناء المشروع (Vite build)..."
    VITE_API_URL=http://localhost:8000 \
    VITE_MOCK_MODE=false \
    npm run build

    log "تشغيل عبر Docker (Nginx)..."
    cd "$BACKEND_DIR"
    docker-compose -f docker-compose.yml up -d frontend

    log "✅ الواجهة جاهزة على:"
    echo -e "  ${CYAN}http://localhost:3000${NC}"
}

show_status() {
    section "حالة الخدمات"
    echo ""
    local services=(
        "8091:/health:indicators-service (33 مؤشر)"
        "8090:/health:vegetation-service (Sentinel-2)"
        "8092:/health:weather-service (WOFOST)"
        "8094:/health:soil-service (FAO)"
        "8000:/:kong-gateway"
        "8222:/healthz:nats-jetstream"
        "9090:/-/healthy:prometheus"
        "3001:/api/health:grafana"
        "5173:/index.html:frontend-dev"
        "3000:/index.html:frontend-prod"
    )
    for svc in "${services[@]}"; do
        IFS=':' read -r port path name <<< "$svc"
        if curl -sf "http://localhost:${port}${path}" &>/dev/null; then
            echo -e "  ${GREEN}✓${NC} $name (localhost:$port)"
        else
            echo -e "  ${RED}✗${NC} $name (localhost:$port) — غير متاح"
        fi
    done
    echo ""
    echo "Docker containers:"
    docker-compose ps 2>/dev/null || echo "(docker-compose غير متاح)"
}

stop_all() {
    section "إيقاف جميع الخدمات"
    # إيقاف frontend dev
    if [[ -f /tmp/sahool_frontend.pid ]]; then
        kill "$(cat /tmp/sahool_frontend.pid)" 2>/dev/null || true
        rm /tmp/sahool_frontend.pid
        log "✓ Frontend dev server stopped"
    fi
    # إيقاف Docker
    cd "$BACKEND_DIR"
    docker-compose down
    log "✅ جميع الخدمات متوقفة"
}

run_health_check() {
    section "فحص صحة النظام"
    local failed=0
    for url in \
        "http://localhost:8091/readyz" \
        "http://localhost:8090/readyz" \
        "http://localhost:8092/readyz" \
        "http://localhost:8094/readyz"; do
        name=$(echo "$url" | sed 's|http://localhost:||;s|/readyz||')
        if curl -sf "$url" | grep -q '"status":"ready"' 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} :$name — جاهز"
        else
            echo -e "  ${RED}✗${NC} :$name — ${YELLOW}degraded${NC}"
            ((failed++)) || true
        fi
    done
    echo ""
    [[ $failed -eq 0 ]] && log "✅ جميع الخدمات صحية" || warn "$failed خدمة غير جاهزة — تحقق من logs"
}

print_summary() {
    section "ملخص النظام"
    echo -e "  ${BOLD}SAHOOL v8.0 — الزراعة الذكية اليمنية${NC}"
    echo ""
    echo -e "  ${CYAN}الواجهة:${NC}"
    echo "    http://localhost:3000  (Production)"
    echo "    http://localhost:5173  (Development)"
    echo ""
    echo -e "  ${CYAN}APIs:${NC}"
    echo "    http://localhost:8000       Kong Gateway"
    echo "    http://localhost:8091/docs  Indicators (33 مؤشر)"
    echo "    http://localhost:8090/docs  Vegetation"
    echo "    http://localhost:8092/docs  Weather + WOFOST"
    echo "    http://localhost:8094/docs  Soil + FAO"
    echo ""
    echo -e "  ${CYAN}المراقبة:${NC}"
    echo "    http://localhost:9090  Prometheus"
    echo "    http://localhost:3001  Grafana (admin/grafana_pass)"
    echo "    http://localhost:8222  NATS Monitor"
    echo ""
    echo -e "  ${CYAN}للاختبار:${NC}"
    echo "    python -m pytest tests/ -v  (47 اختبار)"
    echo "    curl http://localhost:8091/v1/indicators/field_01 | jq"
    echo "    curl http://localhost:8092/weather/wofost_format?days=7"
    echo ""
}

# ══════════════════════════════════════════════════════════════
# التنفيذ الرئيسي
# ══════════════════════════════════════════════════════════════

echo -e "\n${GREEN}${BOLD}"
echo "  ███████╗ █████╗ ██╗  ██╗ ██████╗  ██████╗ ██╗"
echo "  ██╔════╝██╔══██╗██║  ██║██╔═══██╗██╔═══██╗██║"
echo "  ███████╗███████║███████║██║   ██║██║   ██║██║"
echo "  ╚════██║██╔══██║██╔══██║██║   ██║██║   ██║██║"
echo "  ███████║██║  ██║██║  ██║╚██████╔╝╚██████╔╝███████╗"
echo "  ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚══════╝"
echo "  v8.0 — منصة الزراعة الذكية اليمنية"
echo -e "${NC}"

case "$MODE" in
    "all")
        check_deps
        setup_env
        start_backend
        start_frontend_dev
        run_health_check
        print_summary
        ;;
    "backend")
        check_deps
        setup_env
        start_backend
        run_health_check
        ;;
    "frontend")
        check_deps
        start_frontend_dev
        ;;
    "stop")
        stop_all
        ;;
    "status")
        show_status
        ;;
esac
