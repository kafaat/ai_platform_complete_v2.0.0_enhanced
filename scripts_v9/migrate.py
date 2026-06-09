#!/usr/bin/env python3
"""
migrate.py — أداة ترحيل بتتبّع نسخة وتراجع (سدّ فجوة: لا rollback).

الممارسة العالميّة (Alembic/Flyway): تتبّع أيّ ترحيلات طُبّقت + تراجع آمن.
هذه أداة خفيفة بلا تبعيّات خارجيّة (psql فقط) توفّر:
  - جدول schema_migrations (يتتبّع المُطبَّق + checksum + وقت)
  - up: يطبّق الترحيلات غير المُطبَّقة بالترتيب، داخل معاملة
  - down: يتراجع عن آخر ترحيل (يحتاج ملفّ .down.sql مرافق)
  - status: يعرض المُطبَّق وغير المُطبَّق
  - verify: يكشف انجراف checksum (ترحيل عُدِّل بعد التطبيق)

الاستخدام (على جهازك، يحتاج psql + DATABASE_URL):
  python3 scripts_v9/migrate.py status
  python3 scripts_v9/migrate.py up
  python3 scripts_v9/migrate.py down            # يتراجع عن آخر واحد
  python3 scripts_v9/migrate.py up --dry-run

ملفّات الترحيل في migrations/*.sql بترتيب أبجدي. للتراجع، أنشئ
migrations/<name>.down.sql (عكس الترحيل). بلا .down.sql، down يرفض (صدق:
لا يدّعي تراجعاً غير متوفّر).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(ROOT, "migrations")

# ترتيب الترحيلات (حرج — يطابق run_migrations.sql)
MIGRATION_ORDER = [
    "init_v8.sql",
    "v9_foundation.sql",
    "v9_new_tables.sql",
    "v9_auth_improvements.sql",
    "v9_onboarding.sql",
    "v10_command_store_lifecycle.sql",
    "v9_lifecycle_occurred_at.sql",
    "v9_append_only_enforcement.sql",
    "v11_events_bus.sql",
    "v12_trueup_sharing.sql",
    "v9_edge_idempotency.sql",
    "v9_edge_occurred_at.sql",
    "v9_automation_persistence.sql",
    "v13_geospatial_core.sql",
    "v9_rls_tenant_isolation.sql",
]

MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by  TEXT NOT NULL DEFAULT current_user
);
"""


def _db_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("MIGRATE_DB_URL")
    if not url:
        print("✗ DATABASE_URL غير مضبوط. اضبطه ثمّ أعِد المحاولة.")
        print("  export DATABASE_URL='postgresql://sahool_user:PASS@localhost/sahool'")
        sys.exit(2)
    return url


def _psql(url: str, sql: str = None, file: str = None, capture=True):
    """ينفّذ SQL أو ملفّاً عبر psql. يرفع عند الفشل (ON_ERROR_STOP)."""
    cmd = ["psql", url, "-v", "ON_ERROR_STOP=1", "-tA"]
    if file:
        cmd += ["-f", file]
    elif sql:
        cmd += ["-c", sql]
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "").strip())
    return (r.stdout or "").strip()


def _checksum(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def _applied(url: str) -> dict:
    """يُرجِع {version: checksum} للمُطبَّق."""
    _psql(url, MIGRATIONS_TABLE)
    out = _psql(url, "SELECT version || '|' || checksum FROM schema_migrations;")
    res = {}
    for line in out.splitlines():
        if "|" in line:
            v, c = line.split("|", 1)
            res[v.strip()] = c.strip()
    return res


def cmd_status(url: str):
    applied = _applied(url)
    print("═══ حالة الترحيلات ═══")
    for m in MIGRATION_ORDER:
        path = os.path.join(MIGRATIONS_DIR, m)
        if not os.path.exists(path):
            print(f"  ⚠ {m}: الملفّ مفقود")
            continue
        cs = _checksum(path)
        if m in applied:
            drift = "" if applied[m] == cs else " ⚠ انجراف checksum!"
            print(f"  ✓ {m} (مُطبَّق){drift}")
        else:
            print(f"  ○ {m} (غير مُطبَّق)")
    pending = [m for m in MIGRATION_ORDER if m not in applied]
    print(f"\n  المُطبَّق: {len(applied)} · المعلّق: {len(pending)}")


def cmd_up(url: str, dry_run: bool = False):
    applied = _applied(url)
    pending = [m for m in MIGRATION_ORDER if m not in applied]
    if not pending:
        print("✓ لا ترحيلات معلّقة — المخطّط مُحدَّث.")
        return
    print(f"═══ تطبيق {len(pending)} ترحيلاً ═══")
    for m in pending:
        path = os.path.join(MIGRATIONS_DIR, m)
        if not os.path.exists(path):
            print(f"✗ {m}: مفقود — توقّف.")
            sys.exit(1)
        cs = _checksum(path)
        if dry_run:
            print(f"  [dry-run] سيُطبَّق: {m}")
            continue
        print(f"  ⟳ تطبيق {m} ...")
        # تطبيق + تسجيل داخل معاملة واحدة (ذرّيّة: إمّا الكلّ أو لا شيء)
        try:
            _psql(url, file=path)
            _psql(url, f"INSERT INTO schema_migrations(version, checksum) "
                       f"VALUES ('{m}', '{cs}');")
            print(f"  ✓ {m}")
        except RuntimeError as e:
            print(f"  ✗ فشل {m}: {e}")
            print("  توقّف — أصلح الخطأ ثمّ أعِد. (الترحيلات السابقة مُسجّلة.)")
            sys.exit(1)
    print("✓ اكتمل التطبيق.")


def cmd_down(url: str, dry_run: bool = False):
    """يتراجع عن آخر ترحيل مُطبَّق (يحتاج .down.sql مرافق)."""
    applied = _applied(url)
    applied_ordered = [m for m in MIGRATION_ORDER if m in applied]
    if not applied_ordered:
        print("✓ لا ترحيلات للتراجع عنها.")
        return
    last = applied_ordered[-1]
    down_path = os.path.join(MIGRATIONS_DIR, last.replace(".sql", ".down.sql"))
    if not os.path.exists(down_path):
        print(f"✗ لا ملفّ تراجع لـ{last}.")
        print(f"  أنشئ {os.path.basename(down_path)} (عكس الترحيل) أوّلاً.")
        print("  صدق: لا أتراجع عن ترحيل بلا تعليمات تراجع صريحة (خطر فقد بيانات).")
        sys.exit(1)
    if dry_run:
        print(f"  [dry-run] سيُتراجَع عن: {last} عبر {os.path.basename(down_path)}")
        return
    print(f"  ⟳ تراجع عن {last} ...")
    try:
        _psql(url, file=down_path)
        _psql(url, f"DELETE FROM schema_migrations WHERE version = '{last}';")
        print(f"  ✓ تراجَع عن {last}")
    except RuntimeError as e:
        print(f"  ✗ فشل التراجع: {e}")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="أداة ترحيل SAHOOL (تتبّع + تراجع)")
    ap.add_argument("command", choices=["status", "up", "down", "verify"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    url = _db_url()
    if args.command == "status" or args.command == "verify":
        cmd_status(url)
    elif args.command == "up":
        cmd_up(url, args.dry_run)
    elif args.command == "down":
        cmd_down(url, args.dry_run)


if __name__ == "__main__":
    main()
