"""v240 — مرورٌ واحد على MANIFEST يُعطي مخطّط مرورين، على PostgreSQL حيّة.

المُهاجر يُعيد MANIFEST كاملاً في كلّ تشغيل، فالإنتاج في حالة «مرّتين» والتثبيت الجديد في حالة
«مرّة». كانتا تفترقان في 55 سطر ``pg_dump -s`` (قاعدة فارغة، PG 16، c966fd0b2) لأنّ ملفّاتٍ مبكّرة
تُنشئ فهارس/قيوداً مشروطةً بجداول تُنشئها ملفّاتٌ لاحقة. هذا الاختبار يبني قاعدتين **مؤقّتتين**
فارغتين، يطبّق البيان بالمُشغّل القانونيّ مرّةً على الأولى ومرّتين على الثانية، ويقارن بصمةَ
مخطّطٍ من الكتالوج (أعمدة بترتيبها · قيود · فهارس · مُشغّلات · سياسات · RLS · دوالّ · VIEWs ·
تعليقات) — فلا يعتمد على نسخة ``pg_dump``. أحمر بلا v240 (53 فرقاً) وأخضر به.

يحتاج ``TEST_DATABASE_ADMIN_URL`` (أو ``TEST_DATABASE_URL``) لدورٍ يملك CREATEDB، و``psql`` في PATH.
القاعدتان تُحذفان في ``finally``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

asyncpg = pytest.importorskip("asyncpg")

_ROOT = Path(__file__).resolve().parents[1]
_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or os.getenv("TEST_DATABASE_URL") or ""

pytestmark.append(
    pytest.mark.skipif(
        not _DSN or shutil.which("psql") is None,
        reason="يحتاج TEST_DATABASE_ADMIN_URL/TEST_DATABASE_URL (CREATEDB) و psql",
    )
)

# كلّ استعلامٍ يُعيد أسطراً نصّيّة؛ كائنات الامتدادات (PostGIS…) مستثناة — متطابقة بالبناء.
_EXT_MEMBER = (
    "NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = {cat}::regclass "
    "AND d.objid = {oid} AND d.deptype = 'e')"
)
_FINGERPRINT: dict[str, str] = {
    "columns": f"""
        SELECT format('%s.%s #%s %s %s nn=%s def=%s id=%s gen=%s', n.nspname, c.relname,
               row_number() OVER (PARTITION BY c.oid ORDER BY a.attnum), a.attname,
               format_type(a.atttypid, a.atttypmod), a.attnotnull,
               pg_get_expr(ad.adbin, ad.adrelid), a.attidentity, a.attgenerated)
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
        WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r','p','v','m','f')
          AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast'
          AND {_EXT_MEMBER.format(cat="'pg_class'", oid="c.oid")}""",
    "relations": f"""
        SELECT format('%s.%s kind=%s rls=%s force=%s opts=%s', n.nspname, c.relname, c.relkind,
               c.relrowsecurity, c.relforcerowsecurity, c.reloptions)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('r','p','v','m','f','S')
          AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast'
          AND {_EXT_MEMBER.format(cat="'pg_class'", oid="c.oid")}""",
    "constraints": """
        SELECT format('%s %s %s valid=%s', conrelid::regclass, conname,
               pg_get_constraintdef(oid), convalidated)
        FROM pg_constraint WHERE conrelid <> 0
          AND connamespace NOT IN ('pg_catalog'::regnamespace, 'information_schema'::regnamespace)""",
    "indexes": """
        SELECT indexdef FROM pg_indexes
        WHERE schemaname NOT IN ('pg_catalog','information_schema')""",
    "triggers": """
        SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE NOT tgisinternal""",
    "policies": """
        SELECT format('%s.%s %s %s %s roles=%s using=%s check=%s', schemaname, tablename,
               policyname, permissive, cmd, roles, qual, with_check) FROM pg_policies""",
    "functions": f"""
        SELECT format('%s.%s(%s) %s', n.nspname, p.proname,
               pg_get_function_identity_arguments(p.oid), md5(pg_get_functiondef(p.oid)))
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE p.prokind IN ('f','p')
          AND n.nspname NOT IN ('pg_catalog','information_schema')
          AND {_EXT_MEMBER.format(cat="'pg_proc'", oid="p.oid")}""",
    "views": """
        SELECT format('%s.%s %s', schemaname, viewname, md5(definition)) FROM pg_views
        WHERE schemaname NOT IN ('pg_catalog','information_schema')""",
    # تُفهرَس بالاسم المُحلَّل لا بالـoid (يختلف بين القاعدتين بطبيعته).
    "comments": """
        SELECT format('%s %s', pg_describe_object(classoid, objoid, objsubid), md5(description))
        FROM pg_description
        WHERE classoid IN ('pg_policy'::regclass, 'pg_constraint'::regclass,
                           'pg_class'::regclass, 'pg_proc'::regclass)
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = pg_description.classoid
                          AND d.objid = pg_description.objoid AND d.deptype = 'e')
          AND pg_describe_object(classoid, objoid, objsubid) IS NOT NULL""",
    "extensions": "SELECT format('%s %s', extname, extversion) FROM pg_extension",
    "enums": """
        SELECT format('%s %s %s', enumtypid::regtype, enumsortorder, enumlabel) FROM pg_enum""",
}


def _dsn_for(db: str) -> str:
    parts = urlsplit(_DSN)
    return urlunsplit(parts._replace(path=f"/{db}"))


def _apply_manifest(db: str) -> None:
    parts = urlsplit(_DSN)
    env = dict(os.environ, PGPASSWORD=unquote(parts.password or ""))
    proc = subprocess.run(
        [
            "bash",
            "scripts/ci/apply_migration_manifest.sh",
            "--host",
            parts.hostname or "localhost",
            "--port",
            str(parts.port or 5432),
            "--user",
            unquote(parts.username or ""),
            "--db",
            db,
        ],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, (
        f"manifest on {db} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}"
    )


async def _fingerprint(db: str) -> dict[str, list[str]]:
    conn = await asyncpg.connect(_dsn_for(db))
    try:
        out: dict[str, list[str]] = {}
        for key, sql in _FINGERPRINT.items():
            out[key] = sorted(str(r[0]) for r in await conn.fetch(sql))
        return out
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_one_manifest_pass_equals_two_passes_on_an_empty_database():
    admin = await asyncpg.connect(_DSN)
    try:
        can = await admin.fetchval(
            "SELECT rolsuper OR rolcreatedb FROM pg_roles WHERE rolname = current_user"
        )
    finally:
        await admin.close()
    if not can:
        pytest.skip("الدور في DSN لا يملك CREATEDB")

    tag = uuid.uuid4().hex[:10]
    once, twice = f"v240_pathdep_{tag}_once", f"v240_pathdep_{tag}_twice"
    admin = await asyncpg.connect(_DSN)
    try:
        for db in (once, twice):
            # template0: لا يتعارض مع جلساتٍ أخرى على template1، والقاعدتان من القالب نفسه.
            await admin.execute(f'CREATE DATABASE "{db}" TEMPLATE template0')
        _apply_manifest(once)
        _apply_manifest(twice)
        _apply_manifest(twice)
        a, b = await _fingerprint(once), await _fingerprint(twice)
        assert sum(len(v) for v in a.values()) > 1000, "fingerprint suspiciously small"
        diffs = {
            key: {
                "only_once": sorted(set(a[key]) - set(b[key]))[:20],
                "only_twice": sorted(set(b[key]) - set(a[key]))[:20],
            }
            for key in _FINGERPRINT
            if a[key] != b[key]
        }
        count = sum(len(set(a[k]) ^ set(b[k])) for k in _FINGERPRINT)
        assert not diffs, f"one pass != two passes ({count} differing catalog rows): {diffs}"
    finally:
        for db in (once, twice):
            await admin.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
        await admin.close()
