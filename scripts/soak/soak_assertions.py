#!/usr/bin/env python3
"""Evaluate Sahool soak-test summary metrics against certification thresholds."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

THRESHOLDS = {
    "max_5xx_rate": 0.005,
    "max_outbox_backlog_age_seconds": 300,
    "max_dead_letters": 0,
    "max_tile_cache_mismatch": 0,
    "max_ai_fake_fallbacks": 0,
    "max_replay_drift": 0,
    "min_worker_recovery_rate": 0.99,
}


def evaluate(metrics: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if float(metrics.get("http_5xx_rate", 0)) > THRESHOLDS["max_5xx_rate"]:
        failures.append("http_5xx_rate exceeded")
    if int(metrics.get("outbox_backlog_age_seconds", 0)) > THRESHOLDS["max_outbox_backlog_age_seconds"]:
        failures.append("outbox backlog age exceeded")
    if int(metrics.get("dead_letters", 0)) > THRESHOLDS["max_dead_letters"]:
        failures.append("dead letters detected")
    if int(metrics.get("tile_cache_mismatch", 0)) > THRESHOLDS["max_tile_cache_mismatch"]:
        failures.append("tile cache mismatch detected")
    if int(metrics.get("ai_fake_fallbacks", 0)) > THRESHOLDS["max_ai_fake_fallbacks"]:
        failures.append("AI fake fallback detected")
    if int(metrics.get("replay_drift", 0)) > THRESHOLDS["max_replay_drift"]:
        failures.append("replay drift detected")
    if float(metrics.get("worker_recovery_rate", 1)) < THRESHOLDS["min_worker_recovery_rate"]:
        failures.append("worker recovery rate too low")
    return not failures, failures


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--metrics-json", required=True)
    args = p.parse_args()
    metrics = json.loads(Path(args.metrics_json).read_text(encoding="utf-8"))
    ok, failures = evaluate(metrics)
    print(json.dumps({"passed": ok, "failures": failures, "thresholds": THRESHOLDS}, indent=2, sort_keys=True))
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
