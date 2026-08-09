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

**والدور يُقاس بأربع خصائص لا باثنتين — وهو ما كانت الوظيفة تُهيّئه ولا تفحصه.**
الوظيفة تُنشئ ``sahool_app`` بـ``nosuperuser nobypassrls nocreatedb nocreaterole``،
بينما القرار كان يقرأ ``superuser`` و``bypassrls`` وحدهما: ``rolcreatedb``
**يُستعلَم عنه ويُطبَع ولا يحكم**، و``rolcreaterole`` **لا يُسأل عنه أصلاً**. فالفجوة
بين ما يُهيَّأ وما يُقاس هي بعينها «نتيجةٌ عن سؤالٍ لم يُطرَح». والأربع تحجب الآن،
و``CREATEROLE`` منها لأنّ مالكها يصنع دوراً يمنحه ما يشاء — فيبلغ بخطوتين ما مُنِع
منه بخطوة.

**والدليل يُكتَب بحكمه قبل رمز الخروج** (``--evidence``) لا بعد نجاح كلّ شيء: وثيقةٌ
لا توجد إلّا يوم النجاح هي المعنى المقلوب لكلمة «دليل». ويربط نفسه بـ``checkout_sha``
و``checkout_tree`` و``github_sha`` **منفصلة**، ويحمل حدَّ صدقه داخله — الخصائص
**مباشرة** من ``pg_roles``، بلا إغلاقٍ انتقاليّ لعضويّات الأدوار ولا أثر ``SET ROLE``.
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


#: أعمدة `pg_roles` المقروءة — والترتيب عقدٌ مع `ROLE_ATTRIBUTES` أدناه.
_ROLE_CATALOGUE_COLUMNS = ("rolsuper", "rolbypassrls", "rolcreatedb", "rolcreaterole")

#: أسماء الخصائص كما تظهر في الملخّص وفي `live_pg_evidence.json`.
ROLE_ATTRIBUTES = ("superuser", "bypassrls", "createdb", "createrole")

#: الخصائص التي **تحجب** إن كانت `true` — قائمةٌ منفصلة عن الاستعلام **عمداً**.
#:
#: والفصل ليس زخرفاً: العطل المُعالَج هنا كان بالضبط خاصّيّةً **تُقرأ وتُطبَع ولا تحكم**.
#: `rolcreatedb` كان يُستعلَم عنه ويُعرَض في الملخّص، بينما القرار يقرأ `superuser` و
#: `bypassrls` وحدهما ⇒ رقمٌ معروض لا حارس. و`rolcreaterole` لم يكن يُسأل عنه أصلاً.
#:
#: **وخطرُ `CREATEROLE` أوسع من اسمه:** دورٌ يملكها يستطيع إنشاء دورٍ آخر ومنحه ما يشاء،
#: فيبلغ بخطوتين ما مُنِع منه بخطوة. فادّعاء «الدور مقيَّد» تحته أضيق ممّا يُقرأ منه.
#:
#: وبقاءُ القائمتين منفصلتين يجعل الطفرتين مستقلّتين: نزعُ عمودٍ من الاستعلام يُسقِط
#: اختبار «الاستعلام يطلب الأربعة»، ونزعُ اسمٍ من هذه يُسقِط اختبار تلك الخاصّيّة وحدها.
#: ولو اشتُقّت إحداهما من الأخرى لأسقطت الطفرةُ الواحدة اختبارين، فيُقرأ الادّعاءان
#: مغطّيَين وأحدُهما بلا حارس.
_REJECT_IF_TRUE = ("superuser", "bypassrls", "createdb", "createrole")

#: القيم المنطقيّة الوحيدة المقبولة من `::text` على `boolean` في PostgreSQL.
_BOOLEAN_TEXT = ("true", "false")


def role_properties(database: str, owner: str, app_role: str) -> dict[str, str]:
    """خصائص الدور **المباشرة** من `pg_roles` — بفشلٍ مغلق على كلّ صفٍّ لا يُقرأ.

    **حدّ الصدق مكتوبٌ هنا وفي الدليل معاً:** هذه خصائص الدور المُسمّى **نفسه**. ولا
    تُثبِت الإغلاق الانتقاليّ لعضويّات الأدوار (`pg_auth_members`) ولا أثر `SET ROLE`
    ولا صلاحيّات مورَّثة من دورٍ عضوٍ فيه. ولذلك يُسمّى الحقل في الـJSON
    `direct_role_attributes` لا `role_isolation`: الاسم يقول مداه.

    **والفشل المغلق ليس احترازاً نظريّاً:** `split("|")` بلا تحقّق يُنتِج قيماً جزئيّة
    صامتة — عمودٌ يُضاف أو يُحذَف فيُقرأ `rolcreatedb` في خانة `rolbypassrls`، أو صفٌّ
    بقيمةٍ ليست منطقيّة فيُقارَن بـ`"false"` ويُقرأ «مقيَّد». وهو نفس صنف «نتيجةٌ عن
    سؤالٍ لم يُطرَح» الذي يُلاحَق في هذا الملفّ كلّه.
    """
    row = psql(
        "select "
        + "||'|'||".join(f"{column}::text" for column in _ROLE_CATALOGUE_COLUMNS)
        + f" from pg_roles where rolname='{app_role}'",
        database=database,
        role=owner,
    )
    if not row:
        raise SystemExit(f"✗ الدور المقيَّد '{app_role}' غير موجود — العزل غير قابل للقياس")
    values = row.split("|")
    if len(values) != len(ROLE_ATTRIBUTES):
        raise SystemExit(
            f"✗ صفُّ الدور '{app_role}' فيه {len(values)} حقلاً والعقد يقرأ "
            f"{len(ROLE_ATTRIBUTES)} — لا تُقسَم القيم على أسماء لا تقابلها. "
            "‏صفٌّ لا يُفهَم فشلٌ، لا قيمٌ جزئيّة تُقرأ حكماً."
        )
    unreadable = [
        f"{name}={value!r}"
        for name, value in zip(ROLE_ATTRIBUTES, values, strict=True)
        if value not in _BOOLEAN_TEXT
    ]
    if unreadable:
        raise SystemExit(
            f"✗ خصائص الدور '{app_role}' ليست منطقيّة: {' · '.join(unreadable)} — "
            "‏قيمةٌ لا تساوي `true` ولا `false` تمرّ على مقارنة «ليست true» فتُقرأ تقييداً "
            "وهي مجهولة. فشلٌ مغلق."
        )
    return dict(zip(ROLE_ATTRIBUTES, values, strict=True))


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


# ───────────────────────── ④ الدليل المكتوب — لا الملخّص وحده ─────────────────────────


def _git(*args: str) -> str:
    """‏`git` من داخل الشجرة المفحوصة — وغيابُه يُترَك `unavailable` لا يُخترَع."""
    try:
        proc = subprocess.run(  # noqa: S603
            ["git", "-C", str(ROOT), *args], capture_output=True, encoding="utf-8", check=False
        )
    except FileNotFoundError:
        return "unavailable"
    return proc.stdout.strip() if proc.returncode == 0 else "unavailable"


def evidence_document(
    *,
    verdict: str,
    counts: dict[str, int] | None,
    identity: dict[str, str] | None,
    role: dict[str, str] | None,
    drift: list[str],
    problems: list[str],
    app_role: str,
) -> dict:
    """الدليل يربط نفسه **بما اختُبِر**، ويقول مدى ما يُثبِته داخله.

    **‏`checkout_sha` و`checkout_tree` لا `github_sha` وحده:** في أحداث `pull_request`
    تعمل الوظيفة على **دمجٍ وهميّ** لا على رأس الفرع، فـ`GITHUB_SHA` يشير إلى شيءٍ آخر
    غير الشجرة التي جرى عليها القياس. فيُكتَب الثلاثة **منفصلة**: اختلافُ
    `github_sha` عن `checkout_sha` ليس عطلاً — هو **معلومة** تقول إنّ المقيس ليس ما
    أطلق التشغيل. والشجرة (`HEAD^{tree}`) تُكتَب معهما لأنّ الالتزام قد يُعاد كتابته
    بمحتوى الشجرة نفسه، والمحتوى هو ما قِيس.

    وحدُّ الصدق مكتوبٌ **داخل** الوثيقة لا في مراجعةٍ خارجها: من يقرأ الـJSON وحده
    يجب أن يعرف ما لا يُثبِته.
    """
    return {
        "$comment": (
            "دليل وظيفة PG المخصّصة — يُكتَب بحكمه قبل أيّ رمز خروج. "
            "لا يحوي مضيفاً ولا منفذاً ولا مستخدماً ولا كلمة مرور: خصائص مقيسة لا بيانات اعتماد."
        ),
        "schema_version": "1.0.0",
        "verdict": verdict,
        "gap": "FAKE-CONNECTION-ENFORCES-NOTHING-01",
        "binding": {
            "$comment": (
                "‏checkout_sha/checkout_tree هما ما قِيس فعلاً؛ github_sha ما أطلق التشغيل. "
                "اختلافهما في أحداث pull_request طبيعيّ (دمج وهميّ) وهو معلومة لا عطل."
            ),
            "checkout_sha": _git("rev-parse", "HEAD"),
            "checkout_tree": _git("rev-parse", "HEAD^{tree}"),
            "github_sha": os.environ.get("GITHUB_SHA", "unset"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID", "unset"),
        },
        "execution": counts,
        "server": identity,
        "direct_role_attributes": {
            "$comment": (
                "خصائص الدور المُسمّى نفسه من pg_roles. **لا يُثبَت** الإغلاق الانتقاليّ "
                "لعضويّات الأدوار (pg_auth_members) ولا أثر SET ROLE ولا صلاحيّات مورَّثة "
                "من دورٍ هو عضوٌ فيه. الاسم يقول مداه."
            ),
            "role": app_role,
            "attributes": role,
            "gating": list(_REJECT_IF_TRUE),
        },
        "schema_drift": drift,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", type=Path)
    ap.add_argument(
        "--evidence",
        type=Path,
        help="يكتب `live_pg_evidence.json` **بحكمه** قبل إعادة أيّ رمز خروج — "
        "فالدليل يوجد يوم يفشل الفحص، وهو أحوجُ ما نكون إليه",
    )
    ap.add_argument("--database", default=os.environ.get("SAHOOL_TEST_PGDATABASE", "sahool"))
    ap.add_argument("--owner", default=os.environ.get("SAHOOL_TEST_PGOWNER", "sahool_user"))
    ap.add_argument("--app-role", default=os.environ.get("SAHOOL_TEST_PGROLE", "sahool_app"))
    ap.add_argument("--min-executed", type=int, default=30)
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

    def _emit(verdict, counts, identity, role, drift, problems):
        """يكتب الدليل إن طُلِب — **قبل** أيّ `return` أو رفع.

        بلا هذا لا يوجد الدليل إلّا حين ينجح كلّ شيء، وهو المعنى المقلوب تماماً:
        الوثيقة تُطلَب يوم الفشل. ولذلك يُستدعى هذا من مسار الفشل المغلق أيضاً.
        """
        if a.evidence is None:
            return
        a.evidence.write_text(
            json.dumps(
                evidence_document(
                    verdict=verdict,
                    counts=counts,
                    identity=identity,
                    role=role,
                    drift=drift,
                    problems=problems,
                    app_role=a.app_role,
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    # الفشل المغلق (‏`psql` غائب · دورٌ غير موجود · صفٌّ مشوَّه) يُنهي بـ`SystemExit`.
    # فيُلتقَط هنا **كي يُكتَب الدليل بحكمه** ثمّ تُعاد الرسالة كما هي: عطلُ بيئةٍ
    # يبقى عطلَ بيئة، لكنّه يترك أثراً مقروءاً بدل صمتٍ يُقرأ «لم يُشغَّل شيء».
    try:
        counts = tally(a.junit)
        identity = server_identity(a.database, a.owner)
        role = role_properties(a.database, a.owner, a.app_role)
        drift = schema_drift(a.database, a.owner)
    except SystemExit as exit_:
        _emit("FAIL", None, None, None, [], [str(exit_.code)])
        raise

    print("─── أدلّة PG الحيّة — ملخّص مُشتقّ ───")
    print(
        "  التنفيذ: "
        f"collected={counts['collected']} executed={counts['executed']} "
        f"passed={counts['passed']} failed={counts['failed']} skipped={counts['skipped']}"
    )
    print(f"  الخادم: PostgreSQL {identity['postgresql']} · PostGIS {identity['postgis']}")
    print(
        f"  الدور «{a.app_role}»: " + " ".join(f"{name}={role[name]}" for name in ROLE_ATTRIBUTES)
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
    # **كلّ** خاصّيّة في `_REJECT_IF_TRUE` تحجب وحدها. والحلقة لا تُغني عن استقلال
    # الطفرات: نزعُ اسمٍ من تلك القائمة يُسقِط اختبار تلك الخاصّيّة **باسمها** لا غير.
    granted = [name for name in _REJECT_IF_TRUE if role[name] != "false"]
    if granted:
        problems.append(
            f"✗ الدور «{a.app_role}» غير مقيَّد ("
            + " ".join(f"{name}={role[name]}" for name in granted)
            + ") — كلّ ادّعاء عزلٍ تحته يمرّ مجّاناً، و`CREATEROLE` تبلغ بخطوتين "
            "ما مُنِعت منه بخطوة"
        )

    if problems:
        _emit("FAIL", counts, identity, role, drift, problems)
        print("\nlive_pg_evidence FAILED:")
        for p in problems:
            print(f"  {p}")
        return 1
    _emit("PASS", counts, identity, role, drift, [])
    print("live_pg_evidence_ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
