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


def test_the_shipped_tree_takes_no_database_evidence_from_the_guard_runbook():
    """`GUARD_CATALOGUE.md` نثرٌ مولَّد عن الحرّاس — وشُذرات DDL فيه أمثلةٌ لا مخطَّط.

    وهذا التأكيد **كان سيمسك الحادثتين معاً**: `IF` أوّلاً ثمّ `public` — بخلاف تأكيد
    الكلمات المفتاحيّة الذي أمسك الأولى وحدها لأنّ `public` ليست كلمة مفتاحيّة. مصدرُ
    دليلٍ عن قاعدة بيانات لا يكون ملفّاً يصف الحرّاس.
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
    offenders = [
        f"{capability['capability_id']} — {item['value']}"
        for capability in mapping["capabilities"]
        for item in capability.get("database", [])
        if "docs/runbooks/GUARD_CATALOGUE.md" in item.get("value", "")
    ]
    assert offenders == [], "أدلّة «قاعدة بيانات» مصدرها رَنبوك الحرّاس: " + " · ".join(offenders)
