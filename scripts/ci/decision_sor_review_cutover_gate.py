#!/usr/bin/env python3
"""WX-10.7 — SoR-promotion cutover-prep gate (DEPLOYED-DECISION-SOR-PROMOTION).

WX-10.7 landed the reviewer transition (review_state / candidate_lineage_id / decision_reviews).
Promoting decision-service to a deployed SoR is an operational cutover, but the cutover *toolkit*
must be WX-10.7-aware so an operator never has to re-engineer during the flip. This gate is
self-enforcing: it fails if the review layer is not reflected in the backfill/quarantine verifier,
the rollback plan, readiness, the observable migrate step, the compose opt-in passthrough, the
ownership registry, or the cutover docs. It is a STATIC text check — it runs nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CHECKS = {
    "services/decision-service/backfill.py": [
        "--verify-review",
        "classify_candidates",
        "quarantine",
        "candidate_lineage_id",
    ],
    "services/decision-service/rollback.py": [
        "decision_reviews",
        "append-only",
        "preserve WX-10.7 review audit",
    ],
    "services/decision-service/main.py": [
        "_db_readiness",
        "migrations_current",
        "db_reachable",
    ],
    "scripts/deploy/decision_service_migrate.sh": [
        "migration_runner.py",
        "--apply",
        "backfill.py",
        "--verify-review",
        "DECISION_SERVICE_ALLOW_SCHEMA_CHANGE",
    ],
    "docs/architecture/DECISION_SERVICE_SOR_MIGRATION.md": [
        "002_decision_review.sql",
        "decision_reviews",
        "--verify-review",
    ],
    "docs/architecture/DECISION_SERVICE_SOR_CUTOVER_READINESS.md": [
        "--verify-review",
        "migrations_current",
    ],
    "docs/runbooks/DECISION_SERVICE_SOR_PRODUCTION_PROMOTION_RUNBOOK.md": [
        "decision_service_migrate.sh",
        "post-cutover review proof",
    ],
    "docs/architecture/db_ownership.yml": [
        "decision_reviews",
    ],
    "docker-compose.v9.yml": [
        "DECISION_SERVICE_DATABASE_URL",
    ],
    "docker-compose.fixed.yml": [
        "DECISION_SERVICE_DATABASE_URL",
    ],
}


def main() -> int:
    violations: list[str] = []
    for rel, tokens in CHECKS.items():
        path = ROOT / rel
        if not path.exists():
            violations.append(f"{rel}: missing (required WX-10.7 cutover-prep artifact)")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in tokens:
            if token not in text:
                violations.append(f"{rel}: missing token {token!r}")

    # The opt-in DB passthrough must default EMPTY (mirror stays safe until the operator flips).
    for compose in ("docker-compose.v9.yml", "docker-compose.fixed.yml"):
        text = (ROOT / compose).read_text(encoding="utf-8", errors="ignore")
        if "${DECISION_SERVICE_DATABASE_URL:-}" not in text:
            violations.append(
                f"{compose}: decision-service DATABASE_URL must be an opt-in passthrough that "
                "defaults empty (${DECISION_SERVICE_DATABASE_URL:-}) so mirror mode stays safe"
            )

    if violations:
        print("decision_sor_review_cutover_gate_failed")
        print("\n".join(violations))
        return 1
    print("decision_sor_review_cutover_gate_ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
