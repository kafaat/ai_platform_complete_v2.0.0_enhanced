#!/usr/bin/env python3
"""Freshness, replay-prevention, revocation and promotion policy for PATH-3 attestations."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REVOCATIONS = ROOT / "runtime-verification/policy/attestation_revocations.json"
PROMOTIONS = ROOT / "runtime-verification/promotions"
DEFAULT_MAX_AGE_SECONDS = 86400


def parse_time(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def attestation_id(payload: dict[str, Any]) -> str:
    stable = {
        "run_id": payload.get("run_id"),
        "tested_sha": payload.get("tested_sha"),
        "environment_id": payload.get("environment_id"),
        "created_at": payload.get("created_at"),
        "signature": payload.get("signature"),
    }
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_revocations(path: Path = REVOCATIONS) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "1.0", "revocations": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("revocations"), list):
        raise ValueError("invalid revocation ledger")
    return data


def evaluate(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    revocations_path: Path = REVOCATIONS,
    target_environment: str | None = None,
) -> list[str]:
    errors: list[str] = []
    now = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        created = parse_time(str(payload.get("created_at", "")))
    except (TypeError, ValueError):
        return ["invalid_created_at"]
    age = (now - created).total_seconds()
    if age < -300:
        errors.append("attestation_from_future")
    if age > max_age_seconds:
        errors.append("attestation_expired")
    if target_environment and payload.get("environment_id") != target_environment:
        errors.append("environment_promotion_mismatch")
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or len(run_id) < 8:
        errors.append("invalid_run_id")
    aid = attestation_id(payload)
    try:
        ledger = load_revocations(revocations_path)
    except (OSError, ValueError, TypeError):
        errors.append("revocation_ledger_invalid")
        ledger = {"revocations": []}
    for row in ledger.get("revocations", []):
        if row.get("attestation_id") == aid or row.get("run_id") == run_id:
            errors.append("attestation_revoked")
            break
    return sorted(set(errors))


def promotion_record(payload: dict[str, Any], target_environment: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "attestation_id": attestation_id(payload),
        "run_id": payload["run_id"],
        "tested_sha": payload["tested_sha"],
        "source_environment": payload["environment_id"],
        "target_environment": target_environment,
        "promoted_at": datetime.now(UTC).isoformat(),
        "production_certified": False,
        "promotion_scope": "runtime_evidence_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--max-age-seconds", type=int, default=DEFAULT_MAX_AGE_SECONDS)
    parser.add_argument("--target-environment")
    parser.add_argument("--record-promotion", action="store_true")
    args = parser.parse_args()
    path = args.attestation if args.attestation.is_absolute() else ROOT / args.attestation
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        print(f"PATH-3 attestation policy BLOCKED: unreadable ({type(exc).__name__})")
        return 1
    errors = evaluate(
        payload, max_age_seconds=args.max_age_seconds, target_environment=args.target_environment
    )
    if errors:
        print("PATH-3 attestation policy BLOCKED: " + ", ".join(errors))
        return 1
    if args.record_promotion:
        if not args.target_environment:
            print("PATH-3 attestation policy BLOCKED: target environment required")
            return 1
        record = promotion_record(payload, args.target_environment)
        out = PROMOTIONS / f"{record['attestation_id']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            print("PATH-3 attestation policy BLOCKED: replayed_promotion")
            return 1
        out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"PATH-3 promotion recorded: {out.relative_to(ROOT)}")
    else:
        print(f"PATH-3 attestation policy PASS: run={payload.get('run_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
