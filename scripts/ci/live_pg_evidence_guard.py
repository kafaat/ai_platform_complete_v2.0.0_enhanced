#!/usr/bin/env python3
"""عقد وظيفة PG المخصّصة — يُفرَض ويُلخَّص، ولا يُوصَف في تعليق.

``FAKE-CONNECTION-ENFORCES-NOTHING-01`` · ``DEDICATED_PG_JOB``

الوظيفة العامّة تتخطّى بأمان عند غياب القاعدة؛ أمّا هذه فتخطّيها **خضرةٌ تعني «لم
يُقَس»**، وهو الصنف الذي أوجب الفجوة. فالبنود الخمسة تُفرَض هنا برمّتها:

===============================  ==========================================
غياب القاعدة                     ``SAHOOL_REQUIRE_LIVE_PG=1`` ⇒ خطأ جمع
الدور المقيَّد غير مُثبَت          ``role_properties`` مقروءةً من ``pg_roles``
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

# `-X` يتجاهل `~/.psqlrc`: إعدادٌ محلّيّ (`\pset`, `\timing`) يلوّث الخرج فيُقرأ
# سطرٌ زائد قيمةَ كتالوج. و`ON_ERROR_STOP=1` يجعل خطأ SQL يُنهي بغير صفر — بدونه
# قد يعود psql بصفرٍ بعد خطأ فيُقرأ خرجٌ ناقص «نجاحاً»، وهو الصنف الذي يوجد هذا
# الحارس ضدّه. (تصويب المالك.)
_PSQL_SAFE_FLAGS = ["-X", "-v", "ON_ERROR_STOP=1"]

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "architecture" / "live_pg_schema_contract.json"


def psql(sql: str, *, database: str, role: str) -> str:
    """‏`-qAtc` بلا `-h/-p`: تُقرأ من البيئة، فلا تمرّ عبر سطر أمر يُطبَع عند الفشل.

    و`_PSQL_SAFE_FLAGS` جزءٌ من العقد لا تجميل — انظر تعليقها أعلاه.

    وغيابُ العميل يُحوَّل إلى `SystemExit` برسالة عقد: بدونه يرمي `subprocess.run`
    ‏`FileNotFoundError` فتظهر trace غير مُوجَّهة، فيُقرأ عطلُ بيئةٍ خطأً برمجيّاً
    ويُبحَث عنه في المكان الخطأ. (لاحظه Copilot.)
    """
    try:
        proc = subprocess.run(  # noqa: S603
            ["psql", *_PSQL_SAFE_FLAGS, "-d", database, "-U", role, "-qAtc", sql],
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError:
        raise SystemExit(
            "✗ لا عميل psql في PATH — وهذه وظيفة PG المخصّصة، فغيابُ الأداة فشلٌ لا تخطٍّ. "
            "ثبِّت postgresql-client في الوظيفة قبل تشغيل الحارس."
        ) from None
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


# الخصائص التي تُبطِل قياس العزل إن كانت صادقة — **كلٌّ بسببه**، لا قائمةٌ صمّاء.
# سببُ كلٍّ منها جزءٌ من العقد: خاصّيّةٌ تُمنَع بلا سبب مكتوب تُحذَف عند أوّل تعارض
# (`PROHIBITION-WITHOUT-A-REASON`)، وهذا الحارس نفسه بُني ضدّ ذلك الصنف.
#
# **وثقبان مقيسان أوجبا هذا الشكل:** كانت الدالّة تقرأ ثلاثاً ويفحص الشرطُ اثنتين
# — فـ`createdb` تُطبَع ولا تُدان، وهي «خضرةٌ لا تقول شيئاً» بعينها. و`createrole`
# لم تكن تُقرأ أصلاً وهي **أخطرها**: دورٌ يحملها يمنح نفسه عضويّةَ أدوارٍ أخرى
# فيصل إلى بيانات مستأجِرين آخرين بلا superuser وبلا BYPASSRLS — أي أنّ أقصر طريق
# تصعيدٍ كان الوحيد الذي لا يراه.
# المفاتيح **أسماء أعمدة `pg_roles` حرفيّاً** لا أسماءً ودّيّة. اشتققتُ أوّلاً
# العمودَ من اسمٍ ودّيّ (`rol` + `superuser`) فأنتج `rolsuperuser` وهو غير موجود —
# أي أنّي وقعتُ في «قائمتان تصفان الشيء نفسه» داخل التعليق الذي يحذّر منه. الاسم
# الحرفيّ يجعل الاشتقاق مستحيلَ الانحراف، والعرض يتبع الكتالوج فيُراجَع مباشرةً.
_FORBIDDEN_ROLE_ATTRS = {
    "rolsuper": "يتخطّى RLS كلّيّاً، فكلّ ادّعاء عزلٍ تحته يمرّ مجّاناً",
    "rolbypassrls": "يتخطّى RLS دون أن يكون superuser — والأولى وحدها لا تكفي",
    "rolcreatedb": "يُنشئ قاعدةً يملكها، فيتخطّى سياسات هذه القاعدة بالخروج منها",
    "rolcreaterole": "يمنح نفسه عضويّة أدوارٍ أخرى ⇒ تصعيدٌ إلى مستأجِرين آخرين",
}


def role_properties(database: str, owner: str, app_role: str) -> dict[str, str]:
    """يُقرأ ما يُدان بالضبط — لا أكثر فيصير زينةً، ولا أقلّ فيبقى ثقب.

    القراءة مُشتقّة من `_FORBIDDEN_ROLE_ATTRS` لا مكتوبةً بيدٍ موازية: قائمتان تصفان
    الشيء نفسه تنحرفان، وانحرافُهما هنا هو العطل الأصليّ حرفيّاً.
    """
    columns = "||'|'||".join(f"{col}::text" for col in _FORBIDDEN_ROLE_ATTRS)
    row = psql(
        f"select {columns} from pg_roles where rolname='{app_role}'",
        database=database,
        role=owner,
    )
    if not row:
        raise SystemExit(f"✗ الدور المقيَّد '{app_role}' غير موجود — العزل غير قابل للقياس")
    return dict(zip(_FORBIDDEN_ROLE_ATTRS, row.split("|"), strict=True))


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
    "primary_key": "select pg_get_constraintdef(oid) from pg_constraint where conrelid={r} and contype='p'",
    "unique": "select pg_get_constraintdef(oid) from pg_constraint where conrelid={r} and contype='u' order by 1",
    "rls_enabled_forced": "select relrowsecurity::text||'/'||relforcerowsecurity::text from pg_class where oid={r}",
    "check": "select pg_get_constraintdef(oid) from pg_constraint where conrelid={r} and contype='c' order by 1",
    "foreign_key": "select pg_get_constraintdef(oid) from pg_constraint where conrelid={r} and contype='f' order by 1",
    "trigger": "select pg_get_triggerdef(oid) from pg_trigger where tgrelid={r} and not tgisinternal order by 1",
    "index": (
        "select indexdef from pg_indexes where schemaname='public' and tablename='{t}' order by 1"
    ),
    "column": (
        "select column_name||' '||data_type from information_schema.columns "
        "where table_schema='public' and table_name='{t}' order by 1"
    ),
}


def schema_drift(database: str, owner: str) -> list[str]:
    """الغائب يُدان؛ والزائد لا.

    العقد يصف **ما تستند إليه الأدلّة**، لا كامل المخطّط. فهجرةٌ تُضيف قيداً جديداً
    ليست انحرافاً — وإدانتها تجعل العقد جرداً عامّاً يَبيت مع كلّ هجرة فيُدرَّب قارئه
    على تجاهله، وهو ما يُبطِل الحارس بدل أن يُشدّده.
    """
    doc = json.loads(CONTRACT.read_text(encoding="utf-8"))
    problems: list[str] = []

    # الإصدار الرئيسيّ عقدٌ، والتفصيليّ ليس: `16.4` في CI و`16.13` محليّاً وكلاهما
    # يفي. تثبيتُ التفصيليّ يجعل ترقيةَ صورةٍ انحرافاً كاذباً فيُنزَع الحارس.
    major = psql("show server_version_num", database=database, role=owner)[:2]
    if major != str(doc["postgres_major"]):
        problems.append(
            f"✗ الإصدار الرئيسيّ {major} والعقد يشترط {doc['postgres_major']} — "
            "الأدلّة مبنيّة على قواعد نحو DDL لهذا الإصدار"
        )

    for table, expected in doc["objects"].items():
        # التأهيل بالمخطّط ليس تجميلاً: `search_path` قد يقدّم جدولاً مُتماثِل الاسم
        # في مخطّط آخر، فيُقاس العقدُ على جدولٍ ليس الذي تكتب فيه الأدلّة.
        ref = f"'public.{table}'::regclass"
        for kind, want in expected.items():
            query = _QUERY[kind].format(t=table, r=ref)
            live = psql(query, database=database, role=owner).splitlines()
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
    ap.add_argument("--junit", type=Path)
    ap.add_argument("--database", default=os.environ.get("SAHOOL_TEST_PGDATABASE", "sahool"))
    ap.add_argument("--owner", default=os.environ.get("SAHOOL_TEST_PGOWNER", "sahool_user"))
    ap.add_argument("--app-role", default=os.environ.get("SAHOOL_TEST_PGROLE", "sahool_app"))
    ap.add_argument("--min-executed", type=int, default=30)
    ap.add_argument(
        "--attest",
        type=Path,
        help="يكتب الأدلّة مصنوعةً **مربوطة بالـSHA**. سجلّ التشغيل يفنى مع الرَّنَر، "
        "فادّعاء «قِيس على هذا الالتزام» بلا مصنوعة محفوظة لا يُراجَع لاحقاً. "
        "ولا تُلتزَم: مصنوعة تحمل SHA التزامها لا تطابق إعادة توليدها.",
    )
    ap.add_argument(
        "--schema-only",
        action="store_true",
        help="يقارن الكتالوج بالعقد **قبل** الاختبارات ويفشل بانحراف مخطّط — "
        "فيُقرأ العطل باسمه بدل أن يظهر لاحقاً كفشل ادّعاءٍ يُقرأ «الاختبار خاطئ»",
    )
    a = ap.parse_args(argv)

    if a.schema_only:
        drift = schema_drift(a.database, a.owner)
        if drift:
            print("live_pg_schema_drift FAILED:")
            for d in drift:
                print(f"  {d}")
            return 1
        print(
            f"live_pg_schema_contract_ok ({len(json.loads(CONTRACT.read_text(encoding='utf-8'))['objects'])} جدولاً)"
        )
        return 0

    if a.junit is None:
        raise SystemExit("✗ `--junit` مطلوب إلّا مع `--schema-only`")
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
    print(f"  الدور «{a.app_role}»: " + " ".join(f"{k}={v}" for k, v in role.items()))
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
    for attr, why in _FORBIDDEN_ROLE_ATTRS.items():
        if role.get(attr) != "false":
            problems.append(f"✗ الدور «{a.app_role}» يحمل {attr}={role.get(attr)} — {why}")

    if a.attest is not None:
        # يُكتَب **قبل** الحكم لا بعده: أدلّةٌ لا تُحفَظ إلّا عند النجاح تجعل الفشل
        # بلا أثرٍ يُراجَع — وهو عكس الغرض. الحكم نفسه حقلٌ داخلها.
        a.attest.write_text(
            json.dumps(
                {
                    "schema": "sahool.live_pg_evidence_attestation",
                    "version": 1,
                    "commit_sha": os.environ.get("GITHUB_SHA")
                    or subprocess.run(  # noqa: S603
                        ["git", "rev-parse", "HEAD"],
                        capture_output=True,
                        encoding="utf-8",
                        check=False,
                    ).stdout.strip()
                    or "unknown",
                    "run_url": os.environ.get("GITHUB_RUN_ID", ""),
                    "counts": counts,
                    "server": identity,
                    "role": {"name": a.app_role, **role},
                    "schema_contract_matched": not drift,
                    "verdict": "pass" if not problems else "fail",
                    "problems": problems,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"  الأدلّة محفوظة ومربوطة بالـSHA: {a.attest}")

    if problems:
        print("\nlive_pg_evidence FAILED:")
        for p in problems:
            print(f"  {p}")
        return 1
    print("live_pg_evidence_ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
