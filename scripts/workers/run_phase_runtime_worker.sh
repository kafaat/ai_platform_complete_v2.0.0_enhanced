#!/usr/bin/env bash
set -Eeuo pipefail
kind="${1:?worker kind required: outbox|plugin|model|actuator}"
exec python -m api.phase_runtime_workers "$kind"
