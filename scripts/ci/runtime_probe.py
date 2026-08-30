#!/usr/bin/env python3
"""Execute one service's runtime probe plan and write tamper-evident evidence."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "runtime-verification" / "generated" / "runtime_probe_plan.json"
EVIDENCE_DIR = ROOT / "runtime-verification" / "evidence"
TRUST_REGISTRY = ROOT / "runtime-verification" / "trusted_environments.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ENVIRONMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
EVIDENCE_SCHEMA_VERSION = "2.0"


def now() -> str:
    return datetime.now(UTC).isoformat()


def checkout_sha() -> str:
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
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("unable to resolve checkout SHA") from exc
    value = (proc.stdout or "").strip().lower()
    if proc.returncode or not SHA_RE.fullmatch(value):
        raise RuntimeError("checkout HEAD is not a full lowercase Git SHA")
    return value


def git_sha() -> str:
    actual = checkout_sha()
    explicit = os.getenv("TESTED_SHA", "").strip()
    if explicit and not SHA_RE.fullmatch(explicit):
        raise ValueError("TESTED_SHA must be 40 lowercase hex")
    if explicit and explicit != actual:
        raise ValueError("TESTED_SHA does not match the real checkout HEAD")
    return actual


def evidence_digest(evidence: dict[str, Any]) -> str:
    unsigned = dict(evidence)
    unsigned.pop("evidence_sha256", None)
    unsigned.pop("attestation", None)
    payload = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def signing_payload(evidence: dict[str, Any]) -> bytes:
    unsigned = dict(evidence)
    unsigned.pop("attestation", None)
    return json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def trusted_issuer(environment_id: str, issuer: str) -> dict[str, Any]:
    registry = load_json(TRUST_REGISTRY)
    environment = next(
        (
            row
            for row in registry.get("environments", [])
            if isinstance(row, dict) and row.get("environment_id") == environment_id
        ),
        None,
    )
    if not environment or not environment.get("eligible_for_runtime_verified"):
        raise ValueError(
            f"environment {environment_id!r} is not eligible for runtime_verified evidence"
        )
    if issuer not in environment.get("trusted_issuers", []):
        raise ValueError(f"issuer {issuer!r} is not trusted for {environment_id!r}")
    issuer_row = next(
        (
            row
            for row in registry.get("issuers", [])
            if isinstance(row, dict) and row.get("issuer") == issuer
        ),
        None,
    )
    if not issuer_row or issuer_row.get("algorithm") != "hmac-sha256":
        raise ValueError("runtime_probe supports only a registered hmac-sha256 issuer")
    return issuer_row


def deployment_identity(path: Path, service: str, tested_sha: str) -> dict[str, str]:
    manifest = load_json(path)
    row = (manifest.get("services") or {}).get(service)
    if not isinstance(row, dict):
        raise ValueError(f"deployment manifest missing service {service!r}")
    required = ("service", "git_sha", "build_id", "image_digest")
    if any(not isinstance(row.get(key), str) or not row[key] for key in required):
        raise ValueError("deployment manifest identity is incomplete")
    if row["service"] != service or row["git_sha"] != tested_sha:
        raise ValueError("deployment manifest does not match the measured subject")
    if not IMAGE_DIGEST_RE.fullmatch(row["image_digest"]):
        raise ValueError("deployment image_digest must be sha256:<64 lowercase hex>")
    return {key: row[key] for key in required}


def runtime_identity(
    base_url: str,
    identity_path: str,
    timeout: float,
    deployed: dict[str, str],
) -> dict[str, str]:
    url = base_url.rstrip("/") + identity_path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                raise ValueError(f"runtime identity returned HTTP {response.status}")
            value = json.loads(response.read())
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise ValueError(f"unable to verify live runtime identity at {identity_path}") from exc
    if not isinstance(value, dict):
        raise ValueError("runtime identity response is not an object")
    for key in ("service", "git_sha", "build_id", "metadata_source"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise ValueError(f"runtime identity missing {key}")
    if value["metadata_source"] != "immutable-image-file":
        raise ValueError("runtime identity is not backed by immutable image metadata")
    if any(value[key] != deployed[key] for key in ("service", "git_sha", "build_id")):
        raise ValueError("live runtime identity differs from the deployment manifest")
    return {
        "service": value["service"],
        "git_sha": value["git_sha"],
        "build_id": value["build_id"],
        "metadata_source": value["metadata_source"],
        "image_digest": deployed["image_digest"],
        "image_digest_source": "deployment-manifest",
    }


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def request(url: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read()
            code = response.status
        status = "passed" if 200 <= code < 300 else "failed"
        error = None
    except urllib.error.HTTPError as exc:
        body = exc.read()
        code = exc.code
        status = "failed"
        error = f"HTTP {exc.code}"
    except Exception as exc:
        body = b""
        code = None
        status = "failed"
        error = type(exc).__name__
    return {
        "status": status,
        "http_status": code,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "response_bytes": len(body),
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--deployment-manifest", required=True)
    parser.add_argument("--issuer", default="sahool-staging-hmac")
    parser.add_argument("--plan", default=str(PLAN))
    parser.add_argument("--evidence-dir", default=str(EVIDENCE_DIR))
    parser.add_argument("--output-name")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    if not ENVIRONMENT_ID_RE.fullmatch(args.environment_id):
        raise SystemExit("invalid environment identifier")

    plan_path = Path(args.plan)
    if not plan_path.is_absolute():
        plan_path = ROOT / plan_path
    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_absolute():
        evidence_dir = ROOT / evidence_dir
    deployment_manifest = Path(args.deployment_manifest)
    if not deployment_manifest.is_absolute():
        deployment_manifest = ROOT / deployment_manifest
    plan = load_json(plan_path)
    item = next((s for s in plan["services"] if s["service"] == args.service), None)
    if not item:
        raise SystemExit(f"unknown service: {args.service}")
    base_url = args.base_url or os.getenv(item["base_url_env"])
    if not base_url:
        raise SystemExit(f"missing --base-url or {item['base_url_env']}")
    sha = git_sha()
    try:
        issuer_row = trusted_issuer(args.environment_id, args.issuer)
        deployed = deployment_identity(deployment_manifest, args.service, sha)
        live_identity = runtime_identity(
            base_url,
            item.get("identity_path", "/runtime-identity"),
            args.timeout,
            deployed,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    key_env = issuer_row.get("verification_key_env")
    key = os.getenv(key_env, "") if isinstance(key_env, str) else ""
    if not key:
        raise SystemExit(
            f"{key_env or 'HMAC verification key'} is required; unsigned evidence is forbidden"
        )

    started_at = now()
    results = []
    for probe in item["probes"]:
        result = request(base_url.rstrip("/") + probe["path"], args.timeout)
        results.append({**probe, **result})
    evidence = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "service": args.service,
        "tested_sha": sha,
        "environment_id": args.environment_id,
        "base_url_sha256": hashlib.sha256(base_url.encode()).hexdigest(),
        "started_at": started_at,
        "completed_at": now(),
        "plan_sha256": plan["plan_sha256"],
        "runtime_identity": live_identity,
        "probe_results": results,
    }
    evidence["evidence_sha256"] = evidence_digest(evidence)
    evidence["attestation"] = {
        "issuer": args.issuer,
        "algorithm": "hmac-sha256",
        "signature": hmac.new(key.encode(), signing_payload(evidence), hashlib.sha256).hexdigest(),
    }
    output_name = args.output_name or f"{args.service}.json"
    if Path(output_name).name != output_name or not output_name.endswith(".json"):
        raise SystemExit("--output-name must be a plain .json filename")
    output = evidence_dir / output_name
    atomic_write(output, json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    passed = bool(results) and all(r["status"] == "passed" for r in results)
    print(f"wrote {output.relative_to(ROOT)}: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
