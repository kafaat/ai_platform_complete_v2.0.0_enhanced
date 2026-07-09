#!/usr/bin/env python3
"""Production certification checklist inventory/guard.

This guard intentionally does not pretend to run external blockers that require
connected CI, Redis, or model artifacts. It freezes the blocker contract so the
repo cannot silently mark production certification complete without evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "production_certification_checklist.generated.json"
CSV_PATH = ROOT / "production_certification_checklist.csv"
RUNBOOK_PATH = ROOT / "docs" / "runbooks" / "PRODUCTION_CERTIFICATION_CHECKLIST.md"

BLOCKERS = [
    {
        "id": "P-CERT-1",
        "name": "Full branch CI",
        "severity": "critical",
        "status": "pending_external_ci",
        "required_evidence": [
            "pytest -m unit exits 0",
            "platform test suite exits 0",
            "tsc --noEmit exits 0",
            "vitest run exits 0",
            "ruff check exits 0",
            "Docker build matrix exits 0",
            "release bundle exits 0",
            "all generated inventories are clean",
        ],
        "commands": [
            "pytest -m unit",
            "pytest platform/tests",
            "tsc --noEmit",
            "vitest run",
            "ruff check .",
            "docker build matrix",
            "release bundle",
        ],
        "certification_rule": "0 failed, no unexpected critical skip, no inventory/guard drift",
    },
    {
        "id": "P-CERT-2",
        "name": "Connected transitive lock generation",
        "severity": "critical",
        "status": "pending_connected_index_or_internal_mirror",
        "required_evidence": [
            "scripts/ci/compile_transitive_service_locks.sh exits 0 in connected CI",
            "official PyPI is the default index",
            "Alibaba mirror is only an explicit override",
            "Tencent mirror is not a default",
            "pip install uses --timeout 300 and --retries 10",
            "generated transitive lock files are committed or attached to the release bundle",
        ],
        "commands": [
            "scripts/ci/compile_transitive_service_locks.sh",
            "python scripts/ci/pip_mirror_contract_guard.py",
        ],
        "certification_rule": "reproducible locks generated from connected PyPI/default index or reviewed internal mirror",
    },
    {
        "id": "P-CERT-3",
        "name": "Redis live integration",
        "severity": "medium-critical",
        "status": "pending_live_redis_endpoint",
        "required_evidence": [
            "WEATHER_REDIS_INTEGRATION_URL points at a real Redis instance",
            "weather Redis live optional test exits 0",
            "cache write/read works",
            "stale fallback behavior remains verified",
            "/readyz reports cache backend truthfully",
        ],
        "commands": [
            "WEATHER_REDIS_INTEGRATION_URL=redis://localhost:6379/0 pytest services/weather-service/tests/test_weather_redis_live_optional.py",
            "scripts/ci/run_weather_redis_integration.sh",
        ],
        "certification_rule": "live Redis passes without downgrading readiness honesty",
    },
    {
        "id": "P-CERT-4",
        "name": "ONNX/SAM2 model provisioning",
        "severity": "critical",
        "status": "pending_operator_model_artifacts",
        "required_evidence": [
            "/models/pest_detector_int8.onnx exists in deployment environment",
            "/models/yield_estimator_int8.onnx exists in deployment environment",
            "SAM2 artifacts exist in deployment environment",
            "EDGE_READINESS_MODE=strict and EDGE_PRODUCTION_REQUIRED=true",
            "/readyz is ready when artifacts exist",
            "missing model still fails closed",
            "no simulation fallback is used",
        ],
        "commands": [
            "python scripts/ci/edge_model_contract_guard.py",
            "python scripts/ci/edge_production_readiness_guard.py",
            "EDGE_READINESS_MODE=strict EDGE_PRODUCTION_REQUIRED=true pytest services/edge-inference/tests",
        ],
        "certification_rule": "strict readiness passes only with provisioned artifacts; absent artifacts fail closed",
    },
]


def _payload() -> dict:
    return {
        "schema_version": 1,
        "certification_state": "release_candidate_not_production_certified",
        "policy": "Do not mark production certified until every blocker has evidence from the target branch/deployment environment.",
        "recommended_closure_order": ["P-CERT-2", "P-CERT-1", "P-CERT-4", "P-CERT-3"],
        "known_local_skip": {
            "test": "services/weather-service/tests/test_weather_redis_live_optional.py",
            "reason": "Skipped unless WEATHER_REDIS_INTEGRATION_URL is set; this is the explicit P-CERT-3 live Redis blocker, not a hidden failure.",
            "certification_impact": "acceptable for local offline guard runs; not acceptable for final production certification evidence",
        },
        "blockers": BLOCKERS,
    }


def write_files() -> None:
    payload = _payload()
    JSON_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "name",
                "severity",
                "status",
                "certification_rule",
                "commands",
                "required_evidence",
            ],
        )
        writer.writeheader()
        for item in BLOCKERS:
            row = dict(item)
            row["commands"] = " | ".join(item["commands"])
            row["required_evidence"] = " | ".join(item["required_evidence"])
            writer.writerow(row)
    RUNBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNBOOK_PATH.write_text(_runbook_text(), encoding="utf-8")


def _runbook_text() -> str:
    lines = [
        "# Sahool Production Certification Checklist",
        "",
        "This checklist is intentionally evidence-driven. The repository is a governed release candidate; it is not production-certified until the four blockers below are verified in the target CI/deployment environment.",
        "",
        "## Certification state",
        "",
        "`release_candidate_not_production_certified`",
        "",
        "## Recommended closure order",
        "",
        "1. `P-CERT-2` — Connected transitive lock generation",
        "2. `P-CERT-1` — Full branch CI",
        "3. `P-CERT-4` — ONNX/SAM2 model provisioning",
        "4. `P-CERT-3` — Redis live integration",
        "",
        "## Known local skipped test",
        "",
        "`services/weather-service/tests/test_weather_redis_live_optional.py` is skipped unless `WEATHER_REDIS_INTEGRATION_URL` is set. This skip maps directly to `P-CERT-3`; it is acceptable for offline/local guard runs and unacceptable as final certification evidence.",
        "",
        "## Blockers",
        "",
    ]
    for item in BLOCKERS:
        lines.extend(
            [
                f"### {item['id']} — {item['name']}",
                "",
                f"- Severity: `{item['severity']}`",
                f"- Current status: `{item['status']}`",
                f"- Certification rule: {item['certification_rule']}",
                "",
                "Required evidence:",
                "",
            ]
        )
        lines.extend([f"- {e}" for e in item["required_evidence"]])
        lines.extend(["", "Commands:", ""])
        lines.extend([f"```bash\n{cmd}\n```" for cmd in item["commands"]])
        lines.append("")
    lines.extend(
        [
            "## Non-negotiable policy",
            "",
            "Do not change this checklist to `certified` by editing text. Certification requires fresh branch/deployment evidence for every blocker.",
            "",
        ]
    )
    return "\n".join(lines)


def check_files() -> None:
    expected_json = json.dumps(_payload(), indent=2, ensure_ascii=False) + "\n"
    if not JSON_PATH.exists() or JSON_PATH.read_text(encoding="utf-8") != expected_json:
        raise SystemExit("production certification checklist JSON drift; run with --write")
    if not CSV_PATH.exists():
        raise SystemExit("production certification checklist CSV missing; run with --write")
    if not RUNBOOK_PATH.exists():
        raise SystemExit("production certification checklist runbook missing; run with --write")
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    for item in BLOCKERS:
        if item["id"] not in runbook or item["name"] not in runbook:
            raise SystemExit(f"runbook missing blocker {item['id']}")
    if (
        "test_weather_redis_live_optional.py" not in runbook
        or "WEATHER_REDIS_INTEGRATION_URL" not in runbook
    ):
        raise SystemExit("runbook must document the known Redis live skipped test")
    # prevent accidental false certification without evidence automation
    if (
        "production_certified" in expected_json
        and "release_candidate_not_production_certified" not in expected_json
    ):
        raise SystemExit("checklist must not claim production certification")
    print("production_certification_checklist_ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        write_files()
    if args.check or not args.write:
        check_files()


if __name__ == "__main__":
    main()
