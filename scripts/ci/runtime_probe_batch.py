#!/usr/bin/env python3
"""Run the runtime probe plan as one deterministic batch."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "runtime-verification/generated/runtime_probe_plan.json"
PROBE = ROOT / "scripts/ci/runtime_probe.py"
TARGETS = ROOT / "runtime-verification/generated/compose_runtime_targets.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--deployment-manifest", required=True)
    parser.add_argument("--service", action="append", dest="services")
    parser.add_argument("--evidence-dir", default="runtime-verification/evidence")
    parser.add_argument("--plan", default=str(PLAN))
    args = parser.parse_args()

    plan_path = Path(args.plan)
    if not plan_path.is_absolute():
        plan_path = ROOT / plan_path
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    selected = set(
        args.services or [row["service"] for row in plan["services"] if row.get("probes")]
    )
    target_rows = {}
    if TARGETS.exists():
        target_rows = {
            row["service"]: row
            for row in json.loads(TARGETS.read_text(encoding="utf-8"))["targets"]
        }
    failures: list[str] = []
    attempted = 0

    for item in plan["services"]:
        if item["service"] not in selected or not item.get("probes"):
            continue
        attempted += 1
        row = target_rows.get(item["service"], {})
        base_urls = [m["base_url"] for m in row.get("members", []) if m.get("base_url")]
        if not base_urls and row.get("base_url"):
            base_urls = [row["base_url"]]
        if not base_urls:
            raw = os.getenv(item["base_url_env"], "")
            base_urls = [value.strip() for value in raw.split(",") if value.strip()]
        if not base_urls:
            failures.append(f"{item['service']}:missing:{item['base_url_env']}")
            continue
        for index, base_url in enumerate(base_urls, start=1):
            suffix = f"-{index}" if len(base_urls) > 1 else ""
            command = [
                sys.executable,
                str(PROBE),
                "--service",
                item["service"],
                "--environment-id",
                args.environment_id,
                "--deployment-manifest",
                args.deployment_manifest,
                "--plan",
                str(plan_path),
                "--evidence-dir",
                args.evidence_dir,
                "--output-name",
                f"{item['service']}{suffix}.json",
                "--base-url",
                base_url,
            ]
            completed = subprocess.run(command, cwd=ROOT, check=False)
            if completed.returncode:
                failures.append(f"{item['service']}:{index}:probe_failed")

    print(f"Runtime probe batch: attempted={attempted}, failed={len(failures)}")
    if failures:
        print("Failures: " + ", ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
