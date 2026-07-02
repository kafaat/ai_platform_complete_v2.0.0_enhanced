#!/usr/bin/env python3
"""Runtime-chain static contract gate.

This does not replace live Docker E2E. It verifies the code contains runnable contracts for:
- tenant/auth live probes
- weather-signal-engine producer -> platform/UI consumer chain
- raster-tiler-service as an internal tiler dependency
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = {
    "tenant_live_script": ("scripts/e2e/tenant_auth_live_gate.py", ["current_field_state", "tenant_mismatch", "/api/rag/search", "/api/knowledge-graph/nodes"]),
    "weather_signal_worker": ("services/weather-signal-engine/src/main.py", ["field_weather_overlay", "weather_signals", "build_signal_records"]),
    "weather_signal_platform": ("services/sahool-platform/core/daily_ai_brief.py", ["weather_signal"]),
    "weather_signal_playbook": ("services/sahool-platform/core/decision_playbook.py", ["weather_signals", "spray_window_open"]),
    "raster_tiler_readme": ("services/raster-tiler-service/README.md", ["raster-tiler-service", "TITILER_BASE_URL"]),
    "raster_tiler_compose": ("docker-compose.v9.yml", ["raster-tiler-service", "127.0.0.1:8088:8088"]),
}


def main() -> int:
    failures: list[str] = []
    for key, (path, needles) in REQUIRED.items():
        p = ROOT / path
        if not p.exists():
            failures.append(f"{key}: missing {path}")
            continue
        src = p.read_text()
        for n in needles:
            if n not in src:
                failures.append(f"{key}: missing token {n!r} in {path}")
    out = ROOT / "docs/backend/runtime_contract_gate.generated.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"gate":"runtime-contract-gate", "passed": not failures, "failures": failures}, indent=2, ensure_ascii=False)+"\n")
    if failures:
        print("runtime-contract-gate: FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("runtime-contract-gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
