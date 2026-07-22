#!/usr/bin/env python3
"""Decision SoR read-side comparison harness.

Purpose
-------
Compare sahool-platform's current authoritative read side with the decision-service
candidate read side before promotion. The harness is safe by default:
- dry-run is the default;
- live mode requires explicit approval;
- no writes are performed here;
- production mode is allowed only for read-only checks with a separate approval flag.

This is a cutover safety tool, not an application dependency.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import request

ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "services" / "decision-service"

APPROVAL_ENV = "DECISION_SERVICE_READ_COMPARE_APPROVED"
LIVE_ENV = "DECISION_SERVICE_READ_COMPARE_ALLOW_LIVE"
PROD_ENV = "DECISION_SERVICE_READ_COMPARE_ALLOW_PRODUCTION"
ENV_NAME_ENV = "SAHOOL_ENV"


@dataclass
class CompareStep:
    name: str
    ok: bool
    detail: str
    duration_ms: int = 0


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _json_get(url: str, timeout: float = 10.0) -> tuple[int, dict[str, Any]]:
    req = request.Request(url, method="GET", headers={"accept": "application/json"})
    with request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - operator-provided staging/prod URLs
        raw = res.read().decode("utf-8")
        return res.status, json.loads(raw or "{}")


def _run_command(name: str, cmd: list[str], env: dict[str, str]) -> CompareStep:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=90,
            check=False,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        tail = "\n".join((proc.stdout or "").splitlines()[-12:])
        return CompareStep(name, proc.returncode == 0, tail or f"exit={proc.returncode}", elapsed)
    except Exception as exc:  # pragma: no cover - operator path
        return CompareStep(name, False, str(exc), int((time.monotonic() - start) * 1000))


def _check_readiness(decision_service_url: str) -> CompareStep:
    start = time.monotonic()
    try:
        status, body = _json_get(decision_service_url.rstrip("/") + "/v1/cutover/readiness")
        elapsed = int((time.monotonic() - start) * 1000)
        ok = status == 200 and bool(body.get("can_enable_sor"))
        detail = json.dumps(
            {
                "status": status,
                "mode": body.get("mode"),
                "can_enable_sor": body.get("can_enable_sor"),
                "can_demote_platform": body.get("can_demote_platform"),
                "missing_gates": body.get("missing_gates"),
            },
            sort_keys=True,
        )
        return CompareStep("decision readiness", ok, detail, elapsed)
    except Exception as exc:  # pragma: no cover - operator path
        return CompareStep("decision readiness", False, str(exc))


def _compare_health(platform_url: str, decision_service_url: str) -> CompareStep:
    start = time.monotonic()
    try:
        platform_status, platform_body = _json_get(platform_url.rstrip("/") + "/healthz")
        decision_status, decision_body = _json_get(decision_service_url.rstrip("/") + "/healthz")
        elapsed = int((time.monotonic() - start) * 1000)
        ok = 200 <= platform_status < 300 and 200 <= decision_status < 300
        detail = json.dumps(
            {
                "platform_status": platform_status,
                "decision_status": decision_status,
                "platform_keys": sorted(platform_body.keys()),
                "decision_keys": sorted(decision_body.keys()),
            },
            sort_keys=True,
        )
        return CompareStep("platform/decision health comparison", ok, detail, elapsed)
    except Exception as exc:  # pragma: no cover - operator path
        return CompareStep("platform/decision health comparison", False, str(exc))


def _refuse_unsafe_live(env: dict[str, str]) -> None:
    env_name = env.get(ENV_NAME_ENV, "").strip().lower()
    if not _truthy(env.get(APPROVAL_ENV)):
        raise SystemExit(f"Live read-side comparison requires {APPROVAL_ENV}=true")
    if not _truthy(env.get(LIVE_ENV)):
        raise SystemExit(f"Live read-side comparison requires {LIVE_ENV}=true")
    if env_name in {"prod", "production"} and not _truthy(env.get(PROD_ENV)):
        raise SystemExit(f"Production read-side comparison requires {PROD_ENV}=true")


def run_compare(args: argparse.Namespace) -> dict[str, Any]:
    env = os.environ.copy()
    steps: list[CompareStep] = []

    if not args.live:
        steps.append(
            CompareStep(
                "dry-run safety", True, "live network/db checks skipped; pass --live with approvals"
            )
        )
        return {"mode": "dry-run", "ok": True, "steps": [asdict(step) for step in steps]}

    _refuse_unsafe_live(env)
    steps.append(
        _run_command(
            "migration check",
            [sys.executable, str(DECISION / "migration_runner.py"), "--check"],
            env,
        )
    )
    steps.append(
        _run_command(
            "backfill count verification",
            [sys.executable, str(DECISION / "backfill.py"), "--verify-counts"],
            env,
        )
    )
    steps.append(_check_readiness(args.decision_service_url))
    steps.append(_compare_health(args.platform_url, args.decision_service_url))

    ok = all(step.ok for step in steps)
    return {"mode": "live-read-compare", "ok": ok, "steps": [asdict(step) for step in steps]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decision SoR read-side comparison harness")
    parser.add_argument(
        "--live",
        action="store_true",
        help="run live read-only comparison; requires explicit approvals",
    )
    parser.add_argument(
        "--decision-service-url", default=os.getenv("DECISION_SERVICE_URL", "http://localhost:8097")
    )
    parser.add_argument(
        "--platform-url", default=os.getenv("SAHOOL_PLATFORM_URL", "http://localhost:8000")
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    result = run_compare(build_parser().parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
