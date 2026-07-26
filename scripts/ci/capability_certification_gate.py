#!/usr/bin/env python3
"""Evaluate capability certification readiness without granting certification."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "capabilities/registry/capabilities.json"
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


def evaluate(cap: dict) -> dict:
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
    eligible = all(gates.values()) and cap["maturity"] == 5 and cap["evidence_level"] == 5
    return {
        "id": cap["id"],
        "title": cap["title"],
        **gates,
        "gates_passed": passed,
        "gates_total": len(gates),
        "readiness_percent": round(100 * passed / len(gates), 1),
        "eligible_for_certification": eligible,
        "certified": cap["production_certified"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    rows = [evaluate(c) for c in data["capabilities"]]
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
        "Certification requires all nine gates plus maturity/evidence level 5.",
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
