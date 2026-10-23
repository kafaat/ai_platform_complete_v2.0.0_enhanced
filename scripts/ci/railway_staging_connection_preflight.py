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


def validate_status(payload: Any, source_sha: str) -> dict[str, Any]:
    """Validate native Railway CLI v5.63.1 ProjectProject JSON, not a wrapper.

    With explicit project/environment flags, the CLI filters
    environments.edges to the selected environment. Exactly one accessible
    staging edge must be present. A project-level ID alone is not enough.
    """
    if SHA_PATTERN.fullmatch(source_sha) is None:
        raise PreflightError("INVALID_SOURCE_SHA")
    if not isinstance(payload, dict):
        raise PreflightError("INVALID_STATUS_SHAPE")
    if "error" in payload or "errors" in payload:
        raise PreflightError("STATUS_HAS_ERROR")

    if payload.get("id") != PROJECT_ID:
        raise PreflightError("PROJECT_ID_MISMATCH")
    environments = payload.get("environments")
    if not isinstance(environments, dict):
        raise PreflightError("MISSING_ENVIRONMENTS")
    edges = environments.get("edges")
    if not isinstance(edges, list) or len(edges) != 1:
        raise PreflightError("ENVIRONMENT_SCOPE_MISMATCH")
    edge = edges[0]
    if not isinstance(edge, dict) or not isinstance(edge.get("node"), dict):
        raise PreflightError("INVALID_ENVIRONMENT_SHAPE")
    environment = edge["node"]
    if environment.get("id") != STAGING_ID:
        raise PreflightError("ENVIRONMENT_ID_MISMATCH")
    if environment.get("name") != "staging":
        raise PreflightError("ENVIRONMENT_NAME_MISMATCH")
    if environment.get("canAccess") is False:
        raise PreflightError("STAGING_ACCESS_DENIED")

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
        receipt["verifier_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
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
