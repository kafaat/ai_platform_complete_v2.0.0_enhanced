#!/usr/bin/env python3
"""Fail closed when runtime or production certification exceeds accepted evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "runtime-verification/generated/runtime_evidence_ledger.json"
REGISTRY = ROOT / "capabilities/registry/capabilities.json"
OUT = ROOT / "runtime-verification/generated/runtime_certification_summary.json"
REPORT = ROOT / "runtime-verification/generated/RUNTIME_CERTIFICATION_GATE.md"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build() -> tuple[dict[str, Any], str]:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    verified_services = {s["service"] for s in ledger["services"] if s["runtime_verified"]}
    service_claim_violations = [
        s["service"]
        for s in ledger["services"]
        if s.get("production_certified") and not s["runtime_verified"]
    ]
    capabilities = []
    capability_claim_violations = []
    for cap in registry["capabilities"]:
        services = sorted(set(cap.get("services", [])))
        required_verified = bool(services) and all(s in verified_services for s in services)
        runtime_claim = bool(cap.get("runtime_verified", False))
        production_claim = bool(cap.get("production_certified", False))
        if runtime_claim and not required_verified:
            capability_claim_violations.append(f"{cap['id']}:runtime_without_all_services")
        if production_claim:
            capability_claim_violations.append(
                f"{cap['id']}:production_claim_requires_explicit_external_decision"
            )
        capabilities.append(
            {
                "id": cap["id"],
                "services": services,
                "all_services_runtime_verified": required_verified,
                "runtime_verified_claim": runtime_claim,
                "production_certified_claim": production_claim,
            }
        )
    summary = {
        "fail_closed": True,
        "runtime_verified_services": sorted(verified_services),
        "production_certified_services": [],
        "service_claim_violations": sorted(service_claim_violations),
        "capability_claim_violations": sorted(capability_claim_violations),
        "capabilities": capabilities,
        "gate_passed": not service_claim_violations and not capability_claim_violations,
    }
    lines = [
        "# SAHOOL Runtime Certification Gate",
        "",
        "> Runtime verification is evidence-derived. Production certification remains an explicit external release decision.",
        "",
        f"- Runtime verified services: **{len(verified_services)}**",
        "- Production certified services: **0**",
        f"- Service claim violations: **{len(service_claim_violations)}**",
        f"- Capability claim violations: **{len(capability_claim_violations)}**",
        f"- Gate passed: **{str(summary['gate_passed']).lower()}**",
        "",
    ]
    return summary, "\n".join(lines)


def generate() -> None:
    summary, report = build()
    OUT.write_text(canonical(summary), encoding="utf-8")
    REPORT.write_text(report, encoding="utf-8")


def check(strict: bool) -> int:
    summary, report = build()
    drift = []
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != canonical(summary):
        drift.append(str(OUT.relative_to(ROOT)))
    if not REPORT.exists() or REPORT.read_text(encoding="utf-8") != report:
        drift.append(str(REPORT.relative_to(ROOT)))
    if drift:
        print("runtime certification gate drift: " + ", ".join(drift))
        return 1
    if not summary["gate_passed"]:
        print("runtime certification claim violations detected")
        return 1
    if strict and not summary["runtime_verified_services"]:
        print("strict runtime certification requires at least one verified service")
        return 1
    print(
        f"runtime certification gate PASS: {len(summary['runtime_verified_services'])} verified; 0 certified"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--check", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if args.generate:
        generate()
        return 0
    return check(args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
