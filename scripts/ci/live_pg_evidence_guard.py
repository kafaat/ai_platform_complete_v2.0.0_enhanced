#!/usr/bin/env python3
"""عقد وظيفة PG المخصّصة — يُفرَض ويُلخَّص، ولا يُوصَف في تعليق.

``FAKE-CONNECTION-ENFORCES-NOTHING-01`` · ``DEDICATED_PG_JOB``

الوظيفة العامّة تتخطّى بأمان عند غياب القاعدة؛ أمّا هذه فتخطّيها **خضرةٌ تعني «لم
يُقَس»**، وهو الصنف الذي أوجب الفجوة. فالبنود الخمسة تُفرَض هنا برمّتها:

===============================  ==========================================
غياب القاعدة                     ``SAHOOL_REQUIRE_LIVE_PG=1`` ⇒ خطأ جمع
الدور المقيَّد غير مُثبَت          ``--require-restricted-role``
اختبارات مُنتقاة = صفر            ``executed == 0`` ⇒ فشل
اختبارات حيّة مُتخطّاة > صفر       ``skipped > 0`` ⇒ فشل
انحراف الهجرات/المخطّط            مقارنة الكتالوج بـ``live_pg_schema_contract.json``
===============================  ==========================================

**ولماذا `skipped > 0` فشلٌ هنا وحده:** التخطّي في وظيفةٍ عامّة إعلانُ حدٍّ صادق؛
وفيها هو **الثقب نفسه بثوب أخضر**. و``SAHOOL_REQUIRE_LIVE_PG`` يحرس غياب القاعدة
ولا يرى تخطّياً من مصدر آخر — ``importorskip`` مثلاً — فيبقى بابٌ مفتوح بلا هذا.

**والملخّص ليس تجميلاً:** «نجحت» بلا عددٍ مُنفَّذ لا تُميّز التنفيذ من الجمع الفارغ.
فيُطبَع ``collected/executed/passed/failed/skipped`` مع إصدار الخادم وPostGIS
وخصائص الدور — **وبلا أيّ من متغيّرات الاتّصال**: لا مضيف ولا منفذ ولا مستخدم ولا
كلمة مرور. ما يُطبَع خصائصُ مقيسة لا بيانات اعتماد.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "architecture" / "live_pg_schema_contract.json"


def psql(sql: str, *, database: str, role: str) -> str:
    """‏`-qAtc` بلا `-h/-p`: تُقرأ من البيئة، فلا تمرّ عبر سطر أمر يُطبَع عند الفشل."""
    proc = subprocess.run(  # noqa: S603
        ["psql", "-d", database, "-U", role, "-qAtc", sql],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"✗ تعذّر الاستعلام عن الكتالوج: {proc.stderr.strip()[:400]}")
    return proc.stdout.strip()


# ───────────────────────────── ① حصيلة التنفيذ ─────────────────────────────


def tally(junit: Path) -> dict[str, int]:
    """من `--junitxml` لا من نصّ السطر الأخير.

    السطر الأخير صيغةُ عرضٍ تتبدّل بإصدار pytest وبالإضافات؛ وjunit عقدٌ مُهيكَل.
    وتحليلُ نصٍّ حيث تتوفّر بنية هو `MATCHING-TEXT-WHERE-STRUCTURE-WAS-REQUIRED`.
    """
    if not junit.is_file():
        raise SystemExit(f"✗ لا تقرير تنفيذ في {junit} — لم يُشغَّل pytest أصلاً")
    root = ET.parse(junit).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise SystemExit("✗ تقرير تنفيذ بلا أيّ testsuite — لم يُجمَع شيء")

    total = sum(int(s.get("tests", 0)) for s in suites)
    failures = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    return {
        "collected": total,
        "executed": total - skipped,
        "passed": total - failures - errors - skipped,
        "failed": failures + errors,
        "skipped": skipped,
    }


# ─────────────────────── ② الدور المقيَّد وهويّة الخادم ───────────────────────


def role_properties(database: str, owner: str, app_role: str) -> dict[str, str]:
    row = psql(
        "select rolsuper::text||'|'||rolbypassrls::text||'|'||rolcreatedb::text "
        f"from pg_roles where rolname='{app_role}'",
        database=database,
        role=owner,
    )
    if not row:
        raise SystemExit(f"✗ الدور المقيَّد '{app_role}' غير موجود — العزل غير قابل للقياس")
    super_, bypass, createdb = row.split("|")
    return {"superuser": super_, "bypassrls": bypass, "createdb": createdb}


def server_identity(database: str, owner: str) -> dict[str, str]:
    version = psql("show server_version", database=database, role=owner)
    postgis = psql(
        "select coalesce((select extversion from pg_extension where extname='postgis'), 'غير مثبَّتة')",
        database=database,
        role=owner,
    )
    return {"postgresql": version, "postgis": postgis}


# ──────────────────────── ③ انحراف الهجرات / المخطّط ────────────────────────

_QUERY = {
    "primary_key": "select pg_get_constraintdef(oid) from pg_constraint where conrelid='{t}'::regclass and contype='p'",
    "unique": "select pg_get_constraintdef(oid) from pg_constraint where conrelid='{t}'::regclass and contype='u' order by 1",
    "rls_enabled_forced": "select relrowsecurity::text||'/'||relforcerowsecurity::text from pg_class where oid='{t}'::regclass",
    "check": "select pg_get_constraintdef(oid) from pg_constraint where conrelid='{t}'::regclass and contype='c' order by 1",
    "foreign_key": "select pg_get_constraintdef(oid) from pg_constraint where conrelid='{t}'::regclass and contype='f'",
    "trigger": "select pg_get_triggerdef(oid) from pg_trigger where tgrelid='{t}'::regclass and not tgisinternal",
    "index": "select indexdef from pg_indexes where tablename='{t}'",
    "column": "select column_name||' '||data_type from information_schema.columns where table_name='{t}'",
}


def schema_drift(database: str, owner: str) -> list[str]:
    """الغائب يُدان؛ والزائد لا.

    العقد يصف **ما تستند إليه الأدلّة**، لا كامل المخطّط. فهجرةٌ تُضيف قيداً جديداً
    ليست انحرافاً — وإدانتها تجعل العقد جرداً عامّاً يَبيت مع كلّ هجرة فيُدرَّب قارئه
    على تجاهله، وهو ما يُبطِل الحارس بدل أن يُشدّده.
    """
    doc = json.loads(CONTRACT.read_text(encoding="utf-8"))
    problems: list[str] = []
    for table, expected in doc["objects"].items():
        for kind, want in expected.items():
            live = psql(_QUERY[kind].format(t=table), database=database, role=owner).splitlines()
            live = [ln for ln in live if ln.strip()]
            wanted = want if isinstance(want, list) else [want]
            for item in wanted:
                if item not in live:
                    problems.append(
                        f"✗ {table}.{kind}: العقد يتطلّب «{item}» ولا يقابله شيء في الكتالوج"
                    )
    return problems


# ───────────────────────────────── التقرير ─────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", type=Path, required=True)
    ap.add_argument("--database", default=os.environ.get("SAHOOL_TEST_PGDATABASE", "sahool"))
    ap.add_argument("--owner", default=os.environ.get("SAHOOL_TEST_PGOWNER", "sahool_user"))
    ap.add_argument("--app-role", default=os.environ.get("SAHOOL_TEST_PGROLE", "sahool_app"))
    ap.add_argument("--min-executed", type=int, default=25)
    a = ap.parse_args(argv)

    counts = tally(a.junit)
    identity = server_identity(a.database, a.owner)
    role = role_properties(a.database, a.owner, a.app_role)
    drift = schema_drift(a.database, a.owner)

    print("─── أدلّة PG الحيّة — ملخّص مُشتقّ ───")
    print(
        "  التنفيذ: "
        f"collected={counts['collected']} executed={counts['executed']} "
        f"passed={counts['passed']} failed={counts['failed']} skipped={counts['skipped']}"
    )
    print(f"  الخادم: PostgreSQL {identity['postgresql']} · PostGIS {identity['postgis']}")
    print(
        f"  الدور «{a.app_role}»: superuser={role['superuser']} "
        f"bypassrls={role['bypassrls']} createdb={role['createdb']}"
    )
    print(f"  عقد المخطّط: {'مطابق' if not drift else f'{len(drift)} انحرافاً'}")

    problems: list[str] = list(drift)
    # شرطٌ واحد برسالتين، لا `if/elif`. الصياغة الأولى عندي فصلت الصفر عن الحدّ
    # الأدنى، فكان تعطيلُ فرع الصفر **لا يُسقِط شيئاً**: يلتقطه `elif` لأنّ ٠ < ٢٥.
    # أمسكَته الطفرة المُسجَّلة وهي خضراء — أي أنّ الفرع كان زينةً لا حارساً.
    if counts["executed"] < a.min_executed:
        problems.append(
            "✗ صفر اختبار مُنفَّذ — أخضرُ بلا قياس هو الفجوة نفسها"
            if counts["executed"] == 0
            else f"✗ نُفِّذ {counts['executed']} فقط (الحدّ {a.min_executed}) — الملفّ لم يُشغَّل كاملاً"
        )
    if counts["skipped"] > 0:
        problems.append(
            f"✗ {counts['skipped']} اختباراً حيّاً مُتخطّى — التخطّي هنا خضرةٌ تعني «لم يُقَس». "
            "‏SAHOOL_REQUIRE_LIVE_PG يحرس غياب القاعدة وحده، وهذا يسدّ ما سواه."
        )
    if counts["failed"] > 0:
        problems.append(f"✗ {counts['failed']} فشلاً — يُقرأ في سجلّ pytest أعلاه")
    if role["superuser"] != "false" or role["bypassrls"] != "false":
        problems.append(
            f"✗ الدور «{a.app_role}» غير مقيَّد (superuser={role['superuser']} "
            f"bypassrls={role['bypassrls']}) — كلّ ادّعاء عزلٍ تحته يمرّ مجّاناً"
        )

    if problems:
        print("\nlive_pg_evidence FAILED:")
        for p in problems:
            print(f"  {p}")
        return 1
    print("live_pg_evidence_ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
