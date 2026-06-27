#!/usr/bin/env python3
"""Validate SAHOOL tenant RLS write-path protections.

This is a static guard for the production migration chain:
* v122 must contain the catalog backfill that adds WITH CHECK to historical
  tenant policies missing write checks.
* New migrations after v122 may not create tenant write policies without
  WITH CHECK.
* New migrations after v122 may not use app.tenant_id as the sole tenant
  session variable; app.current_tenant is canonical.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

CREATE_POLICY_RE = re.compile(r"CREATE\s+POLICY\s+.*?;", re.IGNORECASE | re.DOTALL)
MIGRATION_NUM_RE = re.compile(r"^v(\d+)[_-].*\.sql$")


def migration_number(path: Path) -> int | None:
    match = MIGRATION_NUM_RE.match(path.name)
    return int(match.group(1)) if match else None


def policy_is_write_path(stmt: str) -> bool:
    upper = stmt.upper()
    # PostgreSQL default for CREATE POLICY is FOR ALL when FOR is omitted.
    return " FOR " not in upper or bool(re.search(r"\bFOR\s+(ALL|INSERT|UPDATE)\b", upper))


def policy_is_tenant_aware(stmt: str) -> bool:
    lower = stmt.lower()
    return "tenant_id" in lower or "app.current_tenant" in lower or "app.tenant_id" in lower


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    migrations = root / "migrations"
    errors: list[str] = []

    v122 = migrations / "v122_rls_with_check_session_unification.sql"
    if not v122.exists():
        errors.append("missing v122_rls_with_check_session_unification.sql backfill migration")
    else:
        text = v122.read_text(encoding="utf-8", errors="replace")
        required_markers = [
            "sahool_effective_tenant_id",
            "pg_policies",
            "with_check IS NULL",
            "ALTER POLICY",
            "WITH CHECK",
            "app.current_tenant",
            "app.tenant_id",
        ]
        for marker in required_markers:
            if marker not in text:
                errors.append(f"v122 backfill missing marker: {marker}")

    for path in sorted(migrations.glob("v*.sql")):
        num = migration_number(path)
        if num is None or num <= 122:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for idx, stmt in enumerate(CREATE_POLICY_RE.findall(text), start=1):
            if policy_is_write_path(stmt) and policy_is_tenant_aware(stmt) and "WITH CHECK" not in stmt.upper():
                errors.append(f"{path.name}: tenant write policy #{idx} missing WITH CHECK")
            if "app.tenant_id" in stmt and "sahool_effective_tenant_id" not in stmt and "app.current_tenant" not in stmt:
                errors.append(f"{path.name}: policy #{idx} uses app.tenant_id without canonical app.current_tenant fallback")

    store = root / "services/sahool-platform/api/phase_runtime_store.py"
    workers = root / "services/sahool-platform/api/phase_runtime_workers.py"
    for source in (store, workers):
        text = source.read_text(encoding="utf-8", errors="replace") if source.exists() else ""
        if "set_config('app.current_tenant'" not in text:
            errors.append(f"{source.relative_to(root)} does not set app.current_tenant")
        if "set_config('app.tenant_id'" not in text:
            errors.append(f"{source.relative_to(root)} does not preserve app.tenant_id compatibility")

    if errors:
        print("RLS write-policy validation failed:")
        for error in errors:
            print(f" - {error}")
        return 1
    print("RLS write-policy validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
