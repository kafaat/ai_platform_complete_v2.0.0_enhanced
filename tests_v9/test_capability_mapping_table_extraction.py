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
