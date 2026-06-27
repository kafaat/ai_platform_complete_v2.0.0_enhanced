#!/usr/bin/env python3
"""Validate the migration system has one source of truth and no unsafe drift."""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

IGNORED_DUPLICATE_PREFIXES = {"v9"}


def manifest_entries(root: Path) -> list[str]:
    path = root / "migrations/MANIFEST.txt"
    rows: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.endswith(".sql") or line.endswith(".down.sql"):
            continue
        if line in seen:
            raise ValueError(f"duplicate manifest entry: {line}")
        seen.add(line)
        rows.append(line)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors: list[str] = []

    entries = manifest_entries(root)
    entry_set = set(entries)
    for entry in entries:
        if not (root / "migrations" / entry).exists():
            errors.append(f"manifest entry missing on disk: {entry}")

    sql_files = sorted(p.name for p in (root / "migrations").glob("*.sql") if not p.name.endswith(".down.sql"))
    unlisted = [name for name in sql_files if name not in entry_set]
    if unlisted:
        errors.append("SQL migrations not listed in MANIFEST.txt: " + ", ".join(unlisted[:30]))

    prefixes: dict[str, list[str]] = defaultdict(list)
    for name in sql_files:
        match = re.match(r"^(v\d+)(?:_|$)", name)
        if match:
            prefixes[match.group(1)].append(name)
    duplicate_prefixes = {k: v for k, v in prefixes.items() if len(v) > 1 and k not in IGNORED_DUPLICATE_PREFIXES}
    if duplicate_prefixes:
        rendered = "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(duplicate_prefixes.items()))
        errors.append("duplicate numeric migration prefixes: " + rendered)

    legacy_sql = root / "scripts_v9/run_migrations.sql"
    legacy_py = root / "scripts_v9/migrate.py"
    legacy_sql_text = legacy_sql.read_text(encoding="utf-8", errors="replace") if legacy_sql.exists() else ""
    legacy_py_text = legacy_py.read_text(encoding="utf-8", errors="replace") if legacy_py.exists() else ""
    if "MANIFEST.txt" not in legacy_sql_text:
        errors.append("scripts_v9/run_migrations.sql does not declare MANIFEST.txt as source of truth")
    if "MANIFEST.txt" not in legacy_py_text or "manifest_order" not in legacy_py_text:
        errors.append("scripts_v9/migrate.py is not manifest-driven")
    missing_from_legacy_sql = [entry for entry in entries if f"migrations/{entry}" not in legacy_sql_text]
    if missing_from_legacy_sql:
        errors.append("scripts_v9/run_migrations.sql is missing manifest entries: " + ", ".join(missing_from_legacy_sql[:20]))

    if errors:
        print("migration manifest validation failed:")
        for error in errors:
            print(f" - {error}")
        return 1
    print(f"migration manifest validation passed: {len(entries)} migrations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
