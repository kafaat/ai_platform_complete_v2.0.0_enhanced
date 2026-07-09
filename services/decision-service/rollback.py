#!/usr/bin/env python3
"""Decision SoR rollback preflight and operator plan.

Rollback must return Sahool to `sahool-platform` as Source of Record first, then
verify mirrored decision-service data without destructive deletes. This script prints
an auditable plan and refuses live mode without explicit approval.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Any

ROLLBACK_APPROVAL_ENV = "DECISION_SERVICE_ROLLBACK_APPROVED"
ROLLBACK_LIVE_ENV = "DECISION_SERVICE_ROLLBACK_ALLOW_LIVE"
ENV_NAME_ENV = "SAHOOL_ENV"


@dataclass
class RollbackStep:
    order: int
    name: str
    command_or_action: str
    destructive: bool = False


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _plan() -> list[RollbackStep]:
    return [
        RollbackStep(
            1, "freeze decision-service promotion", "set DECISION_SERVICE_SOR_ENABLED=false"
        ),
        RollbackStep(2, "restore platform writer", "set SAHOOL_DECISION_WRITE_MODE=platform_sor"),
        RollbackStep(
            3,
            "disable strict service dependency",
            "unset DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
        ),
        RollbackStep(
            4, "verify platform writes", "run platform decision_record integration smoke test"
        ),
        RollbackStep(
            5,
            "verify no destructive cleanup",
            "keep decision-service tables for forensic comparison",
        ),
        RollbackStep(
            6, "compare reads", "python services/decision-service/read_side_compare.py --live"
        ),
        RollbackStep(
            7,
            "resume mirror mode",
            "set SAHOOL_DECISION_WRITE_MODE=shadow only after platform write smoke passes",
        ),
    ]


def run_rollback(args: argparse.Namespace) -> dict[str, Any]:
    env = os.environ.copy()
    plan = _plan()
    if not args.live:
        return {"mode": "dry-run", "ok": True, "plan": [asdict(step) for step in plan]}
    ok = _truthy(env.get(ROLLBACK_APPROVAL_ENV)) and _truthy(env.get(ROLLBACK_LIVE_ENV))
    if not ok:
        return {
            "mode": "live-rollback-preflight",
            "ok": False,
            "error": f"live rollback requires {ROLLBACK_APPROVAL_ENV}=true and {ROLLBACK_LIVE_ENV}=true",
            "environment": env.get(ENV_NAME_ENV, ""),
            "plan": [asdict(step) for step in plan],
        }
    return {
        "mode": "live-rollback-preflight",
        "ok": True,
        "message": "approval present; apply the non-destructive operator plan in order",
        "environment": env.get(ENV_NAME_ENV, ""),
        "plan": [asdict(step) for step in plan],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decision SoR rollback preflight")
    parser.add_argument(
        "--live",
        action="store_true",
        help="verify live rollback approvals; no destructive action is performed",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    result = run_rollback(build_parser().parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
