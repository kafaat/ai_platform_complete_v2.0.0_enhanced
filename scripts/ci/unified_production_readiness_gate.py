#!/usr/bin/env python3
"""Run canonical static production gates and emit one machine-readable verdict.

Static success means release-candidate readiness only. Production certification
additionally requires all target-environment P-CERT evidence files to be verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / "certification" / "evidence" / "unified_readiness_summary.json"
CHECKS = (
    ("ci_contract", [sys.executable, "scripts/ci/validate_ci_gates.py", "--root", "."]),
    ("production_honesty", [sys.executable, "scripts/ci/production_honesty_guard.py"]),
    ("production_truth", [sys.executable, "scripts/ci/production_truth_readiness_gate.py"]),
    ("runtime_contract", [sys.executable, "scripts/ci/runtime_readiness_contract_gate.py"]),
    ("minio_isolation", [sys.executable, "scripts/ci/minio_s3_contract_gate.py"]),
    ("supply_chain", [sys.executable, "scripts/ci/container_image_pin_guard.py"]),
    ("release_attestation", [sys.executable, "scripts/ci/release_attestation_guard.py"]),
    ("secret_history_scan", [sys.executable, "scripts/ci/secret_history_scan_guard.py"]),
    ("github_actions_policy", [sys.executable, "scripts/ci/github_actions_policy_guard.py"]),
    ("waiver_expiry", [sys.executable, "scripts/ci/waiver_expiry_guard.py"]),
    ("frontend_reproducibility", [sys.executable, "scripts/ci/frontend_reproducibility_guard.py"]),
    ("scene_provenance_ui", [sys.executable, "scripts/ci/scene_provenance_ui_guard.py"]),
    ("evidence_pack", [sys.executable, "scripts/ci/production_evidence_pack_guard.py", "--check"]),
    (
        "certification_checklist",
        [sys.executable, "scripts/ci/production_certification_checklist_guard.py", "--check"],
    ),
    (
        "release_package",
        [sys.executable, "scripts/release/validate_release_package.py", "--root", "."],
    ),
    ("dependency_resolution", [sys.executable, "scripts/ci/pip_audit_resolution_guard.py"]),
)

# These require installed toolchains, a built artifact, Git history, or a live target.
# Listing them in the verdict prevents `static_ready` from being mistaken for a full
# test/certification run while keeping this source-only gate deterministic.
EXTERNAL_OR_TOOLCHAIN_GATES = (
    "python_and_raster_test_suites",
    "frontend_typecheck_vitest_and_build",
    "playwright_real_browser",
    "npm_and_pip_vulnerability_audits",
    "release_archive_scan_and_signature",
    "live_database_messaging_models_restore_and_soak",
)


def _run(name: str, command: list[str]) -> dict[str, object]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = (result.stdout + result.stderr).strip()
    return {
        "name": name,
        "status": "passed" if result.returncode == 0 else "failed",
        "exit_code": result.returncode,
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
        "output_tail": output[-1200:],
    }


def _certification_status() -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "scripts/ci/production_certification_blockers_status.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        return {"production_certified": False, "error": result.stderr[-500:]}
    status = json.loads(result.stdout)
    qdrant = ROOT / "certification/evidence/qdrant_restore_drill_summary.json"
    status["qdrant_restore_drill"] = (
        json.loads(qdrant.read_text(encoding="utf-8"))
        if qdrant.exists()
        else {"status": "missing", "required_for_disaster_recovery": True}
    )
    sim_golden = ROOT / "certification/evidence/sim_golden_summary.json"
    status["sim_golden"] = (
        json.loads(sim_golden.read_text(encoding="utf-8"))
        if sim_golden.exists()
        else {"status": "missing", "eligible_for_promotion": False}
    )
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--require-certified", action="store_true")
    parser.add_argument("--check", action="store_true", help="run without writing a report")
    args = parser.parse_args()

    checks = [_run(name, command) for name, command in CHECKS]
    static_ready = all(row["status"] == "passed" for row in checks)
    certification = _certification_status()
    certified = static_ready and bool(certification.get("production_certified"))
    verdict = (
        "production_certified"
        if certified
        else ("release_candidate" if static_ready else "blocked")
    )
    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "verdict": verdict,
        "static_ready": static_ready,
        "production_certified": certified,
        "scope": "static_source_contracts_only",
        "not_executed_by_this_gate": list(EXTERNAL_OR_TOOLCHAIN_GATES),
        "checks": checks,
        "certification": certification,
    }
    if not args.check:
        report = args.report if args.report.is_absolute() else ROOT / args.report
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not static_ready or (args.require_certified and not certified):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
