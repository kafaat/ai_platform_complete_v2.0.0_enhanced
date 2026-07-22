#!/usr/bin/env python3
"""Static gate for P0-4 decision-service staging probe harness."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "services" / "decision-service" / "staging_probe.py"
WORKFLOW = ROOT / ".github" / "workflows" / "field-workspace-production-closure.yml"
TEST = (
    ROOT
    / "services"
    / "sahool-platform"
    / "tests"
    / "test_p0_4_decision_sor_staging_probe_guard.py"
)
RUNBOOK = ROOT / "docs" / "runbooks" / "DECISION_SERVICE_SOR_STAGING_PROBE_RUNBOOK.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def require(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def main() -> None:
    for path in (PROBE, WORKFLOW, TEST, RUNBOOK):
        require(path.exists(), f"missing required P0-4 artifact: {path.relative_to(ROOT)}")
    probe = read(PROBE)
    workflow = read(WORKFLOW)
    runbook = read(RUNBOOK)
    for token in (
        "DECISION_SERVICE_STAGING_PROBE_APPROVED",
        "DECISION_SERVICE_STAGING_PROBE_ALLOW_LIVE",
        "SAHOOL_ENV",
        "Refusing to run the staging probe in production",
        "migration_runner.py",
        "backfill.py",
        "/v1/cutover/readiness",
        "SAHOOL_DECISION_WRITE_MODE",
        "--sample-write",
        "idempotency-key",
    ):
        require(token in probe, f"staging probe missing {token}")
    require("decision_sor_staging_probe_gate.py" in workflow, "CI must run staging probe gate")
    require("test_p0_4_decision_sor_staging_probe_guard.py" in workflow, "CI must run P0-4 guard")
    for phrase in (
        "dry-run first",
        "DECISION_SERVICE_STAGING_PROBE_APPROVED=true",
        "DECISION_SERVICE_STAGING_PROBE_ALLOW_LIVE=true",
        "SAHOOL_ENV=staging",
        "do not run in production",
    ):
        require(phrase in runbook, f"staging probe runbook missing: {phrase}")
    print("Decision SoR staging probe gate passed")


if __name__ == "__main__":
    main()
