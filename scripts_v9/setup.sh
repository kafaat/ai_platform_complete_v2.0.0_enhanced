#!/usr/bin/env bash
# First-time local setup. The build entrypoint checks the configured environment,
# engine and source identity before building.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
bash scripts_v9/run_all.sh build
mkdir -p data/{postgres,redis,minio,nats,qdrant,edge} models logs/{nginx,services,agents}

echo "Setup complete. To start the services: bash scripts_v9/run_all.sh up"
