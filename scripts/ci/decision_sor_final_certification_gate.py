#!/usr/bin/env python3
"""Static gate for P0-5/P0-6 Decision SoR final certification controls."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
READ_COMPARE = ROOT / "services" / "decision-service" / "read_side_compare.py"
PROMOTION = ROOT / "services" / "decision-service" / "production_promotion.py"
ROLLBACK = ROOT / "services" / "decision-service" / "rollback.py"
WORKFLOW = ROOT / ".github" / "workflows" / "field-workspace-production-closure.yml"
TEST = (
    ROOT
    / "services"
    / "sahool-platform"
    / "tests"
    / "test_p0_5_decision_sor_final_certification_guard.py"
)
RUNBOOK = ROOT / "docs" / "runbooks" / "DECISION_SERVICE_SOR_PRODUCTION_PROMOTION_RUNBOOK.md"
ARCH = ROOT / "docs" / "architecture" / "DECISION_SERVICE_SOR_FINAL_CERTIFICATION.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def require(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def main() -> None:
    for path in (READ_COMPARE, PROMOTION, ROLLBACK, WORKFLOW, TEST, RUNBOOK, ARCH):
        require(
            path.exists(),
            f"missing required Decision SoR final certification artifact: {path.relative_to(ROOT)}",
        )

    read_compare = read(READ_COMPARE)
    promotion = read(PROMOTION)
    rollback = read(ROLLBACK)
    workflow = read(WORKFLOW)
    runbook = read(RUNBOOK)
    arch = read(ARCH)

    for token in (
        "DECISION_SERVICE_READ_COMPARE_APPROVED",
        "DECISION_SERVICE_READ_COMPARE_ALLOW_LIVE",
        "DECISION_SERVICE_READ_COMPARE_ALLOW_PRODUCTION",
        "migration_runner.py",
        "backfill.py",
        "/v1/cutover/readiness",
        "no writes are performed",
    ):
        require(token in read_compare, f"read_side_compare missing {token}")

    for token in (
        "DECISION_SERVICE_PRODUCTION_PROMOTION_APPROVED",
        "DECISION_SERVICE_PRODUCTION_PROMOTION_ALLOW_LIVE",
        "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
        "can_demote_platform",
        "dry-run",
        "no writes are performed",
    ):
        require(token in promotion, f"production_promotion missing {token}")

    for token in (
        "DECISION_SERVICE_ROLLBACK_APPROVED",
        "DECISION_SERVICE_ROLLBACK_ALLOW_LIVE",
        "SAHOOL_DECISION_WRITE_MODE=platform_sor",
        "non-destructive",
        "read_side_compare.py --live",
    ):
        require(token in rollback, f"rollback missing {token}")

    require(
        "decision_sor_final_certification_gate.py" in workflow,
        "CI must run final certification gate",
    )
    require(
        "test_p0_5_decision_sor_final_certification_guard.py" in workflow,
        "CI must run P0-5/P0-6 guard",
    )

    for phrase in (
        "read-side comparison",
        "production promotion preflight",
        "rollback plan",
        "do not delete decision-service tables during rollback",
        "DECISION_SERVICE_PRODUCTION_PROMOTION_APPROVED=true",
    ):
        require(phrase in runbook, f"production promotion runbook missing: {phrase}")

    for phrase in (
        "final certification",
        "read-side comparison",
        "promotion is not a single flag",
        "rollback is non-destructive",
    ):
        require(phrase in arch, f"final certification architecture doc missing: {phrase}")

    print("Decision SoR final certification gate passed")


if __name__ == "__main__":
    main()
