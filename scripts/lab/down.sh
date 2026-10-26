#!/usr/bin/env bash
# Stop the Sahool local integration lab. Removes only Docker objects that carry the
# lab label; keeps images (pinned by digest) and $LAB_DIR (venv and evidence) unless
# --purge is given, which also deletes $LAB_DIR.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/lab/lab.env
source scripts/lab/lab.env

docker info >/dev/null 2>&1 || { echo "docker is not running; nothing to stop"; exit 0; }
ids="$(docker ps -aq --filter "label=$LAB_LABEL")"
if [ -n "$ids" ]; then
  # shellcheck disable=SC2086
  docker rm -f -v $ids >/dev/null
fi
echo "removed $(printf '%s' "$ids" | grep -c . || true) lab container(s)"
if [ "${1:-}" = "--purge" ]; then
  rm -rf -- "$LAB_DIR"
  echo "removed $LAB_DIR"
fi
