#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/build-immutable.sh [--gpu] [--no-cache]

Builds SAHOOL images with immutable Git identity. The script:
  * requires a clean Git working tree;
  * resolves TESTED_SHA from the full 40-character HEAD;
  * validates docker compose before building.
USAGE
}

gpu=0
no_cache=0
while (($#)); do
  case "$1" in
    --gpu) gpu=1 ;;
    --no-cache) no_cache=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "Unable to locate the Git repository root." >&2
  exit 1
}
cd "$repo_root"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit or stash changes before immutable build." >&2
  exit 1
fi

sha="$(git rev-parse HEAD)"
if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Unable to resolve a full 40-character Git SHA." >&2
  exit 1
fi

export TESTED_SHA="$sha"
export SAHOOL_BUILD_ID="${SAHOOL_BUILD_ID:-local-${sha:0:12}}"

compose=(-f docker-compose.v9.yml)
if ((gpu)); then
  compose+=(-f docker-compose.v9.gpu.yml --profile gpu)
fi

docker compose "${compose[@]}" config --quiet
build=(docker compose "${compose[@]}" build)
if ((no_cache)); then
  build+=(--no-cache)
fi
"${build[@]}"

echo "Immutable build completed for TESTED_SHA=$sha"
