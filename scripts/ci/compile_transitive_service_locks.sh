#!/usr/bin/env bash
# Compile true transitive lock files for every service with pip-tools.
# Requires network/package-index access. By default it uses Alibaba Cloud PyPI mirror
# (https://mirrors.aliyun.com/pypi/simple/) unless PIP_INDEX_URL/PYPI_MIRROR_URL is overridden.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
source scripts/ci/pip_mirror_env.sh
python -m pip install --upgrade pip pip-tools
while IFS= read -r req; do
  out="${req%.txt}.lock"
  echo "[pip-compile] $req -> $out via $PIP_INDEX_URL"
  python -m piptools compile     --resolver=backtracking     --strip-extras     --generate-hashes     --index-url "$PIP_INDEX_URL"     -o "$out" "$req"
done < <(find services -maxdepth 3 -name 'requirements.txt' -print | sort)
