#!/usr/bin/env python3
"""Run repeatable pre-production evidence without pretending it is live proof.

The lab has two useful levels:
* offline: source and governance guards only;
* ephemeral: the same guards plus real, short-lived PostgreSQL 16/PostGIS,
  Redis, NATS, MinIO and WireMock dependencies.

It is deliberately unable to emit ``production_certified``. Real ingress,
provider delivery, physical devices and target-deployment rollout remain live
gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "config" / "evidence_lab_matrix.json"
COMPOSE_PATH = ROOT / "docker-compose.evidence-lab.yml"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "evidence_lab" / "wiremock" / "mappings"
PROJECT = "sahool-evidence-lab"
ALLOWED_ENVIRONMENTS = {"", "test", "local", "development", "evidence-lab"}
FORBIDDEN_ENVIRONMENTS = {"production", "prod", "staging", "stage"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def assert_non_live_environment() -> None:
    value = os.getenv("SAHOOL_ENV", "").strip().lower()
    if value in FORBIDDEN_ENVIRONMENTS or value not in ALLOWED_ENVIRONMENTS:
        raise SystemExit(
            "Evidence Lab refuses this SAHOOL_ENV. Use it only in local/test/evidence-lab; "
            "target-environment certification must use the production evidence workflow."
        )


def validate_contract() -> list[str]:
    errors: list[str] = []
    try:
        matrix = load_json(MATRIX_PATH)
    except Exception as exc:  # noqa: BLE001
        return [f"invalid matrix: {exc}"]

    policy = matrix.get("claim_policy") or {}
    if policy.get("always_production_certified") is not False:
        errors.append("claim_policy.always_production_certified must be false")
    forbidden = set(policy.get("forbidden_claims") or [])
    required_forbidden = {"production_certified", "live_certified", "production_ready"}
    if not required_forbidden.issubset(forbidden):
        errors.append("claim policy must forbid all live/production certification claims")
    capabilities = matrix.get("capabilities") or []
    if not capabilities:
        errors.append("matrix must contain capabilities")
    for row in capabilities:
        if not row.get("id"):
            errors.append("every capability must have an id")
        if not row.get("remaining_live_gate"):
            errors.append(f"{row.get('id', '<unknown>')} must declare remaining_live_gate")

    compose = COMPOSE_PATH.read_text(encoding="utf-8") if COMPOSE_PATH.exists() else ""
    required_tokens = [
        "postgis/postgis:16-3.4",
        "redis:7-alpine",
        "nats:2.10-alpine",
        "wiremock/wiremock:3.13.2",
        "127.0.0.1:",
        "no-new-privileges:true",
        "internal: true",
        "tmpfs:",
    ]
    for token in required_tokens:
        if token not in compose:
            errors.append(f"compose missing required token {token!r}")
    for token in ("docker-compose.v9.yml", "restart: always", "0.0.0.0:"):
        if token in compose:
            errors.append(f"evidence compose contains forbidden token {token!r}")

    fixture_paths = sorted(FIXTURE_ROOT.glob("*.json"))
    if len(fixture_paths) < 3:
        errors.append("at least three deterministic provider mappings are required")
    for path in fixture_paths:
        try:
            mapping = load_json(path)
            request = mapping.get("request") or {}
            response = mapping.get("response") or {}
            if request.get("method") not in {"GET", "POST"}:
                errors.append(f"{path.name}: unsupported request method")
            if not request.get("urlPath"):
                errors.append(f"{path.name}: urlPath missing")
            status = response.get("status")
            if (
                not isinstance(status, int)
                or not 100 <= status <= 599
                or "jsonBody" not in response
            ):
                errors.append(f"{path.name}: deterministic HTTP status and jsonBody required")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: invalid mapping: {exc}")
    return errors


def source_identity() -> dict[str, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        value = result.stdout.strip()
        if len(value) == 40:
            return {"kind": "git_commit", "value": value}
    except (OSError, subprocess.CalledProcessError):
        pass
    checksums = ROOT / "release" / "FILE_CHECKSUMS.sha256"
    if checksums.exists():
        return {"kind": "release_checksums_sha256", "value": sha256_bytes(checksums.read_bytes())}
    return {"kind": "source_tree_unidentified", "value": "unavailable"}


def redact(text: str) -> str:
    replacements = {
        "evidence-only-password": "[LAB_SECRET]",
        "evidence-only": "[LAB_SECRET]",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text[-12000:]


def run_command(name: str, command: list[str], *, timeout: int = 600) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "SAHOOL_ENV": "evidence-lab"},
        )
        combined = redact((proc.stdout or "") + (proc.stderr or ""))
        return {
            "name": name,
            "status": "passed" if proc.returncode == 0 else "failed",
            "return_code": proc.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "command": command,
            "output_tail": combined,
            "output_sha256": sha256_bytes(combined.encode("utf-8")),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "name": name,
            "status": "failed",
            "return_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "command": command,
            "output_tail": redact(str(exc)),
            "output_sha256": sha256_bytes(str(exc).encode("utf-8")),
        }


def http_probe(
    name: str,
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    expected_status: int = 200,
) -> dict[str, Any]:
    started = time.monotonic()
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - loopback only
            payload = response.read()
            ok = response.status == expected_status
            return {
                "name": name,
                "status": "passed" if ok else "failed",
                "http_status": response.status,
                "duration_seconds": round(time.monotonic() - started, 3),
                "response_sha256": sha256_bytes(payload),
            }
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        ok = exc.code == expected_status
        return {
            "name": name,
            "status": "passed" if ok else "failed",
            "http_status": exc.code,
            "duration_seconds": round(time.monotonic() - started, 3),
            "response_sha256": sha256_bytes(payload),
            "error": None if ok else redact(str(exc)),
        }
    except (urllib.error.URLError, TimeoutError) as exc:
        return {
            "name": name,
            "status": "failed",
            "http_status": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": redact(str(exc)),
        }


def offline_checks(output_dir: Path) -> list[dict[str, Any]]:
    py = sys.executable
    return [
        run_command("production_honesty", [py, "scripts/ci/production_honesty_guard.py"]),
        run_command("consumer_contracts", [py, "scripts/ci/consumer_contract_gate.py"]),
        run_command(
            "production_evidence_contract",
            [py, "scripts/ci/production_evidence_pack_guard.py", "--check"],
        ),
        run_command(
            "production_checklist_contract",
            [py, "scripts/ci/production_certification_checklist_guard.py", "--check"],
        ),
        run_command(
            "decision_runtime_structure",
            [py, "scripts/ci/wx12_runtime_certification_gate.py"],
        ),
        run_command(
            "service_feature_ui_contracts",
            [
                py,
                "scripts/ci/service_feature_ui_contract_gate.py",
                "--report",
                str(output_dir / "service_feature_ui.generated.md"),
                "--json-report",
                str(output_dir / "service_feature_ui.generated.json"),
            ],
        ),
    ]


def compose_base() -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_PATH),
        "-p",
        PROJECT,
    ]


def ephemeral_checks(*, keep: bool) -> list[dict[str, Any]]:
    if shutil.which("docker") is None:
        return [
            {
                "name": "docker_available",
                "status": "failed",
                "return_code": None,
                "duration_seconds": 0,
                "command": ["docker", "compose"],
                "output_tail": "docker executable not found",
                "output_sha256": sha256_bytes(b"docker executable not found"),
            }
        ]
    results: list[dict[str, Any]] = []
    up = run_command("compose_up", compose_base() + ["up", "-d", "--wait"], timeout=900)
    results.append(up)
    try:
        if up["status"] != "passed":
            results.append(run_command("compose_state", compose_base() + ["ps"], timeout=60))
            return results
        results.extend(
            [
                run_command(
                    "migration_apply_postgres16",
                    compose_base() + ["--profile", "migration", "run", "--rm", "evidence-migrate"],
                    timeout=900,
                ),
                run_command(
                    "migration_reapply_postgres16",
                    compose_base() + ["--profile", "migration", "run", "--rm", "evidence-migrate"],
                    timeout=900,
                ),
                run_command(
                    "postgres_16_postgis_rls",
                    compose_base()
                    + [
                        "exec",
                        "-T",
                        "evidence-postgres",
                        "psql",
                        "-U",
                        "evidence_lab",
                        "-d",
                        "evidence_lab",
                        "-Atc",
                        "select current_setting('server_version_num'), postgis_version(), "
                        "(select not rolsuper and not rolbypassrls from pg_roles "
                        "where rolname='sahool_app'), "
                        "(select count(*) from pg_class where relrowsecurity);",
                    ],
                    timeout=60,
                ),
                run_command(
                    "redis_authenticated",
                    compose_base()
                    + [
                        "exec",
                        "-T",
                        "evidence-redis",
                        "redis-cli",
                        "-a",
                        "evidence-only",
                        "--no-auth-warning",
                        "ping",
                    ],
                    timeout=60,
                ),
                http_probe("nats_jetstream", "http://127.0.0.1:58222/jsz"),
                http_probe("minio_health", "http://127.0.0.1:59000/minio/health/live"),
                http_probe("wiremock_admin", "http://127.0.0.1:58080/__admin/mappings"),
                http_probe(
                    "virtualized_open_meteo",
                    "http://127.0.0.1:58080/open-meteo/v1/forecast?latitude=15.35&longitude=44.2",
                ),
                http_probe(
                    "virtualized_stac",
                    "http://127.0.0.1:58080/earth-search/v1/search",
                    method="POST",
                    body=b'{"collections":["sentinel-2-l2a"],"limit":1}',
                ),
                http_probe(
                    "virtualized_provider_failure",
                    "http://127.0.0.1:58080/open-meteo/v1/forecast",
                    headers={"X-Evidence-Fault": "upstream-timeout"},
                    expected_status=503,
                ),
            ]
        )
    finally:
        if not keep:
            results.append(
                run_command("compose_down", compose_base() + ["down", "--volumes"], timeout=300)
            )
    return results


def markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# SAHOOL Evidence Lab Report",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Mode: `{payload['mode']}`",
        f"- State: `{payload['state']}`",
        f"- Maximum claim: `{payload['maximum_claim']}`",
        "- Production certified: `false`",
        "",
        "## Results",
        "",
        "| Check | Status | Duration (s) |",
        "|---|---:|---:|",
    ]
    for row in payload["results"]:
        lines.append(f"| `{row['name']}` | `{row['status']}` | {row.get('duration_seconds', 0)} |")
    lines.extend(
        [
            "",
            "## Remaining live gates",
            "",
        ]
    )
    for gate in payload["remaining_live_gates"]:
        lines.append(f"- {gate}")
    lines.extend(
        [
            "",
            "This is pre-production evidence. It cannot certify public ingress, real provider "
            "delivery, physical equipment safety, target-environment monitoring, backup schedules "
            "or production rollout.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "ephemeral"], default="offline")
    parser.add_argument(
        "--provision", action="store_true", help="start the ephemeral Compose stack"
    )
    parser.add_argument(
        "--keep", action="store_true", help="keep the ephemeral stack for inspection"
    )
    parser.add_argument(
        "--validate", action="store_true", help="validate the lab contract and exit"
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    assert_non_live_environment()
    errors = validate_contract()
    if errors:
        for error in errors:
            print(f"evidence_lab_contract_error: {error}", file=sys.stderr)
        return 2
    if args.validate:
        print("evidence_lab_contract_ok")
        return 0
    if args.mode == "ephemeral" and not args.provision:
        parser.error("--mode ephemeral requires --provision")
    if args.keep and not args.provision:
        parser.error("--keep requires --provision")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (
        args.output.resolve() if args.output else ROOT / "certification" / "evidence-lab" / run_id
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    results = offline_checks(output_dir)
    if args.mode == "ephemeral" and all(row["status"] == "passed" for row in results):
        results.extend(ephemeral_checks(keep=args.keep))

    passed = all(row["status"] == "passed" for row in results)
    if not passed:
        state = "failed"
        maximum_claim = "no_claim"
    elif args.mode == "ephemeral":
        state = "ephemeral_dependency_verified"
        maximum_claim = "ephemeral_dependency_verified"
    else:
        state = "source_verified"
        maximum_claim = "source_verified"

    matrix = load_json(MATRIX_PATH)
    remaining = sorted(
        {
            gate
            for capability in matrix["capabilities"]
            for gate in capability["remaining_live_gate"]
        }
    )
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "mode": args.mode,
        "environment_class": "non_production_evidence_lab",
        "started_at": started_at,
        "finished_at": utc_now(),
        "source_identity": source_identity(),
        "state": state,
        "maximum_claim": maximum_claim,
        "production_certified": False,
        "results": results,
        "remaining_live_gates": remaining,
        "provenance": {
            "format": "slsa-inspired-local-v1",
            "authenticity": "unsigned_local",
            "note": "This is a local evidence statement, not a signed SLSA provenance attestation.",
        },
    }
    (output_dir / "evidence_lab_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "evidence_lab_report.md").write_text(
        markdown_report(payload),
        encoding="utf-8",
    )
    print(f"evidence_lab_state={state}")
    print(f"evidence_lab_report={output_dir / 'evidence_lab_report.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
