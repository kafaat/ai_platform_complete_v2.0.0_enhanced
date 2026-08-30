#!/usr/bin/env python3
"""Validate and normalize runtime evidence into a tamper-evident service ledger."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "runtime-verification/generated/runtime_probe_plan.json"
EVIDENCE_DIR = ROOT / "runtime-verification/evidence"
OUT_DIR = ROOT / "runtime-verification/generated"
LEDGER = OUT_DIR / "runtime_evidence_ledger.json"
REPORT = OUT_DIR / "RUNTIME_EVIDENCE_LEDGER.md"
TRUST_REGISTRY = ROOT / "runtime-verification/trusted_environments.json"
SCHEMA_VERSION = "2.0"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ENVIRONMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_EVIDENCE_AGE = timedelta(hours=24)
MAX_FUTURE_SKEW = timedelta(minutes=5)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evidence_digest(evidence: dict[str, Any]) -> str:
    unsigned = dict(evidence)
    unsigned.pop("evidence_sha256", None)
    unsigned.pop("attestation", None)
    payload = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(payload.encode())


def signing_payload(evidence: dict[str, Any]) -> bytes:
    unsigned = dict(evidence)
    unsigned.pop("attestation", None)
    return json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def trust_policy(
    environment_id: object, attestation: object
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(environment_id, str) or not ENVIRONMENT_ID_RE.fullmatch(environment_id):
        return None, ["invalid_environment_id"]
    try:
        registry = json.loads(TRUST_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None, ["trusted_environment_registry_unavailable"]
    environment = next(
        (
            row
            for row in registry.get("environments", [])
            if isinstance(row, dict) and row.get("environment_id") == environment_id
        ),
        None,
    )
    if not environment:
        return None, ["untrusted_environment"]
    if not environment.get("eligible_for_runtime_verified"):
        errors.append("environment_not_runtime_eligible")
    if not isinstance(attestation, dict):
        return None, errors + ["missing_attestation"]
    issuer = attestation.get("issuer")
    if issuer not in environment.get("trusted_issuers", []):
        errors.append("issuer_not_trusted_for_environment")
    issuer_policy = next(
        (
            row
            for row in registry.get("issuers", [])
            if isinstance(row, dict) and row.get("issuer") == issuer
        ),
        None,
    )
    if not issuer_policy:
        errors.append("unknown_attestation_issuer")
        return None, errors
    if (
        issuer_policy.get("algorithm") != "hmac-sha256"
        or attestation.get("algorithm") != "hmac-sha256"
    ):
        errors.append("unsupported_attestation_algorithm")
    return issuer_policy, errors


def checkout_sha() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = (proc.stdout or "").strip().lower()
    return value if proc.returncode == 0 and SHA_RE.fullmatch(value) else None


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def validate_evidence(
    path: Path,
    item: dict[str, Any],
    plan_hash: str,
    *,
    expected_subject_sha: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        raw = path.read_bytes()
        evidence = json.loads(raw)
    except (OSError, ValueError, TypeError) as exc:
        return {"file": path.name, "valid": False, "errors": [f"unreadable:{type(exc).__name__}"]}
    if not isinstance(evidence, dict):
        return {"file": path.name, "valid": False, "errors": ["evidence_not_object"]}

    required = {
        "schema_version",
        "service",
        "tested_sha",
        "environment_id",
        "base_url_sha256",
        "started_at",
        "completed_at",
        "probe_results",
        "plan_sha256",
        "evidence_sha256",
        "runtime_identity",
        "attestation",
    }
    missing = sorted(required.difference(evidence))
    if missing:
        errors.append("missing:" + ",".join(missing))
    if evidence.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version_mismatch")
    if evidence.get("service") != item["service"]:
        errors.append("service_mismatch")
    if evidence.get("plan_sha256") != plan_hash:
        errors.append("plan_hash_mismatch")
    tested_sha = evidence.get("tested_sha")
    if not isinstance(tested_sha, str) or not SHA_RE.fullmatch(tested_sha):
        errors.append("invalid_tested_sha")
    if expected_subject_sha is None:
        errors.append("subject_sha_unavailable")
    elif tested_sha != expected_subject_sha:
        errors.append("tested_sha_mismatch")
    environment_id = evidence.get("environment_id")
    issuer_policy, trust_errors = trust_policy(environment_id, evidence.get("attestation"))
    errors.extend(trust_errors)
    base_url_sha256 = evidence.get("base_url_sha256")
    if not isinstance(base_url_sha256, str) or not DIGEST_RE.fullmatch(base_url_sha256):
        errors.append("invalid_base_url_sha256")
    sealed_digest = evidence.get("evidence_sha256")
    if (
        not isinstance(sealed_digest, str)
        or not DIGEST_RE.fullmatch(sealed_digest)
        or sealed_digest != evidence_digest(evidence)
    ):
        errors.append("evidence_digest_mismatch")
    attestation = evidence.get("attestation")
    if isinstance(attestation, dict) and issuer_policy is not None:
        signature = attestation.get("signature")
        key_env = issuer_policy.get("verification_key_env")
        key = os.getenv(key_env, "") if isinstance(key_env, str) else ""
        if not key:
            errors.append("attestation_verification_key_unavailable")
        elif not isinstance(signature, str) or not DIGEST_RE.fullmatch(signature):
            errors.append("invalid_attestation_signature")
        else:
            expected_signature = hmac.new(
                key.encode(), signing_payload(evidence), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected_signature):
                errors.append("invalid_attestation_signature")

    identity = evidence.get("runtime_identity")
    if not isinstance(identity, dict):
        errors.append("missing_runtime_identity")
        identity = {}
    if identity.get("service") != item["service"]:
        errors.append("runtime_identity_service_mismatch")
    if identity.get("git_sha") != tested_sha:
        errors.append("runtime_identity_sha_mismatch")
    if identity.get("metadata_source") != "immutable-image-file":
        errors.append("runtime_identity_not_immutable")
    if not isinstance(identity.get("build_id"), str) or not identity.get("build_id"):
        errors.append("runtime_identity_build_id_missing")
    if not isinstance(identity.get("image_digest"), str) or not IMAGE_DIGEST_RE.fullmatch(
        identity.get("image_digest", "")
    ):
        errors.append("runtime_identity_image_digest_invalid")

    started = parse_time(evidence.get("started_at"))
    completed = parse_time(evidence.get("completed_at"))
    if started is None or completed is None:
        errors.append("invalid_timestamps")
    elif completed < started:
        errors.append("completed_before_started")
    else:
        observed_at = now or datetime.now(UTC)
        if completed > observed_at + MAX_FUTURE_SKEW:
            errors.append("evidence_from_future")
        elif observed_at - completed > MAX_EVIDENCE_AGE:
            errors.append("stale_evidence")

    expected = {(p["kind"], p["method"], p["path"]) for p in item["probes"]}
    results = evidence.get("probe_results")
    if not isinstance(results, list) or not results:
        errors.append("missing_probe_results")
        results = []
    observed: set[tuple[str, str, str]] = set()
    observed_count = 0
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            errors.append(f"probe_{index}:not_object")
            continue
        key = (result.get("kind"), result.get("method"), result.get("path"))
        if all(isinstance(v, str) for v in key):
            observed.add(key)  # type: ignore[arg-type]
            observed_count += 1
        if result.get("status") != "passed":
            errors.append(f"probe_{index}:not_passed")
        if not isinstance(result.get("http_status"), int) or not 200 <= result["http_status"] < 300:
            errors.append(f"probe_{index}:invalid_http_status")
        if not isinstance(result.get("latency_ms"), (int, float)) or result["latency_ms"] < 0:
            errors.append(f"probe_{index}:invalid_latency")
        digest = result.get("response_sha256")
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
            errors.append(f"probe_{index}:invalid_response_sha256")
    if observed_count != len(observed):
        errors.append("duplicate_probe_results")
    if observed != expected:
        errors.append("probe_set_mismatch")

    return {
        "file": path.name,
        "file_sha256": sha256_bytes(raw),
        "service": evidence.get("service"),
        "tested_sha": evidence.get("tested_sha"),
        "environment_id": evidence.get("environment_id"),
        "attestation_issuer": attestation.get("issuer") if isinstance(attestation, dict) else None,
        "runtime_image_digest": identity.get("image_digest"),
        "started_at": evidence.get("started_at"),
        "completed_at": evidence.get("completed_at"),
        "probe_count": len(results),
        "valid": not errors,
        "errors": sorted(set(errors)),
    }


def build() -> tuple[dict[str, Any], str]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    service_by_name = {item["service"]: item for item in plan["services"]}
    files_by_service: dict[str, list[Path]] = {}
    unknown_files: list[str] = []
    for path in sorted(EVIDENCE_DIR.glob("*.json")) if EVIDENCE_DIR.exists() else []:
        try:
            service = json.loads(path.read_text(encoding="utf-8")).get("service")
        except (OSError, ValueError, TypeError):
            unknown_files.append(path.name)
            continue
        if service not in service_by_name:
            unknown_files.append(path.name)
            continue
        files_by_service.setdefault(service, []).append(path)

    expected_subject_sha = checkout_sha()
    services: list[dict[str, Any]] = []
    for name, item in sorted(service_by_name.items()):
        validations = [
            validate_evidence(
                path,
                item,
                plan["plan_sha256"],
                expected_subject_sha=expected_subject_sha,
            )
            for path in files_by_service.get(name, [])
        ]
        valid = [entry for entry in validations if entry["valid"]]
        latest = (
            sorted(valid, key=lambda e: (e.get("completed_at") or "", e["file"]))[-1]
            if valid
            else None
        )
        services.append(
            {
                "service": name,
                "probeable": bool(item["probes"]),
                "planned_probe_count": len(item["probes"]),
                "evidence_files": validations,
                "valid_evidence_count": len(valid),
                "runtime_verified": latest is not None,
                "latest_valid_evidence": latest,
                "production_certified": False,
            }
        )

    ledger_core = {
        "schema_version": SCHEMA_VERSION,
        "plan_sha256": plan["plan_sha256"],
        "fail_closed": True,
        "unknown_or_unbound_evidence_files": sorted(unknown_files),
        "services": services,
    }
    ledger = dict(ledger_core)
    ledger["ledger_sha256"] = sha256_bytes(canonical(ledger_core).encode())

    valid_services = sum(s["runtime_verified"] for s in services)
    invalid_files = sum(sum(not e["valid"] for e in s["evidence_files"]) for s in services) + len(
        unknown_files
    )
    lines = [
        "# SAHOOL Runtime Evidence Ledger",
        "",
        "> Fail-closed normalized ledger. Static repository evidence cannot set runtime_verified.",
        "",
        "## Summary",
        "",
        f"- Services: **{len(services)}**",
        f"- Runtime verified services: **{valid_services}**",
        f"- Invalid, stale, or unbound evidence files: **{invalid_files}**",
        "- Production certified services: **0**",
        "",
        "| Service | Planned probes | Valid evidence | Runtime verified |",
        "|---|---:|---:|---|",
    ]
    for service in services:
        lines.append(
            f"| {service['service']} | {service['planned_probe_count']} | "
            f"{service['valid_evidence_count']} | {str(service['runtime_verified']).lower()} |"
        )
    return ledger, "\n".join(lines) + "\n"


def generate() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ledger, report = build()
    LEDGER.write_text(canonical(ledger), encoding="utf-8")
    REPORT.write_text(report, encoding="utf-8")


def check() -> int:
    ledger, report = build()
    drift = []
    if not LEDGER.exists() or LEDGER.read_text(encoding="utf-8") != canonical(ledger):
        drift.append(str(LEDGER.relative_to(ROOT)))
    if not REPORT.exists() or REPORT.read_text(encoding="utf-8") != report:
        drift.append(str(REPORT.relative_to(ROOT)))
    if drift:
        print("runtime evidence ledger drift: " + ", ".join(drift))
        return 1
    invalid = ledger["unknown_or_unbound_evidence_files"][:]
    invalid.extend(
        entry["file"]
        for service in ledger["services"]
        for entry in service["evidence_files"]
        if not entry["valid"]
    )
    if invalid:
        print("invalid/stale/unbound runtime evidence: " + ", ".join(sorted(invalid)))
        return 1
    verified = sum(s["runtime_verified"] for s in ledger["services"])
    print(f"runtime evidence ingestion PASS: {verified} runtime-verified services")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.generate:
        generate()
        return 0
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
