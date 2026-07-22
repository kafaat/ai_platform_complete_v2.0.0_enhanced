#!/usr/bin/env python3
"""Static gate for P0-3 decision-service shadow/promotion controls."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = [
    ROOT / "services" / "decision-service" / "cutover.py",
    ROOT / "services" / "sahool-platform" / "api" / "decision_sor_mode.py",
    ROOT
    / "services"
    / "sahool-platform"
    / "tests"
    / "test_p0_3_decision_sor_shadow_promotion_guard.py",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def require(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def main() -> None:
    for path in REQUIRED:
        require(path.exists(), f"missing required cutover artifact: {path}")
    cutover = read(REQUIRED[0])
    mode = read(REQUIRED[1])
    main_py = read(ROOT / "services" / "decision-service" / "main.py")
    workflow = read(ROOT / ".github" / "workflows" / "field-workspace-production-closure.yml")

    for token in (
        "DECISION_SERVICE_MIGRATIONS_VERIFIED",
        "DECISION_SERVICE_BACKFILL_VERIFIED",
        "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED",
        "DECISION_SERVICE_OUTBOX_VERIFIED",
        "DECISION_SERVICE_STAGING_CUTOVER_APPROVED",
        "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
        "can_demote_platform",
    ):
        require(token in cutover, f"cutover readiness missing {token}")
    for token in (
        "SAHOOL_DECISION_WRITE_MODE",
        "platform_writes_required",
        "strict_decision_service_required",
        "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
    ):
        require(token in mode, f"platform mode contract missing {token}")
    require(
        "/v1/cutover/readiness" in main_py,
        "decision-service missing runtime cutover readiness endpoint",
    )
    require(
        "decision_sor_shadow_promotion_gate.py" in workflow, "CI does not run shadow promotion gate"
    )
    require(
        "test_p0_3_decision_sor_shadow_promotion_guard.py" in workflow, "CI does not run P0-3 guard"
    )
    print("Decision SoR shadow promotion gate passed")


if __name__ == "__main__":
    main()
