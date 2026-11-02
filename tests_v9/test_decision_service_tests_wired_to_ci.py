"""كلّ ملفّ اختبار في decision-service تُشغّله وظيفةٌ ما — لا انحدارَ «مُصلَحاً» بلا مُشغِّل.

تدقيق 2026-11-01 (Q4): ``tests/test_execution_outcome_receipt_gate.py`` و
``tests/test_model_promotion_guardrail_direction.py`` حرسا فجوتين أُعلِنتا مُصلَحتين في #1289،
ولم يُسمِّهما أيُّ workflow. اختبارات الخدمة خارج ``testpaths = tests_v9`` فلا يجمعها
``-m unit``؛ وظيفة *Decision Service Tests* تُشغّل ملفّاتها **بالاسم**، فملفٌّ جديد لا يُضاف
إليها يُقرأ تغطيةً وهو لا يعمل.

فحصٌ نصّيّ: اسمُ الملفّ بمساره النسبيّ (``tests/<name>``) يظهر في workflow ما.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SERVICE_TESTS = ROOT / "services" / "decision-service" / "tests"

# دَينٌ مُعلَن لا إعفاء: كلّ مدخل بكلفته المكتوبة، والمدخل البائت يُحمِرّ.
DECLARED_UNWIRED: dict[str, str] = {
    "test_eligibility_assessment_live_pg.py": (
        "دليلٌ حيّ على مكدّس المالك (psql بالدور sahool_user على قاعدة sahool + هجرات المنصّة)؛ "
        "قاعدة الوظيفة decision_test لا تحمل جدول decision_eligibility_assessments"
    ),
}


def _workflow_text() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8") for p in sorted((ROOT / ".github/workflows").glob("*.y*ml"))
    )


def test_every_decision_service_test_file_is_named_by_a_workflow():
    text = _workflow_text()
    unwired = sorted(
        p.name
        for p in SERVICE_TESTS.glob("test_*.py")
        if f"tests/{p.name}" not in text and p.name not in DECLARED_UNWIRED
    )
    assert not unwired, (
        f"ملفّات اختبار decision-service لا يُشغّلها أيّ workflow: {unwired}. "
        "أضفها إلى وظيفة Decision Service Tests في .github/workflows/ci.yml."
    )


def test_the_unwired_inventory_has_no_stale_entry():
    text = _workflow_text()
    stale = sorted(
        name
        for name in DECLARED_UNWIRED
        if not (SERVICE_TESTS / name).is_file() or f"tests/{name}" in text
    )
    assert not stale, f"مدخلٌ لم يعد دَيناً (حُذِف الملفّ أو صار موصولاً) — يُحذَف: {stale}"
