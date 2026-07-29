from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR = ROOT / "scripts/runtime/env_doctor.py"
WRAPPER = ROOT / "scripts/runtime/runtime_doctor.sh"
REPORT = ROOT / "PHASE17_RUNTIME_BOOTSTRAP_ENV_DOCTOR_REPORT_20260626.md"


def safe_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": "postgresql://sahool_app:strong-pass@sahool-postgres:5432/sahool",
            "JOBS_DATABASE_URL": "postgresql://sahool_jobs:strong-pass@sahool-postgres:5432/sahool",
            "JWT_PUBLIC_KEY": "-----BEGIN PUBLIC KEY-----\\nTEST\\n-----END PUBLIC KEY-----",
            "JWT_ISSUER": "sahool",
            "JWT_AUDIENCE": "sahool-api",
            "X_AGENT_TOKEN": "strong-token-value-for-contract-tests",
            "REDIS_URL": "redis://:strong-pass@sahool-redis:6379/0",
            "NATS_URL": "nats://sahool-nats:4222",
            "MINIO_ROOT_USER": "sahool-minio",
            "MINIO_ROOT_PASSWORD": "strong-minio-password",
            "MINIO_ACCESS_KEY": "sahool-minio",
            "MINIO_SECRET_KEY": "strong-minio-password",
            "S3_ACCESS_KEY": "sahool-minio",
            # docker-compose.v9.yml requires each of these (`${VAR:?...}`); the
            # docker-compose-config check runs `docker compose config` with this exact
            # subprocess env and no `.env` file (gitignored), so every required
            # interpolation must be set here or the check fails on any clean machine.
            "SH_CLIENT_ID": "sahool-sh-client-id",
            "SH_CLIENT_SECRET": "sahool-sh-client-secret",
            "RASTER_S3_ACCESS_KEY": "sahool-raster-s3-access-key",
            "RASTER_S3_SECRET_KEY": "sahool-raster-s3-secret-key",
            "SCOUT_INGEST_S3_ACCESS_KEY": "sahool-scout-s3-access-key",
            "SCOUT_INGEST_S3_SECRET_KEY": "sahool-scout-s3-secret-key",
            "QDRANT_API_KEY": "sahool-qdrant-api-key",
            "MQTT_USERNAME": "sahool-mqtt",
            "MQTT_PASSWORD": "sahool-mqtt-password",
            "EDGE_SYNC_TOKEN": "sahool-edge-sync-token",
            "FIELD_SERVICE_TENANT_ASSERTION_KEY": "sahool-field-service-key",
            "SAHOOL_AGENT_TOKEN": "strong-token-value-for-contract-tests",
            "SAHOOL_BUILD_ID": "test-build",
            "TESTED_SHA": "0000000000000000000000000000000000000",
            "ZLMEDIAKIT_IMAGE": "zlmediakit/zlmediakit:master",
            "APP_DB_PASSWORD": "strong-pass",
            "DB_PASSWORD": "strong-pass",
            "INGEST_DB_PASSWORD": "strong-pass",
            "JOBS_DB_PASSWORD": "strong-pass",
            "JWT_SECRET": "strong-jwt-secret",
            "REDIS_PASSWORD": "strong-pass",
            "ADMIN_PASSWORD": "strong-admin-pass",
            "GRAFANA_PASSWORD": "strong-grafana-pass",
            "TELEGRAM_WEBHOOK_SECRET": "strong-telegram-secret",
        }
    )
    return env


def test_phase17_assets_exist():
    assert DOCTOR.exists()
    assert WRAPPER.exists()
    assert REPORT.exists()


def test_runtime_doctor_preflight_json_contract(tmp_path):
    out = tmp_path / "doctor.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(DOCTOR),
            "--root",
            str(ROOT),
            "--mode",
            "preflight",
            "--format",
            "json",
            "--output",
            str(out),
        ],
        cwd=ROOT,
        env=safe_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    assert proc.returncode in (0, 2), proc.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["readiness"] in {"ready", "attention"}
    names = {c["name"] for c in payload["checks"]}
    assert {
        "required-files",
        "environment",
        "migrations",
        "compose-static",
        "docker-compose-config",
        "local-port-scan",
    }.issubset(names)
    failed = [c for c in payload["checks"] if c["status"] == "fail"]
    assert failed == []


def test_runtime_doctor_detects_bad_database_role():
    env = safe_env()
    env["DATABASE_URL"] = "postgresql://postgres:bad@sahool-postgres:5432/sahool"
    proc = subprocess.run(
        [
            sys.executable,
            str(DOCTOR),
            "--root",
            str(ROOT),
            "--mode",
            "preflight",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    env_check = next(c for c in payload["checks"] if c["name"] == "environment")
    assert env_check["status"] == "fail"
    assert "sahool_app" in env_check["message"]


def test_release_builder_tracks_phase17_assets():
    builder = (ROOT / "scripts/release/build_release_bundle.py").read_text(encoding="utf-8")
    assert "scripts/runtime/env_doctor.py" in builder
    assert "scripts/runtime/runtime_doctor.sh" in builder
    assert "PHASE17_RUNTIME_BOOTSTRAP_ENV_DOCTOR_REPORT_20260626.md" in builder


def test_command_available_ignores_unreadable_path_entries(monkeypatch, tmp_path):
    from scripts.runtime.env_doctor import command_available

    unreadable = tmp_path / "blocked"
    unreadable.mkdir()
    unreadable.chmod(0)
    try:
        monkeypatch.setenv("PATH", str(unreadable))
        assert command_available("definitely-not-installed") is False
    finally:
        unreadable.chmod(0o700)
