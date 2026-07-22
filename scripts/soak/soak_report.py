#!/usr/bin/env python3
"""Create a compact markdown report from soak scenario and metrics JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from soak_assertions import THRESHOLDS, evaluate


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scenario-json", required=True)
    p.add_argument("--metrics-json", required=True)
    p.add_argument("--output", default="SOAK_TEST_RUNTIME_REPORT.md")
    args = p.parse_args()
    scenario = json.loads(Path(args.scenario_json).read_text(encoding="utf-8"))
    metrics = json.loads(Path(args.metrics_json).read_text(encoding="utf-8"))
    ok, failures = evaluate(metrics)
    lines = [
        "# Sahool Soak Test Runtime Report",
        "",
        f"Status: {'PASSED' if ok else 'FAILED'}",
        "",
        "## Scenario",
        "```json",
        json.dumps(scenario, indent=2, sort_keys=True),
        "```",
        "",
        "## Metrics",
        "```json",
        json.dumps(metrics, indent=2, sort_keys=True),
        "```",
        "",
        "## Thresholds",
        "```json",
        json.dumps(THRESHOLDS, indent=2, sort_keys=True),
        "```",
        "",
        "## Failures",
        "None" if not failures else "\n".join(f"- {x}" for x in failures),
    ]
    Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
