#!/usr/bin/env python3
"""Generate and validate a fail-closed runtime verification plan.

The generated plan is derived from runtime contracts. Evidence is never marked
verified by repository discovery alone. Live evidence must be produced by
runtime_probe.py and pass schema/integrity checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "runtime-contracts" / "generated" / "runtime_contracts.json"
OUT_DIR = ROOT / "runtime-verification" / "generated"
PLAN = OUT_DIR / "runtime_probe_plan.json"
SUMMARY = OUT_DIR / "runtime_verification_summary.json"
REPORT = OUT_DIR / "RUNTIME_VERIFICATION_HARNESS.md"
EVIDENCE_DIR = ROOT / "runtime-verification" / "evidence"
SCHEMA_VERSION = "1.0"


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def build() -> tuple[dict[str, Any], dict[str, Any], str]:
    source = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    probes: list[dict[str, Any]] = []
    for service in source["services"]:
        endpoints = service["endpoints"]
        service_probes: list[dict[str, str]] = []
        for kind in ("health", "readiness", "metrics"):
            for path in endpoints.get(kind, []):
                service_probes.append({"kind": kind, "method": "GET", "path": path})
        probes.append(
            {
                "service": service["service"],
                "source_service": service["source_service"],
                "base_url_env": f"{service['service'].upper().replace('-', '_')}_BASE_URL",
                "probes": sorted(service_probes, key=lambda p: (p["kind"], p["path"])),
                "required_evidence_fields": [
                    "schema_version",
                    "service",
                    "tested_sha",
                    "environment_id",
                    "started_at",
                    "completed_at",
                    "probe_results",
                    "plan_sha256",
                ],
                "runtime_verified": False,
                "production_certified": False,
            }
        )
    plan_core = {
        "schema_version": SCHEMA_VERSION,
        "source_contract_sha256": hashlib.sha256(CONTRACTS.read_bytes()).hexdigest(),
        "fail_closed": True,
        "services": sorted(probes, key=lambda p: p["service"]),
    }
    plan = dict(plan_core)
    plan["plan_sha256"] = digest(plan_core)

    evidence_files = sorted(EVIDENCE_DIR.glob("*.json")) if EVIDENCE_DIR.exists() else []
    valid_evidence = 0
    invalid: list[str] = []
    for path in evidence_files:
        try:
            evidence = json.loads(path.read_text(encoding="utf-8"))
            required = {
                "schema_version",
                "service",
                "tested_sha",
                "environment_id",
                "started_at",
                "completed_at",
                "probe_results",
                "plan_sha256",
            }
            ok = required.issubset(evidence) and evidence["plan_sha256"] == plan["plan_sha256"]
            ok = ok and bool(evidence["tested_sha"]) and bool(evidence["environment_id"])
            ok = ok and bool(evidence["probe_results"])
            ok = ok and all(
                r.get("status") == "passed"
                and isinstance(r.get("latency_ms"), (int, float))
                and r.get("response_sha256")
                for r in evidence["probe_results"]
            )
            if ok:
                valid_evidence += 1
            else:
                invalid.append(path.name)
        except (OSError, ValueError, TypeError):
            invalid.append(path.name)

    services_with_probes = sum(1 for s in probes if s["probes"])
    summary = {
        "schema_version": SCHEMA_VERSION,
        "services": len(probes),
        "services_with_probeable_endpoints": services_with_probes,
        "services_without_probeable_endpoints": len(probes) - services_with_probes,
        "planned_probes": sum(len(s["probes"]) for s in probes),
        "evidence_files": len(evidence_files),
        "valid_live_evidence_files": valid_evidence,
        "invalid_or_stale_evidence_files": invalid,
        "runtime_verified_services": valid_evidence,
        "production_certified_services": 0,
        "static_plan_only": valid_evidence == 0,
    }
    lines = [
        "# SAHOOL Runtime Verification Harness",
        "",
        "> Fail-closed plan. Repository discovery never counts as live runtime evidence.",
        "",
        "## Summary",
        "",
        f"- Services: **{summary['services']}**",
        f"- Services with probeable endpoints: **{services_with_probes}**",
        f"- Planned probes: **{summary['planned_probes']}**",
        f"- Valid live evidence files: **{valid_evidence}**",
        f"- Runtime verified services: **{valid_evidence}**",
        "- Production certified services: **0**",
        "",
        "## Evidence contract",
        "",
        "Each evidence file must bind the tested Git SHA, environment identifier, exact plan hash, timestamps, status, latency, and response SHA-256. Any stale or incomplete evidence is rejected.",
        "",
        "## Service probe coverage",
        "",
        "| Service | Planned probes | Evidence state |",
        "|---|---:|---|",
    ]
    for item in probes:
        lines.append(f"| {item['service']} | {len(item['probes'])} | not verified |")
    return plan, summary, "\n".join(lines) + "\n"


def write() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    plan, summary, report = build()
    PLAN.write_text(canonical(plan), encoding="utf-8")
    SUMMARY.write_text(canonical(summary), encoding="utf-8")
    REPORT.write_text(report, encoding="utf-8")


def check() -> int:
    expected = build()
    files = (PLAN, SUMMARY, REPORT)
    rendered = (canonical(expected[0]), canonical(expected[1]), expected[2])
    drift = [
        str(p.relative_to(ROOT))
        for p, content in zip(files, rendered, strict=False)
        if not p.exists() or p.read_text(encoding="utf-8") != content
    ]
    if drift:
        print("runtime verification harness drift: " + ", ".join(drift))
        return 1
    if expected[1]["invalid_or_stale_evidence_files"]:
        print(
            "invalid/stale runtime evidence: "
            + ", ".join(expected[1]["invalid_or_stale_evidence_files"])
        )
        return 1
    print(
        f"runtime verification harness PASS: {expected[1]['planned_probes']} probes; {expected[1]['valid_live_evidence_files']} valid evidence files"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.generate:
        write()
        return 0
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
