#!/usr/bin/env python3
"""Static cutover-readiness gate for decision-service SoR promotion.

This is intentionally a static CI gate. Live DB checks are performed by:
- services/decision-service/migration_runner.py --check
- services/decision-service/backfill.py --verify-counts
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "services" / "decision-service"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def require(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def main() -> None:
    runner = DECISION / "migration_runner.py"
    backfill = DECISION / "backfill.py"
    main_py = DECISION / "main.py"
    persistence = DECISION / "persistence.py"
    workflow = ROOT / ".github" / "workflows" / "field-workspace-production-closure.yml"
    runbook = ROOT / "docs" / "runbooks" / "DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md"

    for path in (runner, backfill, main_py, persistence, workflow, runbook):
        require(path.exists(), f"Missing required cutover artifact: {path.relative_to(ROOT)}")

    runner_text = read(runner)
    require(
        "DECISION_SERVICE_ALLOW_SCHEMA_CHANGE" in runner_text,
        "Migration runner must require explicit schema-change approval",
    )
    require(
        "pg_advisory_xact_lock" in runner_text, "Migration runner must serialize schema changes"
    )
    require(
        "decision_service_schema_migrations" in runner_text,
        "Migration runner must track applied migrations",
    )
    require("checksum" in runner_text, "Migration runner must detect migration drift")
    require(
        "--check" in runner_text and "--apply" in runner_text,
        "Migration runner must support check/apply modes",
    )

    backfill_text = read(backfill)
    for table in ("decision_record", "outcome_record", "online_learning_updates"):
        require(table in backfill_text, f"Backfill verifier must include {table}")
    require(
        "--verify-counts" in backfill_text,
        "Backfill tool must provide a non-mutating count verification mode",
    )
    require(
        "PLATFORM_DATABASE_URL" in backfill_text and "DECISION_DATABASE_URL" in backfill_text,
        "Backfill must be ready for split DB topology",
    )

    main_text = read(main_py)
    require(
        "sor_requested_without_db" in main_text,
        "readyz must fail closed when SoR is requested without DB",
    )
    require("DECISION_SERVICE_SOR_ENABLED" in main_text, "SoR mode must remain explicitly gated")
    require(
        "sahool-platform (temporary)" in main_text,
        "Platform must remain the temporary SoR before cutover",
    )

    persistence_text = read(persistence)
    require(
        "DECISION_SERVICE_SOR_ENABLED" in persistence_text and "DATABASE_URL" in persistence_text,
        "Persistence must be gated by env + DB",
    )
    require("decision_outbox_events" in persistence_text, "Persistence must emit outbox events")

    workflow_text = read(workflow)
    require(
        "decision_sor_cutover_readiness_gate.py" in workflow_text,
        "CI must run the cutover readiness gate",
    )
    require(
        "test_p0_2_decision_sor_cutover_readiness_guard.py" in workflow_text,
        "CI must run P0-2 guard tests",
    )

    runbook_text = read(runbook)
    for phrase in (
        "DECISION_SERVICE_SOR_ENABLED=true",
        "migration_runner.py --check",
        "backfill.py --verify-counts",
        "rollback",
        "do not demote sahool-platform",
    ):
        require(phrase in runbook_text, f"Runbook missing: {phrase}")

    print("Decision SoR cutover readiness gate passed")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Decision SoR cutover readiness gate failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
