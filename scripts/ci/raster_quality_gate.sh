#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$ROOT_DIR"

echo "== Raster service static compile =="
python3 -m compileall -q services/raster-service scripts/ci services/sahool-platform/api

echo "== Raster main decomposition gate =="
python3 scripts/ci/raster_main_decomposition_gate.py

echo "== Raster import graph gate =="
python3 scripts/ci/raster_import_graph_gate.py

echo "== Raster service tests =="
(
  cd services/raster-service
  python3 -m pytest -q
)

echo "Raster quality gate passed"
