#!/usr/bin/env python3
"""Create and verify a signed PATH-3 runtime-run attestation.

The signature is HMAC-SHA256 over a canonical JSON payload. The signing key is
supplied only through PATH3_ATTESTATION_KEY and is never written to disk.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "runtime-verification/evidence"
ATTESTATION_DIR = ROOT / "runtime-verification/attestations"
PLAN = ROOT / "runtime-verification/generated/runtime_probe_plan.json"
TARGETS = ROOT / "runtime-verification/generated/compose_runtime_targets.json"
SCHEMA_VERSION = "1.0"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signing_key() -> bytes:
    raw = os.getenv("PATH3_ATTESTATION_KEY", "")
    if len(raw) < 32:
        raise ValueError("PATH3_ATTESTATION_KEY must contain at least 32 characters")
    return raw.encode("utf-8")


def sign(core: dict[str, Any]) -> str:
    return hmac.new(signing_key(), canonical(core), hashlib.sha256).hexdigest()


def verify_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version_mismatch")
    signature = payload.get("signature")
    core = {k: v for k, v in payload.items() if k != "signature"}
    try:
        expected = sign(core)
    except ValueError as exc:
        return [str(exc)]
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        errors.append("invalid_signature")
    if payload.get("signature_algorithm") != "HMAC-SHA256":
        errors.append("signature_algorithm_mismatch")
    if payload.get("plan_sha256") != json.loads(PLAN.read_text(encoding="utf-8")).get(
        "plan_sha256"
    ):
        errors.append("plan_hash_mismatch")
    if payload.get("targets_file_sha256") != sha256_file(TARGETS):
        errors.append("targets_hash_mismatch")

    files = payload.get("evidence_files")
    if not isinstance(files, list) or not files:
        errors.append("missing_evidence_files")
        files = []
    for index, row in enumerate(files):
        if not isinstance(row, dict):
            errors.append(f"evidence_{index}:not_object")
            continue
        path = EVIDENCE_DIR / str(row.get("file", ""))
        if not path.is_file():
            errors.append(f"evidence_{index}:missing")
            continue
        if sha256_file(path) != row.get("sha256"):
            errors.append(f"evidence_{index}:hash_mismatch")
            continue
        try:
            evidence = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            errors.append(f"evidence_{index}:unreadable")
            continue
        for field in (
            "run_id",
            "tested_sha",
            "environment_id",
            "compose_config_sha256",
            "targets_file_sha256",
        ):
            if evidence.get(field) != payload.get(field):
                errors.append(f"evidence_{index}:{field}_mismatch")
    return sorted(set(errors))


def build(args: argparse.Namespace) -> dict[str, Any]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    evidence_rows: list[dict[str, Any]] = []
    for path in sorted(EVIDENCE_DIR.glob("*.json")):
        try:
            evidence = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if evidence.get("run_id") != args.run_id:
            continue
        evidence_rows.append(
            {
                "file": path.name,
                "service": evidence.get("service"),
                "sha256": sha256_file(path),
                "probe_count": len(evidence.get("probe_results") or []),
            }
        )
    core = {
        "schema_version": SCHEMA_VERSION,
        "signature_algorithm": "HMAC-SHA256",
        "run_id": args.run_id,
        "tested_sha": args.tested_sha,
        "environment_id": args.environment_id,
        "created_at": datetime.now(UTC).isoformat(),
        "plan_sha256": plan["plan_sha256"],
        "targets_file_sha256": sha256_file(TARGETS),
        "compose_config_sha256": args.compose_config_sha256,
        "compose_images_output_sha256": args.compose_images_output_sha256,
        "selected_services": sorted(set(args.service or [])),
        "evidence_files": evidence_rows,
        "fail_closed": True,
        "production_certified": False,
    }
    return {**core, "signature": sign(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--run-id", required=True)
    create.add_argument("--tested-sha", required=True)
    create.add_argument("--environment-id", required=True)
    create.add_argument("--compose-config-sha256", required=True)
    create.add_argument("--compose-images-output-sha256", required=True)
    create.add_argument("--service", action="append")
    create.add_argument("--output", type=Path)
    check = sub.add_parser("check")
    check.add_argument("--attestation", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "create":
        payload = build(args)
        output = args.output or (ATTESTATION_DIR / f"{args.run_id}.json")
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            f"PATH-3 attestation created: {output.relative_to(ROOT)} ({len(payload['evidence_files'])} evidence files)"
        )
        return 0

    path = args.attestation if args.attestation.is_absolute() else ROOT / args.attestation
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        print(f"PATH-3 attestation unreadable: {type(exc).__name__}")
        return 1
    errors = verify_payload(payload)
    if errors:
        print("PATH-3 attestation INVALID: " + ", ".join(errors))
        return 1
    print(
        f"PATH-3 attestation PASS: run={payload['run_id']} evidence={len(payload['evidence_files'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
