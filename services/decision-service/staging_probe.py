#!/usr/bin/env python3
"""Decision-service SoR staging probe harness.

This probe is intentionally safe by default:
- dry-run is the default mode;
- live mode requires an explicit staging approval flag;
- production is refused;
- schema mutation is not performed here; migration_runner.py --check is used.

The probe is designed for staging cutover rehearsals, not production promotion.
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
from urllib import error, request

ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "services" / "decision-service"

APPROVAL_ENV = "DECISION_SERVICE_STAGING_PROBE_APPROVED"
LIVE_ENV = "DECISION_SERVICE_STAGING_PROBE_ALLOW_LIVE"
ENV_NAME_ENV = "SAHOOL_ENV"


@dataclass
class ProbeStep:
    name: str
    ok: bool
    detail: str
    duration_ms: int = 0


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _json_request(
    method: str, url: str, payload: dict[str, Any] | None = None, timeout: float = 10.0
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        url, data=body, method=method, headers={"content-type": "application/json"}
    )
    with request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - staging operator-supplied URL
        raw = res.read().decode("utf-8")
        return res.status, json.loads(raw or "{}")


def _run_command(name: str, cmd: list[str], env: dict[str, str]) -> ProbeStep:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        tail = "\n".join((proc.stdout or "").splitlines()[-8:])
        return ProbeStep(
            name=name,
            ok=proc.returncode == 0,
            detail=tail or f"exit={proc.returncode}",
            duration_ms=elapsed,
        )
    except Exception as exc:  # pragma: no cover - defensive operator path
        elapsed = int((time.monotonic() - start) * 1000)
        return ProbeStep(name=name, ok=False, detail=str(exc), duration_ms=elapsed)


def _check_readiness(url: str) -> ProbeStep:
    start = time.monotonic()
    try:
        status, body = _json_request("GET", url.rstrip("/") + "/v1/cutover/readiness")
        elapsed = int((time.monotonic() - start) * 1000)
        missing = body.get("missing_gates") or []
        can_enable = bool(body.get("can_enable_sor"))
        can_demote = bool(body.get("can_demote_platform"))
        ok = status == 200 and can_enable and not can_demote
        detail = json.dumps(
            {
                "status": status,
                "can_enable_sor": can_enable,
                "can_demote_platform": can_demote,
                "missing_gates": missing,
            },
            sort_keys=True,
        )
        return ProbeStep("decision-service readiness endpoint", ok, detail, elapsed)
    except error.URLError as exc:
        return ProbeStep("decision-service readiness endpoint", False, f"url error: {exc}")
    except Exception as exc:  # pragma: no cover - defensive operator path
        return ProbeStep("decision-service readiness endpoint", False, str(exc))


def _sample_shadow_write(
    platform_url: str, tenant_id: str, field_id: str, idempotency_key: str
) -> ProbeStep:
    """Submit a tiny staging-only decision sample through the platform BFF.

    The exact platform endpoint can differ by deployment. Operators can expose a
    staging-compatible endpoint at this conventional path or skip sample writes.
    The probe is intentionally explicit rather than silently inventing writes.
    """
    start = time.monotonic()
    payload = {
        "field_id": field_id,
        "stage": "staging_probe",
        "recommendation_id": "probe_recommendation",
        "decision": "noop_probe",
        "confidence": 0.0,
        "evidence": {"source": "decision_sor_staging_probe"},
        "idempotency_key": idempotency_key,
    }
    try:
        endpoint = platform_url.rstrip("/") + f"/api/v1/fields/{field_id}/decisions"
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "content-type": "application/json",
                "x-tenant-id": tenant_id,
                "idempotency-key": idempotency_key,
            },
        )
        with request.urlopen(req, timeout=10.0) as res:  # noqa: S310 - staging operator-supplied URL
            body = json.loads(res.read().decode("utf-8") or "{}")
        elapsed = int((time.monotonic() - start) * 1000)
        ok = 200 <= res.status < 300 and body.get("persisted") in {True, False, None}
        return ProbeStep(
            "platform shadow sample write",
            ok,
            json.dumps({"status": res.status, "body_keys": sorted(body.keys())}),
            elapsed,
        )
    except Exception as exc:
        return ProbeStep("platform shadow sample write", False, str(exc))


def _refuse_unsafe_live(env: dict[str, str]) -> None:
    env_name = env.get(ENV_NAME_ENV, "").strip().lower()
    if env_name in {"prod", "production"}:
        raise SystemExit("Refusing to run the staging probe in production")
    if not _truthy(env.get(APPROVAL_ENV)):
        raise SystemExit(f"Live staging probe requires {APPROVAL_ENV}=true")
    if not _truthy(env.get(LIVE_ENV)):
        raise SystemExit(f"Live staging probe requires {LIVE_ENV}=true")


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    env = os.environ.copy()
    steps: list[ProbeStep] = []

    if not args.live:
        steps.append(
            ProbeStep(
                "dry-run safety",
                True,
                "live network/db checks skipped; pass --live with staging approvals",
            )
        )
        return {"mode": "dry-run", "ok": True, "steps": [asdict(step) for step in steps]}

    _refuse_unsafe_live(env)
    env.setdefault("SAHOOL_DECISION_WRITE_MODE", "shadow")

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

    if args.sample_write:
        steps.append(
            _sample_shadow_write(
                args.platform_url, args.tenant_id, args.field_id, args.idempotency_key
            )
        )
    else:
        steps.append(
            ProbeStep(
                "platform shadow sample write",
                True,
                "skipped; pass --sample-write for staging noop write",
            )
        )

    ok = all(step.ok for step in steps)
    return {"mode": "live-staging", "ok": ok, "steps": [asdict(step) for step in steps]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decision-service SoR staging probe harness")
    parser.add_argument(
        "--live",
        action="store_true",
        help="run live staging checks; requires explicit env approvals",
    )
    parser.add_argument(
        "--decision-service-url", default=os.getenv("DECISION_SERVICE_URL", "http://localhost:8097")
    )
    parser.add_argument(
        "--platform-url", default=os.getenv("SAHOOL_PLATFORM_URL", "http://localhost:8000")
    )
    parser.add_argument(
        "--sample-write",
        action="store_true",
        help="send a staging noop decision through the platform",
    )
    parser.add_argument("--tenant-id", default=os.getenv("STAGING_TENANT_ID", "staging-tenant"))
    parser.add_argument("--field-id", default=os.getenv("STAGING_FIELD_ID", "staging-field"))
    parser.add_argument(
        "--idempotency-key",
        default=os.getenv("STAGING_PROBE_IDEMPOTENCY_KEY", "decision-sor-staging-probe"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_probe(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
