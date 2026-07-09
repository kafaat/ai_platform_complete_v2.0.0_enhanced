#!/usr/bin/env bash
# Shared pip index defaults for connected CI / operator environments.
# Default is official PyPI. Operators may opt into Alibaba Cloud or a private mirror
# by setting PYPI_MIRROR_URL or PIP_INDEX_URL without editing the repo.
set -euo pipefail

DEFAULT_PYPI_INDEX_URL="https://pypi.org/simple"
ALIBABA_PYPI_MIRROR="https://mirrors.aliyun.com/pypi/simple/"
export ALIBABA_PYPI_MIRROR
export PYPI_MIRROR_URL="${PYPI_MIRROR_URL:-${PIP_INDEX_URL:-$DEFAULT_PYPI_INDEX_URL}}"
export PIP_INDEX_URL="$PYPI_MIRROR_URL"
export PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-}"
export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-60}"
export PIP_RETRIES="${PIP_RETRIES:-5}"

if [ -n "$PIP_TRUSTED_HOST" ]; then
  echo "pip index: $PIP_INDEX_URL (trusted-host configured)"
else
  echo "pip index: $PIP_INDEX_URL"
fi
