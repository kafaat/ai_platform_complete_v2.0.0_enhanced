#!/usr/bin/env bash
# SAHOOL v9.0 -- First-Time Setup Script
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     SAHOOL v9.0 -- Setup Wizard               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""

# Check Docker
echo "[1/5] Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker not found. Please install Docker first.${NC}"
    exit 1
fi
if ! command -v docker compose &> /dev/null; then
    echo -e "${RED}docker compose not found. Please install docker compose first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker OK${NC}"

# Check Git
echo "[2/5] Checking Git..."
if ! command -v git &> /dev/null; then
    echo -e "${RED}Git not found.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Git OK${NC}"

# Generate secrets
echo "[3/5] Generating secure secrets..."
JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | xxd -p | tr -d '\n')
DB_PASS=$(openssl rand -base64 24 2>/dev/null || head -c 32 /dev/urandom | base64 | tr -d '=+/\n')
AGENT_TOKEN=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | xxd -p | tr -d '\n')
EDGE_TOKEN=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | xxd -p | tr -d '\n')
MINIO_PASS=$(openssl rand -base64 24 2>/dev/null || head -c 32 /dev/urandom | base64 | tr -d '=+/\n')

cat > .env << EOF
# SAHOOL v9.0 -- Auto-generated on $(date)
# ⚠️ Keep this file secret! Do not commit to Git.

POSTGRES_PASSWORD=$DB_PASS
JWT_SECRET=$JWT_SECRET
MINIO_ROOT_USER=sahool
MINIO_ROOT_PASSWORD=$MINIO_PASS
SH_CLIENT_ID=your_sentinel_hub_client_id
SH_CLIENT_SECRET=your_sentinel_hub_client_secret
SH_INSTANCE_ID=your_instance_id
SAHOOL_AGENT_TOKEN=$AGENT_TOKEN
EDGE_SYNC_TOKEN=$EDGE_TOKEN
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_from_botfather
GRAFANA_PASSWORD=admin_change_me
MAPBOX_TOKEN=your_mapbox_token
EDGE_DEVICE=rpi5
OFFLINE_MODE=false
EOF

echo -e "${GREEN}✓ .env generated with secure secrets${NC}"

# Create directories
echo "[4/5] Creating data directories..."
mkdir -p data/postgres data/redis data/minio data/nats data/qdrant data/edge models
mkdir -p logs/nginx logs/services logs/agents
echo -e "${GREEN}✓ Directories created${NC}"

# Build images
echo "[5/5] Building Docker images (this may take 5-10 minutes)..."
docker compose -f docker-compose.v9.yml build --parallel
echo -e "${GREEN}✓ Images built${NC}"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Setup Complete!                          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your Sentinel Hub + Telegram tokens"
echo "  2. Run: ./scripts/run_all.sh up"
echo "  3. Access dashboard at http://localhost:3001"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT: Keep .env secret! Add it to .gitignore${NC}"
