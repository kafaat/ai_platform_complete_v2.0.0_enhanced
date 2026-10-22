#!/usr/bin/env python3
"""Fail-closed Railway staging status verification. Never emit raw CLI data."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ID = "33c50993-1110-43eb-8e92-04c15edae51e"
STAGING_ID = "70cc51f8-b11f-4506-87b2-4b6615e472be"
PRODUCTION_ID = "79de27a7-dae8-4cae-b37e-e9f7fae66c1d"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MAX_STATUS_BYTES = 2_000_000


class PreflightError(ValueError):
    """Only constant, secret-free error codes."""


def _identity(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("id")
    return value if isinstance(value, str) and value else None


def _read_id(payload: dict[str, Any], nested: str, flat: str) -> str:
    values = [
        v for v in (_identity(payload.get(nested)), _identity(payload.get(flat)))
        if v is not None
    ]
    if not values:
        raise PreflightError(f"MISSING_{flat.upper()}")
    if len(set(values)) != 1:
        raise PreflightError(f"CONFLICTING_{flat.upper()}")
    return values[0]


def validate_status(payload: Any, source_sha: str) -> dict[str, Any]:
    if SHA_PATTERN.fullmatch(source_sha) is None:
        raise PreflightError("INVALID_SOURCE_SHA")
    if not isinstance(payload, dict):
        raise PreflightError("INVALID_STATUS_SHAPE")
    if "error" in payload or "errors" in payload:
        raise PreflightError("STATUS_HAS_ERROR")

    project = _read_id(payload, "project", "projectId")
    environment = _read_id(payload, "environment", "environmentId")
    if project != PROJECT_ID:
        raise PreflightError("PROJECT_ID_MISMATCH")
    if environment == PRODUCTION_ID or environment != STAGING_ID:
        raise PreflightError("ENVIRONMENT_ID_MISMATCH")
    details = payload.get("environment")
    if isinstance(details, dict) and details.get("name") not in (None, "staging"):
        raise PreflightError("ENVIRONMENT_NAME_MISMATCH")

    return {
        "verdict": "CONNECTION_ONLY_PASS",
        "project_id": PROJECT_ID,
        "environment_id": STAGING_ID,
        "source_sha": source_sha,
        "scope": "staging",
        "read_only": True,
        "deployment_performed": False,
        "migration_performed": False,
        "database_access_verified": False,
        "runtime_verified": False,
        "production_certified": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--status-json", type=Path, required=True)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    args = ap.parse_args()
    try:
        if args.status_json.stat().st_size > MAX_STATUS_BYTES:
            raise PreflightError("STATUS_TOO_LARGE")
        try:
            payload = json.loads(args.status_json.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise PreflightError("MALFORMED_STATUS_JSON") from None
        receipt = validate_status(payload, args.source_sha)
        receipt["observed_at_utc"] = datetime.now(UTC).isoformat()
        receipt["verifier_sha256"] = hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest()
        args.evidence.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (PreflightError, OSError) as exc:
        code = str(exc) if isinstance(exc, PreflightError) else "STATUS_FILE_UNREADABLE"
        print(f"::error::{code}", file=sys.stderr)
        return 1
    print("CONNECTION_ONLY_PASS: read-only staging identity verified; no deploy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
