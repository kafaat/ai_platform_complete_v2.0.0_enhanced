#!/usr/bin/env python3
"""Decision SoR production promotion preflight.

This script does not mutate production by default. It verifies that every explicit
promotion gate is present before operators change runtime flags. It is designed to
make the final demotion of sahool-platform deliberate and auditable.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Any
from urllib import request

PROMOTION_APPROVAL_ENV = "DECISION_SERVICE_PRODUCTION_PROMOTION_APPROVED"
PROMOTION_LIVE_ENV = "DECISION_SERVICE_PRODUCTION_PROMOTION_ALLOW_LIVE"
ENV_NAME_ENV = "SAHOOL_ENV"
REQUIRED_TRUE_FLAGS = (
    "DECISION_SERVICE_SOR_ENABLED",
    "DECISION_SERVICE_MIGRATIONS_VERIFIED",
    "DECISION_SERVICE_BACKFILL_VERIFIED",
    "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED",
    "DECISION_SERVICE_OUTBOX_VERIFIED",
    "DECISION_SERVICE_STAGING_CUTOVER_APPROVED",
    "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
)


@dataclass
class PromotionCheck:
    name: str
    ok: bool
    detail: str


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _json_get(url: str, timeout: float = 10.0) -> tuple[int, dict[str, Any]]:
    req = request.Request(url, method="GET", headers={"accept": "application/json"})
    with request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - operator-provided production URL
        return res.status, json.loads(res.read().decode("utf-8") or "{}")


def _env_checks(env: dict[str, str]) -> list[PromotionCheck]:
    checks = [
        PromotionCheck(
            "environment is production",
            env.get(ENV_NAME_ENV, "").strip().lower() in {"prod", "production"},
            env.get(ENV_NAME_ENV, ""),
        ),
        PromotionCheck(
            "promotion approved", _truthy(env.get(PROMOTION_APPROVAL_ENV)), PROMOTION_APPROVAL_ENV
        ),
        PromotionCheck(
            "live promotion allowed", _truthy(env.get(PROMOTION_LIVE_ENV)), PROMOTION_LIVE_ENV
        ),
        PromotionCheck(
            "database url configured", bool(env.get("DATABASE_URL", "").strip()), "DATABASE_URL"
        ),
    ]
    for flag in REQUIRED_TRUE_FLAGS:
        checks.append(PromotionCheck(f"{flag}=true", _truthy(env.get(flag)), flag))
    return checks


def _readiness_check(decision_service_url: str) -> PromotionCheck:
    try:
        status, body = _json_get(decision_service_url.rstrip("/") + "/v1/cutover/readiness")
        ok = (
            status == 200
            and bool(body.get("can_demote_platform"))
            and bool(body.get("production_approved"))
        )
        return PromotionCheck(
            "decision-service readiness allows platform demotion",
            ok,
            json.dumps(
                {
                    "status": status,
                    "mode": body.get("mode"),
                    "can_enable_sor": body.get("can_enable_sor"),
                    "can_demote_platform": body.get("can_demote_platform"),
                    "missing_gates": body.get("missing_gates"),
                },
                sort_keys=True,
            ),
        )
    except Exception as exc:  # pragma: no cover - operator path
        return PromotionCheck(
            "decision-service readiness allows platform demotion", False, str(exc)
        )


def run_preflight(args: argparse.Namespace) -> dict[str, Any]:
    env = os.environ.copy()
    if not args.live:
        return {
            "mode": "dry-run",
            "ok": True,
            "message": "promotion preflight is dry-run; pass --live in production with explicit approvals",
            "required_flags": list(REQUIRED_TRUE_FLAGS)
            + [PROMOTION_APPROVAL_ENV, PROMOTION_LIVE_ENV],
        }
    checks = _env_checks(env)
    checks.append(_readiness_check(args.decision_service_url))
    ok = all(check.ok for check in checks)
    return {
        "mode": "live-production-preflight",
        "ok": ok,
        "checks": [asdict(check) for check in checks],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decision SoR production promotion preflight")
    parser.add_argument(
        "--live", action="store_true", help="run live production preflight; no writes are performed"
    )
    parser.add_argument(
        "--decision-service-url", default=os.getenv("DECISION_SERVICE_URL", "http://localhost:8097")
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    result = run_preflight(build_parser().parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
