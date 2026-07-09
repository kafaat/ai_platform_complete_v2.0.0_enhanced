#!/usr/bin/env python3
"""SAHOOL production RLS/runtime-role gate.

Static, CI-safe guard for the exact class of failures that previously broke
multi-tenant isolation: runtime services accidentally using the owner/superuser
DB role, or broad BYPASSRLS access outside the explicit jobs channel.

This script does not connect to Postgres. It validates checked-in deployment
contracts before a container is started.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception as exc:  # pragma: no cover - deployment env issue
    print(f"FAIL: PyYAML is required for rls_runtime_gate.py: {exc}")
    sys.exit(2)

ROOT = Path(os.environ.get("ROOT", Path(__file__).resolve().parents[2]))
COMPOSE = ROOT / "docker-compose.v9.yml"
ENV_FILES = [ROOT / ".env", ROOT / ".env.example"]

OWNER_OR_SUPERUSER_PATTERNS = (
    re.compile(r"postgres(?:ql)?://(?:postgres|sahool_user)(?::|@|/)"),
    re.compile(r"POSTGRES_USER\s*[:=]\s*postgres\b"),
    re.compile(r"sslmode=disable\b"),
)

ALLOWED_JOBS_DB_SERVICES = {
    "sahool-platform",
    "sahool-weather-polygon-worker",
    "sahool-weather-signal-engine",
    "sahool-phase-runtime-outbox-worker",
    "sahool-plugin-runtime-worker",
    "sahool-model-registry-worker",
    "sahool-actuator-dispatch-worker",
    # عامل إبطال كاش الراستر (FINDING-005): يطالب طابور raster_cache_invalidations
    # العابر بدور BYPASSRLS ثمّ يعلّم raster_assets stale بفلتر tenant_id صريح.
    "sahool-raster-cache-invalidation-worker",
    # عامل فحص backfill (v5/v6): يطالب backfill_runs العابر بدور JOBS ويجدول المعالجة.
    "sahool-raster-backfill-scan-worker",
}

TRUTHY = {"1", "true", "yes", "on"}


def _env_map(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, list):
        out: dict[str, str] = {}
        for item in raw:
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                out[k] = v
        return out
    return {}


def _strip_comment(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("#"):
        return ""
    return line


def _check_env_files(errors: list[str]) -> None:
    for path in ENV_FILES:
        if not path.exists():
            continue
        text = "\n".join(
            _strip_comment(line) for line in path.read_text(encoding="utf-8").splitlines()
        )
        for pattern in OWNER_OR_SUPERUSER_PATTERNS:
            if pattern.search(text):
                errors.append(
                    f"{path.name}: forbidden runtime DB/TLS pattern matched: {pattern.pattern}"
                )
        if "DATABASE_URL=" in text and not re.search(
            r"^DATABASE_URL=postgresql://sahool_app:", text, re.M
        ):
            errors.append(f"{path.name}: DATABASE_URL must point to sahool_app")
        if "JOBS_DATABASE_URL=" in text and not re.search(
            r"^JOBS_DATABASE_URL=postgresql://sahool_jobs:", text, re.M
        ):
            errors.append(f"{path.name}: JOBS_DATABASE_URL must point to sahool_jobs")


def _check_compose(errors: list[str]) -> None:
    if not COMPOSE.exists():
        errors.append("docker-compose.v9.yml not found")
        return
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    services = compose.get("services", {}) or {}
    if "sahool-platform" not in services:
        errors.append("sahool-platform must be present in canonical compose")
    for name, svc in services.items():
        env = _env_map((svc or {}).get("environment"))
        # Postgres owner is allowed only for the database bootstrap container itself.
        if name != "sahool-postgres" and env.get("POSTGRES_USER", "") == "postgres":
            errors.append(f"{name}: POSTGRES_USER=postgres is forbidden for runtime services")
        db_url = env.get("DATABASE_URL", "")
        if db_url:
            for forbidden in (
                "postgresql://postgres",
                "postgres://postgres",
                "postgresql://sahool_user",
                "postgres://sahool_user",
            ):
                if forbidden in db_url:
                    errors.append(f"{name}: DATABASE_URL uses owner/superuser role: {forbidden}")
            if "sslmode=disable" in db_url:
                errors.append(f"{name}: DATABASE_URL disables DB TLS")
        jobs_url = env.get("JOBS_DATABASE_URL")
        if jobs_url and name not in ALLOWED_JOBS_DB_SERVICES:
            errors.append(
                f"{name}: JOBS_DATABASE_URL is only allowed for {sorted(ALLOWED_JOBS_DB_SERVICES)}"
            )
        allow_bypass = env.get("SAHOOL_ALLOW_RLS_BYPASS_ROLE", "").strip().lower()
        if allow_bypass in TRUTHY:
            errors.append(f"{name}: SAHOOL_ALLOW_RLS_BYPASS_ROLE must not be enabled in compose")


def main() -> int:
    errors: list[str] = []
    _check_env_files(errors)
    _check_compose(errors)
    if errors:
        print("FAIL: RLS/runtime role gate")
        for err in errors:
            print(f" - {err}")
        return 1
    print("OK: RLS/runtime role gate passed")
    print("OK: runtime DATABASE_URL is constrained to sahool_app")
    print("OK: JOBS_DATABASE_URL is limited to approved background workers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
