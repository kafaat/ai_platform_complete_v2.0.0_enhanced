#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$ROOT"
TENANTS="${TENANTS:-1000}"
FIELDS="${FIELDS:-100000}"
DAYS="${DAYS:-7}"
OUT_DIR="${OUT_DIR:-soak-results}"
mkdir -p "$OUT_DIR"
python3 scripts/soak/soak_scenario.py --tenants "$TENANTS" --fields "$FIELDS" --days "$DAYS" > "$OUT_DIR/scenario.json"
cat > "$OUT_DIR/README_NEXT_STEPS.md" <<'MD'
# Sahool Soak Harness

This harness intentionally does not fake a 7-14 day live run. Use it after the
stack is up and point k6/chaos/recovery jobs at the target environment. At the
end, write aggregate metrics to `metrics.json` and run:

```bash
python3 scripts/soak/soak_assertions.py --metrics-json soak-results/metrics.json
python3 scripts/soak/soak_report.py --scenario-json soak-results/scenario.json --metrics-json soak-results/metrics.json
```

Required metrics keys:
`http_5xx_rate`, `outbox_backlog_age_seconds`, `dead_letters`,
`tile_cache_mismatch`, `ai_fake_fallbacks`, `replay_drift`,
`worker_recovery_rate`.
MD
echo "Generated $OUT_DIR/scenario.json. Run the live workload and produce $OUT_DIR/metrics.json."
