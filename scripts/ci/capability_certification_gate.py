#!/usr/bin/env python3
"""Evaluate capability certification readiness without granting certification."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "capabilities/registry/capabilities.json"
RUNTIME_AUTHORITY = ROOT / "runtime-verification/generated/runtime_certification_summary.json"
OUT = ROOT / "capabilities/generated"

REQUIRED = (
    "service",
    "api",
    "test",
    "metrics",
    "traces",
    "receipts",
    "audit_events",
    "runtime_proof",
    "production_proof",
)


def load_promotion_preconditions() -> dict[str, dict]:
    """Per-capability promotion preconditions from the runtime authority summary.

    Fail closed: a missing summary or a capability absent from it reads as unsatisfied,
    so eligibility can never outrun the authority producer.
    """
    if not RUNTIME_AUTHORITY.exists():
        return {}
    summary = json.loads(RUNTIME_AUTHORITY.read_text(encoding="utf-8"))
    rows = summary.get("capabilities")
    if not isinstance(rows, list):
        return {}
    return {str(r.get("id")): r for r in rows if isinstance(r, dict) and r.get("id")}


def evaluate(cap: dict, preconditions: dict[str, dict]) -> dict:
    runtime = cap["runtime"]
    production_evidence = [e for e in cap.get("evidence", []) if e.get("type") == "production"]
    runtime_evidence = [e for e in cap.get("evidence", []) if e.get("type") == "runtime"]
    gates = {
        "service": bool(cap.get("services")),
        "api": bool(cap.get("apis")),
        "test": bool(cap.get("tests")),
        "metrics": bool(runtime.get("metrics")),
        "traces": bool(runtime.get("traces")),
        "receipts": bool(runtime.get("receipts")),
        "audit_events": bool(runtime.get("audit_events")),
        "runtime_proof": bool(runtime_evidence),
        "production_proof": bool(production_evidence),
    }
    passed = sum(gates.values())
    authority_row = preconditions.get(cap["id"], {})
    execution_outcome = authority_row.get("execution_outcome_satisfied") is True
    subject_sha_binding = authority_row.get("subject_sha_binding_satisfied") is True
    # An L5 declaration is necessary but never sufficient: certification eligibility
    # additionally requires a bound execution outcome and subject/SHA binding.
    eligible = (
        all(gates.values())
        and cap["maturity"] == 5
        and cap["evidence_level"] == 5
        and execution_outcome
        and subject_sha_binding
    )
    return {
        "id": cap["id"],
        "title": cap["title"],
        **gates,
        "gates_passed": passed,
        "gates_total": len(gates),
        "readiness_percent": round(100 * passed / len(gates), 1),
        "execution_outcome": execution_outcome,
        "subject_sha_binding": subject_sha_binding,
        "eligible_for_certification": eligible,
        "certified": cap["production_certified"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    preconditions = load_promotion_preconditions()
    rows = [evaluate(c, preconditions) for c in data["capabilities"]]
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "capability_certification_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = {
        "capabilities_total": len(rows),
        "eligible_for_certification": sum(r["eligible_for_certification"] for r in rows),
        "certified": sum(r["certified"] for r in rows),
        "incorrect_certifications": [
            r["id"] for r in rows if r["certified"] and not r["eligible_for_certification"]
        ],
        "top_ready": [
            {"id": r["id"], "readiness_percent": r["readiness_percent"]}
            for r in sorted(rows, key=lambda x: (-x["readiness_percent"], x["id"]))[:15]
        ],
    }
    (OUT / "capability_certification_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Capability Certification Readiness",
        "",
        "Certification requires all nine gates plus maturity/evidence level 5,",
        "plus a bound execution outcome and subject/SHA binding — level 5 alone is never sufficient.",
        "",
        "| Capability | Passed | Readiness | Eligible | Certified |",
        "|---|---:|---:|---|---|",
    ]
    for r in sorted(rows, key=lambda x: (-x["readiness_percent"], x["id"])):
        lines.append(
            f"| {r['id']} | {r['gates_passed']}/{r['gates_total']} | {r['readiness_percent']}% | {str(r['eligible_for_certification']).lower()} | {str(r['certified']).lower()} |"
        )
    (OUT / "CAPABILITY_CERTIFICATION_READINESS.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    if summary["incorrect_certifications"]:
        print("incorrect_capability_certification", summary["incorrect_certifications"])
        return 1
    if args.strict and any(r["eligible_for_certification"] != r["certified"] for r in rows):
        print("eligible_capabilities_require_explicit_certification_decision")
        return 1
    print("capability_certification_gate_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
