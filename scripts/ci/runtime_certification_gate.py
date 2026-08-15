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
APPLY_LEDGER_DIR = ROOT / "runtime-verification/apply-ledger"
FIELD_AUTHORITY_POLICY = ROOT / "docs/capability-registry/field_authority_policy.json"
AUTH_RECEIPT_TYPE = "attested-runtime-verification"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_authority_policy() -> dict[str, Any]:
    policy = json.loads(FIELD_AUTHORITY_POLICY.read_text(encoding="utf-8"))
    fields = policy.get("field_authority", {})
    if policy.get("schema") != "sahool.capability-field-authority/v1":
        raise ValueError("capability field authority policy schema mismatch")
    if fields.get("runtime_verified", {}).get("authority") != "runtime_verification":
        raise ValueError("runtime_verified authority must be runtime_verification")
    if fields.get("runtime.verification_receipts", {}).get("authority") != "runtime_verification":
        raise ValueError("runtime verification receipt authority mismatch")
    if fields.get("runtime.verification_receipts", {}).get("receipt_type") != AUTH_RECEIPT_TYPE:
        raise ValueError("runtime verification receipt type mismatch")
    if fields.get("production_certified", {}).get("authority") != "certification":
        raise ValueError("production_certified authority mismatch")
    return policy


def governed_receipts(cap: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Return receipts whose append-only application ledger corroborates the registry copy."""
    valid: list[dict[str, Any]] = []
    errors: list[str] = []
    for receipt in cap.get("runtime", {}).get("receipts", []) or []:
        if not isinstance(receipt, dict) or receipt.get("type") != AUTH_RECEIPT_TYPE:
            continue
        app_id = str(receipt.get("application_id", ""))
        if len(app_id) != 64 or any(ch not in "0123456789abcdef" for ch in app_id):
            errors.append("malformed_application_id")
            continue
        ledger_path = APPLY_LEDGER_DIR / f"{app_id}.json"
        if not ledger_path.is_file():
            errors.append("application_ledger_missing")
            continue
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append("application_ledger_unreadable")
            continue
        expected = {
            "application_id": app_id,
            "candidate_id": receipt.get("candidate_id"),
            "approval_run_id": receipt.get("approval_run_id"),
            "target_sha": receipt.get("target_sha"),
            "environment_id": receipt.get("environment_id"),
        }
        if any(ledger.get(k) != v for k, v in expected.items()):
            errors.append("application_ledger_mismatch")
            continue
        if cap.get("id") not in (ledger.get("capabilities") or []):
            errors.append("capability_missing_from_application_ledger")
            continue
        valid.append(receipt)
    return valid, errors


def runtime_authority_verified(
    runtime_claim: bool,
    required_verified: bool,
    receipts: list[dict[str, Any]],
    receipt_errors: list[str],
) -> bool:
    """The only capability-level runtime truth accepted by downstream maturity logic."""
    return runtime_claim and required_verified and bool(receipts) and not receipt_errors


def build() -> tuple[dict[str, Any], str]:
    load_authority_policy()
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
        receipts, receipt_errors = governed_receipts(cap)
        authority_verified = runtime_authority_verified(
            runtime_claim, required_verified, receipts, receipt_errors
        )
        if runtime_claim and not required_verified:
            capability_claim_violations.append(f"{cap['id']}:runtime_without_all_services")
        if runtime_claim and not receipts:
            capability_claim_violations.append(f"{cap['id']}:runtime_without_governed_receipt")
        for reason in sorted(set(receipt_errors)):
            capability_claim_violations.append(f"{cap['id']}:runtime_receipt_{reason}")
        if receipts and not runtime_claim:
            capability_claim_violations.append(
                f"{cap['id']}:governed_receipt_without_runtime_claim"
            )
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
                "governed_runtime_receipt_count": len(receipts),
                "runtime_authority_verified": authority_verified,
                "production_certified_claim": production_claim,
            }
        )
    summary = {
        "fail_closed": True,
        "runtime_verified_services": sorted(verified_services),
        "runtime_authority_verified_capabilities": sorted(
            c["id"] for c in capabilities if c["runtime_authority_verified"]
        ),
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
        f"- Capability authority-verified: **{len(summary['runtime_authority_verified_capabilities'])}**",
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
