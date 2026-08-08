"""استخراج أسماء الجداول في `capability_mapping_engine` — كلمةٌ مفتاحيّة ليست جدولاً.

`TABLE_RE` هو مصدر بُعد **`database`** في `capability_mapping.json`، ومنه تُشتقّ
`coverage_dimensions` ثمّ مصفوفة الأدلّة ثمّ مصفوفة الإدارة. فمدخلٌ كاذب واحد لا يبقى
في مكانه: يرفع بُعد تغطية قدرةٍ ويُغيّر رقماً حوكميّاً.

**والعطل المقيس:** `(?:\\s+if\\s+not\\s+exists)?` كانت اختياريّةً قابلة للتراجع. عند
`CREATE TABLE IF NOT EXISTS + DROP POLICY…` — وهو **تعليقٌ عربيّ في هجرة**، لا DDL —
يفشل ما بعد الكلمات فيتراجع المُطابِق إلى صفر تكرار ويلتقط `IF` اسمَ جدول. أنتج ذلك
**١٢ مدخلاً كاذباً** سابقةً لأيّ من شريحتَي الحارس، مصادرها تعليقات وملفّات اختبار؛
وصارت **١٦** حين وُلِّد نصّ الطفرة الجديدة في `GUARD_CATALOGUE.md`.

**ولماذا اختبارٌ هنا وقد كانت الدالّة بلا اختبار أصلاً:** لأنّ الخضرة السابقة لم تكن
شهادةً — لم يكن هناك من يسأل. والصمت الذي يُقرأ «لا جدول هنا» كان يعني «التقطتُ كلمةً
وسمّيتها جدولاً»، وهو الوجه المقابل للعطل نفسه: نتيجةٌ عن سؤالٍ لم يُطرَح.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ENGINE = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "capability_mapping_engine.py"


def _engine():
    spec = importlib.util.spec_from_file_location("capability_mapping_engine", _ENGINE)
    #: **قبل `module_from_spec` لا بعده.** `spec_from_file_location` يُرجِع `None` لمسارٍ
    #: غير قابل للتحميل — ملفٌّ نُقِل أو أُعيدت تسميته — فيرمي `module_from_spec` خطأً
    #: خاماً عن `None`، ويُقرأ خطأً برمجيّاً في الاختبار بدل «الملفّ ليس هناك».
    assert spec is not None and spec.loader is not None, f"تعذّر تحميل {_ENGINE} — صحّح المسار"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tables(text: str) -> list[str]:
    return [item.split(" @ ")[0] for item in _engine().db_items("sample.sql", text)]


@pytest.mark.parametrize(
    "text,label",
    [
        (
            "-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).",
            "التعليق الحرفيّ في migrations/v79_outcome_record.sql:16",
        ),
        (
            "-- idempotent بالكامل (ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS /",
            "التعليق الحرفيّ في migrations/v58_field_boundary_quality.sql:9",
        ),
        ("ALTER TABLE IF EXISTS ONLY <t> ADD COLUMN decision_eligible boolean;", "اسمٌ نائب `<t>`"),
    ],
)
def test_a_keyword_is_never_reported_as_a_table(text, label):
    """لا اسم جدول حيث لا جدول — والتراجع لا يُنتج `IF`."""
    assert _tables(text) == [], label


@pytest.mark.parametrize(
    "text,expected,label",
    [
        ("CREATE TABLE decision_snapshots (", "decision_snapshots", "الصيغة العارية"),
        (
            "CREATE TABLE IF NOT EXISTS decision_snapshots (",
            "decision_snapshots",
            "`IF NOT EXISTS`",
        ),
        ("ALTER TABLE ONLY decision_snapshots ADD", "decision_snapshots", "`ONLY`"),
        (
            "ALTER TABLE IF EXISTS ONLY public.decision_snapshots ADD COLUMN x int",
            "decision_snapshots",
            "المركّبة القانونيّة مع بادئة المخطَّط",
        ),
        ('ALTER TABLE "decision_snapshots" ADD', "decision_snapshots", "الاسم المقتبَس"),
    ],
)
def test_every_legal_ddl_prefix_still_yields_the_table(text, expected, label):
    """إسكاتُ الكاذب يجب ألّا يُسكِت الصادق — قواعد PostgreSQL كلّها ما تزال مقروءة."""
    assert _tables(text) == [expected], label


def test_the_shipped_tree_carries_no_keyword_named_table():
    """المخرَج المُلتزَم نفسه — لا مصنوعة تدّعي جدولاً اسمه كلمةٌ مفتاحيّة.

    الاختبارات أعلاه تقيس الدالّة؛ وهذا يقيس **ما شُحِن فعلاً**. الفارق بينهما هو ما
    أفلت سابقاً: دالّةٌ تُصلَح ومصنوعةٌ لا يُعاد توليدها تبقى تُقرأ على أنّها صادقة.
    """
    import json

    mapping = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "capability-registry"
            / "generated"
            / "mapping"
            / "capability_mapping.json"
        ).read_text(encoding="utf-8")
    )
    keywords = {"if", "not", "exists", "only", "table"}
    offenders = [
        f"{capability['capability_id']} — {item['value']}"
        for capability in mapping["capabilities"]
        for item in capability.get("database", [])
        if item.get("value", "").split(" @ ")[0].lower() in keywords
    ]
    assert offenders == [], "أدلّة «قاعدة بيانات» اسمها كلمة مفتاحيّة: " + " · ".join(offenders)


@pytest.mark.parametrize(
    "text,expected,label",
    [
        (
            'CREATE TABLE public . "decision_vegetation_snapshots" (\n  "decision_eligible" boolean\n);',
            "decision_vegetation_snapshots",
            "المركّبة: مخطَّط بمسافات + جدول مقتبس",
        ),
        (
            'ALTER TABLE IF EXISTS ONLY public . "decision_vegetation_snapshots" *\n'
            '  ADD COLUMN IF NOT EXISTS "policy_version" text;',
            "decision_vegetation_snapshots",
            "المركّبة الكاملة مع النجمة",
        ),
        ("ALTER TABLE public . orders ADD COLUMN x int", "orders", "مسافات حول النقطة بلا اقتباس"),
        ('CREATE TABLE "public" . "orders" (', "orders", "المخطَّط والجدول مقتبسان"),
    ],
)
def test_a_schema_qualifier_is_never_reported_as_the_table_composite(text, expected, label):
    """الصيغ الكاملة — انظر الشقيقة أدناه للشُّذرة الناقصة."""
    assert _tables(text) == [expected], label


@pytest.mark.parametrize(
    "text,label",
    [
        ('ALTER TABLE "public" .', "الشُّذرة الناقصة — نقطةٌ خلف اقتباس بلا اسمٍ بعدها"),
        ('CREATE TABLE "public" .', "الشُّذرة الناقصة في `CREATE`"),
        ('ALTER TABLE "public"  .  ', "نفسها بمسافات"),
    ],
)
def test_a_truncated_qualifier_yields_nothing(text, label):
    """**المُصنِّف يقرأ نثراً وشُذرات غير مكتملة، لا ملفّات SQL وحدها.**

    ولذلك تُضمَّن علامة الاقتباس **داخل** النظرة اللاحقة: `(?!["]?\\s*\\.)`. فالنظرة
    العارية `(?!\\s*\\.)` ترى `"` لا `.` عند `ALTER TABLE "public" .` — فتمرّ ويُلتقَط
    `public` مُؤهِّلاً بوصفه مُؤهَّلاً. **نفس العطل، في الشُّذرة الناقصة بدل الكاملة**:
    سطرٌ مقطوع في نثرٍ يكفي لإنتاج ادّعاء «جدول» لا وجود له.
    """
    assert _tables(text) == [], label


@pytest.mark.parametrize(
    "text,expected,label",
    [
        ("CREATE TABLE public . orders (", "orders", "لا تُسكِت الصادق"),
        ('ALTER TABLE "public".orders ADD', "orders", "بلا مسافات"),
    ],
)
def test_a_schema_qualifier_is_never_reported_as_the_table(text, expected, label):
    """ما قبل النقطة مخطَّطٌ لا جدول — والتراجع لا يُنتِج `public`.

    بادئة المخطَّط كانت اختياريّةً **قابلة للتراجع**: عند `public . "<t>"` يفشل الالتقاط
    بعد الاقتباس فيتراجع المُطابِق ويأخذ **`public`**. أربعة مداخل كاذبة، ورقمٌ حوكميّ
    (`capabilities_multidimensional`) تحرّك من ٤٨ إلى ٤٩ عليها.
    """
    assert _tables(text) == [expected], label


@pytest.mark.parametrize(
    "text,label",
    [
        ("CREATE TABLE public (id int);", "`public` جدولاً غير مؤهَّل"),
        ("ALTER TABLE public ADD COLUMN x int;", "`public` جدولاً في ALTER"),
    ],
)
def test_public_unqualified_is_still_a_legitimate_table_name(text, label):
    """**العلاج بنيويّ لا حظرَ كلمة.**

    `public` اسمُ جدولٍ قانونيّ تماماً حين تَرِد غير مؤهَّلة. حظرُها بالاسم كان سيُنتِج
    العمى المقابل: كاشفٌ يرفض حقيقةً ليتجنّب كذبة. المرفوض هو **الموضع** — اسمٌ تتبعه
    نقطة — لا الاسم نفسه.
    """
    assert _tables(text) == ["public"], label


def test_the_guard_runbook_yields_no_keyword_or_qualifier_named_table():
    """الحادثتان المقيستان بعينهما — `if` و`public` من `GUARD_CATALOGUE.md`.

    **والتأكيد ضيّقٌ عمداً:** لا يقول «لا دليل قاعدة بيانات من هذا الملفّ مطلقاً»، لأنّ
    استبعاد ملفٍّ كاملاً حكمٌ يحتاج تحكيماً لم يجرِ — وقد يذكر الرَّنبوك يوماً اسم جدولٍ
    حقيقيّ بحقّ. المحروس هو **الصنف المُثبَت**: كلمةٌ مفتاحيّة أو مُؤهِّل مخطَّط يُسمَّى
    جدولاً. أمّا صحّة تحليل التأهيل نفسه فتُثبِتها اختبارات الوحدة المركّبة أعلاه، لا
    تأكيدٌ على مصنوعة.
    """
    import json

    mapping = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "capability-registry"
            / "generated"
            / "mapping"
            / "capability_mapping.json"
        ).read_text(encoding="utf-8")
    )
    banned = {"if", "not", "exists", "only", "table", "public"}
    offenders = [
        f"{capability['capability_id']} — {item['value']}"
        for capability in mapping["capabilities"]
        for item in capability.get("database", [])
        if "docs/runbooks/GUARD_CATALOGUE.md" in item.get("value", "")
        and item["value"].split(" @ ")[0].lower() in banned
    ]
    assert offenders == [], "كلمةٌ مفتاحيّة أو مُؤهِّل يُسمَّى جدولاً في الرَّنبوك: " + " · ".join(offenders)


# ─────────────────────────────────────────────────────────────────────────────
# عقد المؤقّت والدائم — بُعد `database` يقيس **العلاقات الدائمة**
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,label",
    [
        ("CREATE TEMP TABLE staging (id int);", "`TEMP`"),
        ("CREATE TEMPORARY TABLE staging (id int);", "`TEMPORARY`"),
        ("CREATE GLOBAL TEMP TABLE staging (id int);", "`GLOBAL TEMP`"),
        ("CREATE GLOBAL TEMPORARY TABLE staging (id int);", "`GLOBAL TEMPORARY`"),
        ("CREATE LOCAL TEMP TABLE staging (id int);", "`LOCAL TEMP`"),
        ("CREATE LOCAL TEMPORARY TABLE staging (id int);", "`LOCAL TEMPORARY`"),
        ("create temp table if not exists staging (id int);", "`TEMP` مع `IF NOT EXISTS`"),
    ],
)
def test_a_temporary_table_is_never_a_database_relation(text, label):
    """**استبعاد المؤقّت عقدٌ الآن، وكان أثراً جانبيّاً.**

    بُعد `database` يُقرأ على أنّه «العلاقات التي تعيش في هذه المنصّة». والجدول المؤقّت
    يعيش داخل جلسةٍ واحدة، في مخطَّط `pg_temp_N`، ويختفي بانتهائها — فلا ملكيّة ولا
    هجرة ولا نَسَب أدلّة. إحصاؤه يرفع بُعد تغطية قدرةٍ على علاقةٍ لا توجد بعد `COMMIT`.

    **وهذا التأكيد كان يمرّ قبل الإصلاح — بالمصادفة لا بالعقد.** النمط السابق طلب
    `TABLE` **مباشرةً** بعد `CREATE`، فسقط كلّ ما بينهما مُعدِّلٌ أيّاً كان: المؤقّت
    والدائم معاً. أي أنّ الصمت عن `TEMP` كان الوجه الآخر للعمى عن `UNLOGGED`، لا حكماً
    عليه. فيوم يُدعَم أيّ مُعدِّل — وقد دُعِم `UNLOGGED` في هذه الشريحة نفسها — يعود
    المؤقّت مع الدائم **صامتاً**. هذا التأكيد هو ما يمنع ذلك: يحمرّ إن اتّسع المُعدِّل
    ليبتلع `TEMP`.
    """
    assert _tables(text) == [], label


@pytest.mark.parametrize(
    "text,expected,label",
    [
        ("CREATE UNLOGGED TABLE fast_cache (id int);", "fast_cache", "الصيغة العارية"),
        (
            "CREATE UNLOGGED TABLE IF NOT EXISTS fast_cache (id int);",
            "fast_cache",
            "مع `IF NOT EXISTS`",
        ),
        (
            "create unlogged table public.fast_cache (id int);",
            "fast_cache",
            "مع بادئة المخطَّط",
        ),
    ],
)
def test_an_unlogged_table_is_a_permanent_relation(text, expected, label):
    """**`UNLOGGED` دائم — وكان يسقط: عمًى مقيس لا افتراضيّ.**

    الجدول غير المُسجَّل يفقد **بياناته** عند انهيارٍ غير نظيف، لكنّ **تعريفه** في
    الكتالوج: له مالك وقيود وفهارس وهجرة تُنشئه، ويبقى بعد إعادة التشغيل جدولاً فارغاً
    لا معدوماً. فهو علاقةٌ دائمة بكلّ ما يعنيه بُعد `database`، ومع ذلك كان النمط
    السابق يُعطي `[]` عليه — **مقيس على `68cc8cfb7` قبل هذه الشريحة**.

    وهذا هو الشقّ الموجب من العقد: التأكيد الأوّل يمنع دخول المؤقّت، وهذا يمنع أن
    يُشترى ذلك المنع بإسقاط الدائم.
    """
    assert _tables(text) == [expected], label


@pytest.mark.parametrize(
    "text,label",
    [
        ("CREATE FOREIGN TABLE films_remote (id int) SERVER f;", "جدول أجنبيّ"),
        ("CREATE MATERIALIZED VIEW ndvi_daily AS SELECT 1;", "مشهد مُجسَّد"),
        ("SELECT * INTO archived_orders FROM orders;", "‏`SELECT … INTO`"),
        ("CREATE SEQUENCE order_seq;", "متتالية"),
    ],
)
def test_the_declared_out_of_scope_forms_are_silent(text, label):
    """**حدّ النطاق مقيس ومُثبَّت — والصمت ليس حكماً بالغياب.**

    نطاق هذا الماسح **الجداول المحلّيّة الدائمة** المُعلَنة بـ`CREATE TABLE` أو
    `ALTER TABLE`. وما دونها لا يراه: الجداول الأجنبيّة · المشاهد المُجسَّدة ·
    `SELECT … INTO` · المتتاليات. فخلوّ بُعد `database` من علاقةٍ **لا يُثبِت أنّها غير
    موجودة**؛ يُثبِت أنّها ليست من الصنف الذي يُسأل عنه.

    **ولماذا يُثبَّت الحدّ باختبارٍ لا بفقرةٍ وحدها:** لأنّ الفقرة لا تحمرّ. وتوسيعُ
    النطاق يوماً عملٌ مشروع — لكنّه يجب أن يكون **قراراً**: يحمرّ هذا التأكيد فتُحدَّث
    قائمتُه وتُحدَّث معها فقرة النطاق في `capability_mapping_engine.py`، بدل أن يتّسع
    الرقم الحوكميّ بلا من يلاحظ أنّ معناه تغيّر.
    """
    assert _tables(text) == [], (
        f"{label}: إن كان التوسيع مقصوداً فحدِّث هذه القائمة **وفقرة النطاق** في "
        "scripts/ci/capability_mapping_engine.py — لا هذه وحدها"
    )
