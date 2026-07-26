#!/usr/bin/env python3
"""Artifact-based closure gate for PATH-2 integration/runtime-evidence governance.

This closes the repository-side governance framework only. It intentionally
cannot convert a static plan into live runtime verification or production
certification; those require externally generated, plan-bound evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "governance" / "path2-generated"
SUMMARY_PATH = OUT_DIR / "INTEGRATION_RUNTIME_GOVERNANCE_CLOSURE.json"
REPORT_PATH = OUT_DIR / "INTEGRATION_RUNTIME_GOVERNANCE_CLOSURE.md"
MANIFEST_PATH = OUT_DIR / "INTEGRATION_RUNTIME_GOVERNANCE_ARTIFACTS.sha256"

ARTIFACT_ROOTS = [
    ROOT / "gateway-audit/generated",
    ROOT / "event-audit/generated",
    ROOT / "database-audit/generated",
    ROOT / "runtime-verification/generated",
]

REQUIRED = {
    "path1": ROOT / "governance/generated/STATIC_GOVERNANCE_CLOSURE.json",
    "gateway": ROOT / "gateway-audit/generated/gateway_reachability.json",
    "event": ROOT / "event-audit/generated/event_contract_summary.json",
    "database": ROOT / "database-audit/generated/database_contract_summary.json",
    "runtime_plan": ROOT / "runtime-verification/generated/runtime_verification_summary.json",
    "runtime_evidence": ROOT / "runtime-verification/generated/runtime_evidence_ledger.json",
    "certification": ROOT / "runtime-verification/generated/runtime_certification_summary.json",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def artifact_files() -> list[Path]:
    files: list[Path] = []
    for root in ARTIFACT_ROOTS:
        if root.exists():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def manifest_text() -> str:
    return "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(ROOT).as_posix()}\n"
        for path in artifact_files()
    )


def check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def evaluate() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    data = {name: load_json(path) for name, path in REQUIRED.items()}
    checks = [
        check(f"artifact:{name}", bool(payload), path.relative_to(ROOT).as_posix())
        for (name, path), payload in zip(REQUIRED.items(), data.values(), strict=True)
    ]
    if not all(item["passed"] for item in checks):
        return checks, data

    path1 = data["path1"]
    gateway = data["gateway"]
    event = data["event"]
    database = data["database"]
    plan = data["runtime_plan"]
    evidence = data["runtime_evidence"]
    certification = data["certification"]

    unknown_evidence = evidence.get("unknown_or_unbound_evidence_files", [])
    service_violations = certification.get("service_claim_violations", [])
    capability_violations = certification.get("capability_claim_violations", [])

    checks.extend(
        [
            check("path1:closed", path1.get("status") == "CLOSED", f"status={path1.get('status')}"),
            check(
                "gateway:no_hard_configuration_errors",
                gateway.get("hard_configuration_errors", []) == [],
                f"hard_errors={len(gateway.get('hard_configuration_errors', []))}",
            ),
            check(
                "gateway:no_runtime_or_production_claim",
                gateway.get("runtime_verified") is False
                and gateway.get("production_certified") is False,
                "runtime=false, production=false",
            ),
            check(
                "events:no_cross_component_durable_collision",
                event.get("cross_component_duplicate_durables") == 0,
                f"collisions={event.get('cross_component_duplicate_durables')}",
            ),
            check(
                "events:no_runtime_or_production_claim",
                event.get("runtime_verified") is False
                and event.get("production_certified") is False,
                "runtime=false, production=false",
            ),
            check(
                "database:manifest_complete",
                database.get("manifest_missing_count") == 0
                and database.get("unlisted_sql_count") == 0,
                f"missing={database.get('manifest_missing_count')}, unlisted={database.get('unlisted_sql_count')}",
            ),
            check(
                "database:no_runtime_or_production_claim",
                database.get("runtime_verified") is False
                and database.get("production_certified") is False,
                "runtime=false, production=false",
            ),
            check(
                "runtime_plan:nonempty",
                isinstance(plan.get("planned_probes"), int) and plan.get("planned_probes", 0) > 0,
                f"planned_probes={plan.get('planned_probes')}",
            ),
            check(
                "runtime_plan:fail_closed_static_state",
                plan.get("static_plan_only") is True
                and plan.get("runtime_verified_services") == 0
                and plan.get("production_certified_services") == 0,
                "static plan only; verified=0; certified=0",
            ),
            check(
                "runtime_evidence:fail_closed",
                evidence.get("fail_closed") is True,
                f"fail_closed={evidence.get('fail_closed')}",
            ),
            check(
                "runtime_evidence:no_unknown_files",
                unknown_evidence == [],
                f"unknown_or_unbound={len(unknown_evidence) if isinstance(unknown_evidence, list) else 'invalid'}",
            ),
            check(
                "certification:gate_passed",
                certification.get("gate_passed") is True,
                f"gate_passed={certification.get('gate_passed')}",
            ),
            check(
                "certification:no_claim_violations",
                service_violations == [] and capability_violations == [],
                f"service={len(service_violations)}, capability={len(capability_violations)}",
            ),
            check(
                "certification:no_production_claim",
                certification.get("production_certified_services") in (0, [], None),
                f"production_certified_services={certification.get('production_certified_services')}",
            ),
        ]
    )
    return checks, data


def closure_payload(checks: list[dict[str, Any]]) -> dict[str, Any]:
    closed = all(item.get("passed", False) for item in checks)
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "scope": "path-2-integration-and-runtime-evidence-governance",
        "status": "CLOSED" if closed else "OPEN",
        "integration_governance_verified": closed,
        "runtime_verification_framework_ready": closed,
        "runtime_verified": False,
        "production_certified": False,
        "checks": checks,
        "tracked_non_blocking_remainders": [
            "gateway security review candidates requiring live request verification",
            "dynamic NATS subjects requiring runtime topology evidence",
            "tenant/RLS review candidates requiring PostgreSQL catalog proof",
            "live health, readiness, metrics, queue, database, and end-to-end evidence",
        ],
        "handoff_to_path3": "Execute the stack and ingest plan-bound evidence; only valid evidence may change runtime_verified state.",
        "boundary": "PATH-2 closes repository-side integration and runtime-evidence governance. It does not certify a running stack or production environment.",
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["content_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# SAHOOL PATH-2 Closure — Integration and Runtime-Evidence Governance",
        "",
        f"**Final status: `{payload['status']}`**",
        "",
        "## Closure gates",
        "",
        "| Gate | Result | Detail |",
        "|---|---|---|",
    ]
    for item in payload["checks"]:
        detail = str(item["detail"]).replace("|", "/")
        lines.append(
            f"| `{item['name']}` | **{'PASS' if item['passed'] else 'FAIL'}** | {detail} |"
        )
    lines.extend(
        [
            "",
            "## Formal boundary",
            "",
            payload["boundary"],
            "",
            "## PATH-3 handoff",
            "",
            payload["handoff_to_path3"],
            "",
            "## Tracked non-blocking remainders",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["tracked_non_blocking_remainders"])
    lines.extend(["", f"Content SHA-256: `{payload['content_sha256']}`", ""])
    return "\n".join(lines)


def write_closure(payload: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    REPORT_PATH.write_text(render_report(payload), encoding="utf-8")
    MANIFEST_PATH.write_text(manifest_text(), encoding="utf-8")


def validate_closure(payload: dict[str, Any]) -> bool:
    return (
        SUMMARY_PATH.exists()
        and SUMMARY_PATH.read_text(encoding="utf-8")
        == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        and REPORT_PATH.exists()
        and REPORT_PATH.read_text(encoding="utf-8") == render_report(payload)
        and MANIFEST_PATH.exists()
        and MANIFEST_PATH.read_text(encoding="utf-8") == manifest_text()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    checks, _ = evaluate()
    payload = closure_payload(checks)
    if args.generate:
        write_closure(payload)
    elif not validate_closure(payload):
        print("FAIL: PATH-2 closure drift; run --generate")
        return 1
    passed = sum(item["passed"] for item in checks)
    print(f"PATH-2 {payload['status']}: {passed}/{len(checks)} closure checks passed")
    return 0 if payload["status"] == "CLOSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
