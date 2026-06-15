"""SAHOOL — حارس انجراف أنواع العمليّات الزراعيّة (activity_type).

يوجد تعريفُ مجموعةِ أنواع العمليّات الزراعيّة في ثلاثة مواضع يجب أن تبقى
مصدراً واحداً للحقيقة (single source of truth):

1) قيد CHECK في قاعدة البيانات — ``migrations/v35_activities.sql``
   (``activity_type IN (...)``).
2) مجموعة التحقّق في بايثون — ``_ACTIVITY_TYPES`` في
   ``services/sahool-platform/api/main.py``.
3) (إضافيّ) اتّحاد الأنواع في الواجهة — ``ActivityType`` في
   ``frontend/src/services/api.ts``.

كشف التدقيق E نسخة منحرفة في mock (أُزيل لاحقاً). يمنع هذا الاختبار عودة
الانجراف بأن يُفشل CI عند اختلاف أيّ نسختين. النصوص تُقرأ كنصّ خام
(regex) دون استيراد ``main.py`` (تبعيّات ثقيلة) أو تشغيل أيّ قاعدة بيانات،
فيعمل ضمن وظيفة «اختبارات الوحدة».
"""

from __future__ import annotations

import os
import re

import pytest

# جذر المستودع = الأب المباشر لمجلّد tests_v9/.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SQL_PATH = os.path.join(_REPO_ROOT, "migrations", "v35_activities.sql")
_PY_PATH = os.path.join(_REPO_ROOT, "services", "sahool-platform", "api", "main.py")
_TS_PATH = os.path.join(_REPO_ROOT, "frontend", "src", "services", "api.ts")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _db_activity_types() -> set[str]:
    """يستخرج حرفيّات قيد ``CHECK (activity_type IN (...))`` من ملفّ الهجرة."""
    src = _read(_SQL_PATH)
    # نلتقط محتوى القوسين بعد activity_type ... IN — قد يمتدّ على عدّة أسطر.
    m = re.search(
        r"activity_type\s+IN\s*\((.*?)\)",
        src,
        re.IGNORECASE | re.DOTALL,
    )
    assert m, "تعذّر العثور على قيد CHECK لـactivity_type في v35_activities.sql"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def _python_activity_types() -> set[str]:
    """يستخرج حرفيّات مجموعة ``_ACTIVITY_TYPES = { ... }`` من نصّ main.py."""
    src = _read(_PY_PATH)
    m = re.search(r"_ACTIVITY_TYPES\s*=\s*\{(.*?)\}", src, re.DOTALL)
    assert m, "تعذّر العثور على _ACTIVITY_TYPES في main.py"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def _ts_activity_types() -> set[str] | None:
    """يستخرج حرفيّات اتّحاد ``ActivityType`` من api.ts، أو None عند التعذّر."""
    if not os.path.exists(_TS_PATH):
        return None
    src = _read(_TS_PATH)
    # type ActivityType = | 'planting' | 'fertilization' | ... ;
    m = re.search(r"ActivityType\s*=\s*(.*?);", src, re.DOTALL)
    if not m:
        return None
    literals = set(re.findall(r"'([^']+)'", m.group(1)))
    return literals or None


@pytest.mark.unit
def test_db_and_python_activity_types_match() -> None:
    """قيد قاعدة البيانات ومجموعة بايثون يجب أن يتطابقا حرفاً بحرف."""
    db = _db_activity_types()
    py = _python_activity_types()

    assert db, "مجموعة أنواع العمليّات في قاعدة البيانات فارغة (فشل التحليل)"
    assert py, "مجموعة _ACTIVITY_TYPES في بايثون فارغة (فشل التحليل)"

    only_db = db - py
    only_py = py - db
    assert db == py, (
        "انجراف في أنواع العمليّات الزراعيّة بين قاعدة البيانات وبايثون: "
        f"موجود في DB فقط = {sorted(only_db)} ؛ "
        f"موجود في Python فقط = {sorted(only_py)}"
    )


@pytest.mark.unit
def test_frontend_activity_types_match() -> None:
    """(إضافيّ) اتّحاد ActivityType في الواجهة يجب أن يطابق قاعدة البيانات."""
    ts = _ts_activity_types()
    if ts is None:
        pytest.skip("تعذّر تحديد ActivityType في الواجهة")

    db = _db_activity_types()
    only_db = db - ts
    only_ts = ts - db
    assert db == ts, (
        "انجراف في أنواع العمليّات الزراعيّة بين قاعدة البيانات والواجهة: "
        f"موجود في DB فقط = {sorted(only_db)} ؛ "
        f"موجود في TS فقط = {sorted(only_ts)}"
    )
