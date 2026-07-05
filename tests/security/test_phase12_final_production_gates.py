from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_rls_runtime_gate_passes() -> None:
    result = subprocess.run(
        ["python", "scripts/security/rls_runtime_gate.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RLS/runtime role gate passed" in result.stdout


def test_jobs_database_url_is_limited_to_background_channels() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    allowed = {
        "sahool-platform",
        "sahool-weather-polygon-worker",
        "sahool-weather-signal-engine",
        "sahool-phase-runtime-outbox-worker",
        "sahool-plugin-runtime-worker",
        "sahool-model-registry-worker",
        "sahool-actuator-dispatch-worker",
        # عامل إبطال كاش الراستر (FINDING-005): يطالب طابور raster_cache_invalidations
        # العابر بدور JOBS (BYPASSRLS) ثمّ يعلّم raster_assets stale بفلتر tenant_id صريح.
        "sahool-raster-cache-invalidation-worker",
        # عامل فحص backfill (v5/v6): يطالب backfill_runs العابر بدور JOBS ويجدول المعالجة.
        "sahool-raster-backfill-scan-worker",
    }
    offenders: list[str] = []
    for name, svc in compose["services"].items():
        env = svc.get("environment") or {}
        if isinstance(env, list):
            env = dict(item.split("=", 1) for item in env if isinstance(item, str) and "=" in item)
        if "JOBS_DATABASE_URL" in env and name not in allowed:
            offenders.append(name)
    assert offenders == []


def test_checked_in_env_uses_restricted_runtime_roles() -> None:
    # ‎.env‎ سرّيّ مُستثنى من git (.gitignore)؛ القالب المُودَع هو ‎.env.example‎ وعليه
    # تُفرَض الأدوار المقيّدة (sahool_app/sahool_jobs لا postgres/sahool_user).
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^DATABASE_URL=postgresql://sahool_app:", env, re.M)
    assert re.search(r"^JOBS_DATABASE_URL=postgresql://sahool_jobs:", env, re.M)
    assert not re.search(r"^DATABASE_URL=postgresql://(?:postgres|sahool_user):", env, re.M)


def test_production_validation_gate_script_exists_and_chains_required_checks() -> None:
    script = (ROOT / "scripts/production_validation_gate.sh").read_text(encoding="utf-8")
    required = [
        "bash scripts/security_audit.sh",
        "python scripts/security/rls_runtime_gate.py",
        "docker-compose.v9.yml parsed",
        "required runtime migrations",
        "migration manifest consistency",
        "Python compile",
    ]
    for token in required:
        assert token in script
