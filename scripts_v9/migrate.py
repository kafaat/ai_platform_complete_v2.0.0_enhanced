#!/usr/bin/env python3
"""SAHOOL migration runner backed by migrations/MANIFEST.txt.

This legacy entry point is kept for compatibility, but the hard-coded v9-only
migration list has been removed. The single source of truth is now
``migrations/MANIFEST.txt`` so Phase 9-12/Feature Store/Workers migrations are
not skipped by old operational scripts.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations"
MANIFEST = MIGRATIONS_DIR / "MANIFEST.txt"

MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by  TEXT NOT NULL DEFAULT current_user
);
"""


def manifest_order() -> list[str]:
    if not MANIFEST.exists():
        print(f"✗ ملف ترتيب الترحيلات مفقود: {MANIFEST}")
        sys.exit(2)
    rows: list[str] = []
    seen: set[str] = set()
    for raw in MANIFEST.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.endswith(".sql") or line.endswith(".down.sql"):
            continue
        if line in seen:
            print(f"✗ تكرار في MANIFEST.txt: {line}")
            sys.exit(2)
        seen.add(line)
        rows.append(line)
    return rows


MIGRATION_ORDER = manifest_order()


def _db_url() -> str:
    # JOBS_DATABASE_URL: الهجرات تُطبَّق بدور sahool_jobs (صلاحيّة DDL عبر المسار
    # المُهيَّأ)؛ helm/k8s يمرّره باسمه (migration-job.yaml)، فنقبله كي يعمل مسار النشر.
    url = os.getenv("DATABASE_URL") or os.getenv("MIGRATE_DB_URL") or os.getenv("JOBS_DATABASE_URL")
    if not url:
        print("✗ DATABASE_URL غير مضبوط. اضبطه ثمّ أعِد المحاولة.")
        print("  export DATABASE_URL='postgresql://sahool_jobs:PASS@localhost/sahool'")
        sys.exit(2)
    return url


def _psql(url: str, sql: str | None = None, file: Path | None = None, capture: bool = True) -> str:
    cmd = ["psql", url, "-v", "ON_ERROR_STOP=1", "-tA"]
    if file:
        cmd += ["-f", str(file)]
    elif sql:
        cmd += ["-c", sql]
    result = subprocess.run(cmd, capture_output=capture, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip())
    return (result.stdout or "").strip()


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _applied(url: str) -> dict[str, str]:
    _psql(url, MIGRATIONS_TABLE)
    out = _psql(url, "SELECT version || '|' || checksum FROM schema_migrations;")
    res: dict[str, str] = {}
    for line in out.splitlines():
        if "|" in line:
            version, checksum = line.split("|", 1)
            res[version.strip()] = checksum.strip()
    return res


def cmd_status(url: str) -> None:
    applied = _applied(url)
    print("═══ حالة الترحيلات من migrations/MANIFEST.txt ═══")
    for migration in MIGRATION_ORDER:
        path = MIGRATIONS_DIR / migration
        if not path.exists():
            print(f"  ⚠ {migration}: الملفّ مفقود")
            continue
        checksum = _checksum(path)
        if migration in applied:
            drift = "" if applied[migration] == checksum else " ⚠ انجراف checksum!"
            print(f"  ✓ {migration} (مُطبَّق){drift}")
        else:
            print(f"  ○ {migration} (غير مُطبَّق)")
    pending = [m for m in MIGRATION_ORDER if m not in applied]
    print(
        f"\n  المُطبَّق: {len(applied)} · المعلّق: {len(pending)} · المسجّل في MANIFEST: {len(MIGRATION_ORDER)}"
    )


def cmd_up(url: str, dry_run: bool = False) -> None:
    applied = _applied(url)
    pending = [m for m in MIGRATION_ORDER if m not in applied]
    if not pending:
        print("✓ لا ترحيلات معلّقة — المخطّط مُحدَّث.")
        return
    print(f"═══ تطبيق {len(pending)} ترحيلاً من MANIFEST.txt ═══")
    for migration in pending:
        path = MIGRATIONS_DIR / migration
        if not path.exists():
            print(f"✗ {migration}: مفقود — توقّف.")
            sys.exit(1)
        checksum = _checksum(path)
        if dry_run:
            print(f"  [dry-run] سيُطبَّق: {migration}")
            continue
        print(f"  ⟳ تطبيق {migration} ...")
        try:
            _psql(url, file=path)
            _psql(
                url,
                f"INSERT INTO schema_migrations(version, checksum) VALUES ({repr(migration)}, {repr(checksum)});",
            )
            print(f"  ✓ {migration}")
        except RuntimeError as exc:
            print(f"  ✗ فشل {migration}: {exc}")
            print("  توقّف — أصلح الخطأ ثمّ أعِد. الترحيلات السابقة مُسجّلة.")
            sys.exit(1)
    print("✓ اكتمل التطبيق.")


def cmd_down(url: str, dry_run: bool = False) -> None:
    applied = _applied(url)
    applied_ordered = [m for m in MIGRATION_ORDER if m in applied]
    if not applied_ordered:
        print("✓ لا ترحيلات للتراجع عنها.")
        return
    last = applied_ordered[-1]
    down_path = MIGRATIONS_DIR / last.replace(".sql", ".down.sql")
    if not down_path.exists():
        print(f"✗ لا ملفّ تراجع لـ{last}.")
        print(f"  أنشئ {down_path.name} أوّلاً. لا يوجد تراجع وهمي.")
        sys.exit(1)
    if dry_run:
        print(f"  [dry-run] سيُتراجَع عن: {last} عبر {down_path.name}")
        return
    try:
        _psql(url, file=down_path)
        _psql(url, f"DELETE FROM schema_migrations WHERE version = {repr(last)};")
        print(f"  ✓ تراجَع عن {last}")
    except RuntimeError as exc:
        print(f"  ✗ فشل التراجع: {exc}")
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="أداة ترحيل SAHOOL وفق migrations/MANIFEST.txt")
    parser.add_argument("command", choices=["status", "up", "down", "verify"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    url = _db_url()
    if args.command in {"status", "verify"}:
        cmd_status(url)
    elif args.command == "up":
        cmd_up(url, args.dry_run)
    elif args.command == "down":
        cmd_down(url, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
