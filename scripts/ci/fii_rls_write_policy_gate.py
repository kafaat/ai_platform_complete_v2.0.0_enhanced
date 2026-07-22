#!/usr/bin/env python3
"""FII Safety Increment 1C: reject unsafe tenant-write RLS patterns.

This is a static ratchet, not a substitute for the live PostgreSQL integration test.
It scans migrations that define tenant RLS and fails on explicit missing-context bypasses.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

UNSAFE = {
    "missing-context OR bypass": re.compile(
        r"NULLIF\s*\(\s*current_setting\s*\([^)]*app\.current_tenant[^)]*true[^)]*\)\s*,\s*''\s*\)\s+IS\s+NULL\s+OR",
        re.I | re.S,
    ),
    "raw current_tenant IS NULL OR": re.compile(r"current_tenant[^;\n]{0,160}IS\s+NULL\s+OR", re.I),
    "unconditional WITH CHECK": re.compile(r"WITH\s+CHECK\s*\(\s*TRUE\s*\)", re.I | re.S),
}

# Ratchet scope: NEW migrations only (> BASELINE_MAX). Historical migrations are
# shipped, immutable, and superseded at runtime by the forward fail-closed
# migrations below (which DROP+CREATE their tenant_isolation policy after them in
# MANIFEST order). We deliberately do NOT scan the historical files — editing them
# would rewrite shipped history and drift the release checksums; their runtime
# posture is proven fail-closed by the live PostgreSQL integration test, not here.
BASELINE_MAX = 191
TARGETS = {
    "v192_fii_rls_write_fail_closed.sql",
    "v194_fii_chemical_chain_rls_fail_closed.sql",
}


def version(path: Path) -> int | None:
    m = re.match(r"v(\d+)_", path.name)
    return int(m.group(1)) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    ns = ap.parse_args()
    migration_dir = ns.root / "migrations"
    failures: list[str] = []
    for path in sorted(migration_dir.glob("*.sql")):
        v = version(path)
        if path.name not in TARGETS and (v is None or v <= BASELINE_MAX):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in UNSAFE.items():
            if pattern.search(text):
                failures.append(f"{path.relative_to(ns.root)}: {label}")
        if "CREATE POLICY" in text.upper() and "tenant" in text.lower():
            # New tenant-policy migrations must make FORCE explicit when altering a table.
            if "ALTER TABLE" in text.upper() and "FORCE ROW LEVEL SECURITY" not in text.upper():
                failures.append(f"{path.relative_to(ns.root)}: tenant policy without FORCE RLS")
    if failures:
        print("FII RLS write-policy gate FAILED")
        print("\n".join(f"- {x}" for x in failures))
        return 1
    print("FII RLS write-policy gate PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
