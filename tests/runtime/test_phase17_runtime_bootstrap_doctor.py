from __future__ import annotations

import importlib.util
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
            # Fernet-compatible test value (32 zero bytes, URL-safe base64). The
            # compose contract remains fail-closed; only this isolated doctor
            # fixture supplies the value required by `docker compose config`.
            "MFA_SECRET_ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            "REDIS_PASSWORD": "strong-pass",
            "ADMIN_PASSWORD": "strong-admin-pass",
            "GRAFANA_PASSWORD": "strong-grafana-pass",
            "TELEGRAM_WEBHOOK_SECRET": "strong-telegram-secret",
            # NATS-BROKER-HAS-NO-AUTHENTICATION-…-01 ثمّ NATS-AUTHORIZATION-NOT-ENFORCED: لكلّ
            # عميلٍ هويّةٌ بكلمة مرورٍ مُلزَمةٍ بـ`:?` في compose — ومن غيرها يسقط
            # `docker compose config` برسالةٍ عن الاستيفاء لا عن الإعداد.
            **{
                f"NATS_{name}_PASSWORD": f"nstrong{name.lower()}"
                for name in (
                    "PLATFORM",
                    "OUTBOX_WORKER",
                    "PLUGIN_WORKER",
                    "MODEL_WORKER",
                    "ACTUATOR_WORKER",
                    "RELAY_WORKER",
                    "LEARNING_WORKER",
                    "NOTIFICATION",
                    "VEGETATION",
                )
            },
        }
    )
    return env


def test_the_fixture_covers_every_required_compose_interpolation():
    """التعليقُ أعلاه يُعلِن الشرطَ — وهذا يفرضه.

    **العطلُ مقيسٌ لا مُتوقَّع:** أُلزِم `NATS_USER`/`NATS_PASSWORD` بـ`:?` في
    `docker-compose.v9.yml`، فسقط `test_runtime_doctor_preflight_json_contract`
    برسالةٍ عن **فشل `docker compose config`** — لا عن متغيّرٍ ناقصٍ في هذه الأداة.
    أي أنّ السببَ الحقيقيّ (تجهيزةٌ صارت ناقصة) يصل القارئَ متنكّراً في عَرَضٍ آخر،
    وهو الصنفُ الذي يُضيّع جولةَ CI كاملة.

    فالشرطُ يُقاس من الشجرة: كلُّ `${VAR:?…}` في compose يجب أن تضبطه `safe_env`.
    """
    import re

    compose = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    required = set(re.findall(r"\$\{([A-Z0-9_]+):\?", compose))
    assert len(required) > 20, "انهار الاستخراج — شرطٌ يُقاس على لا شيء يمرّ دائماً"
    env = safe_env()
    missing = sorted(v for v in required if not env.get(v))
    assert not missing, (
        "متغيّراتٌ يُلزِمها compose بـ`:?` ولا تضبطها `safe_env`: "
        + ", ".join(missing)
        + "\n  أضِفها أعلاه، وإلّا سقط فحصُ `docker-compose-config` على أيّ آلةٍ نظيفة "
        "برسالةٍ عن الاستيفاء لا عن سببها."
    )


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


# ── MINIO-IMAGES-DELETED-FROM-DOCKER-HUB-01: a local `.env` from the old template overrides the fix ──
# The template before #1139 set both variables explicitly to the repositories MinIO deleted from Docker
# Hub, and compose lets the shell and `.env` override the default — so the fix in the compose files and
# `.env.example` never reaches a machine whose `.env` was copied from the old template.
OLD_TEMPLATE_MINIO_IMAGES = (
    "MINIO_IMAGE=minio/minio:RELEASE.2025-04-22T22-12-26Z\n"
    "MINIO_MC_IMAGE=minio/mc:RELEASE.2025-04-16T18-13-26Z\n"
)


def _doctor():
    spec = importlib.util.spec_from_file_location("env_doctor_under_test", DOCTOR)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # @dataclass resolves annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


def _minio_images_check(tmp_path, monkeypatch, local_env=None, shell=None):
    for key in ("MINIO_IMAGE", "MINIO_MC_IMAGE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in (shell or {}).items():
        monkeypatch.setenv(key, value)
    (tmp_path / ".env.example").write_bytes((ROOT / ".env.example").read_bytes())
    if local_env is not None:
        (tmp_path / ".env").write_text(local_env, encoding="utf-8")
    checks: list = []
    _doctor().check_minio_images(tmp_path, checks)
    (check,) = checks
    assert check.name == "minio-images"
    return check


def test_minio_images_fail_when_the_local_env_keeps_the_deleted_repositories(tmp_path, monkeypatch):
    check = _minio_images_check(tmp_path, monkeypatch, OLD_TEMPLATE_MINIO_IMAGES)
    assert check.status == "fail", check
    assert set(check.detail["stale"]) == {"MINIO_IMAGE", "MINIO_MC_IMAGE"}
    assert ".env.example" in check.message


def test_minio_images_pass_without_a_local_override(tmp_path, monkeypatch):
    assert _minio_images_check(tmp_path, monkeypatch).status == "pass"


def test_minio_images_pass_when_the_local_env_carries_the_template_pin(tmp_path, monkeypatch):
    template = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    pinned = "".join(
        line + "\n" for line in template if line.startswith(("MINIO_IMAGE=", "MINIO_MC_IMAGE="))
    )
    assert pinned.count("@sha256:") == 2, pinned
    assert _minio_images_check(tmp_path, monkeypatch, pinned).status == "pass"


def test_a_stale_minio_image_in_the_shell_fails_even_with_a_clean_env_file(tmp_path, monkeypatch):
    check = _minio_images_check(
        tmp_path, monkeypatch, shell={"MINIO_MC_IMAGE": "minio/mc:RELEASE.2025-04-16T18-13-26Z"}
    )
    assert check.status == "fail", check
    assert set(check.detail["stale"]) == {"MINIO_MC_IMAGE"}


def test_a_minio_image_away_from_the_pin_is_a_warning_not_a_failure(tmp_path, monkeypatch):
    check = _minio_images_check(
        tmp_path, monkeypatch, "MINIO_IMAGE=quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z\n"
    )
    assert check.status == "warn", check
    assert set(check.detail["differs_from_template"]) == {"MINIO_IMAGE"}


def test_an_empty_shell_value_wins_over_a_stale_env_file(tmp_path, monkeypatch):
    """Copilot on #1162: an empty shell variable takes precedence over `.env`, and `${VAR:-pin}`
    then selects the pin — the stale `.env` underneath is not what compose pulls."""
    check = _minio_images_check(
        tmp_path,
        monkeypatch,
        OLD_TEMPLATE_MINIO_IMAGES,
        shell={"MINIO_IMAGE": "", "MINIO_MC_IMAGE": ""},
    )
    assert check.status == "pass", check
