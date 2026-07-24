"""حارس P1-8 — وسم سبب evidence-only في ردّ الوكيل الزراعيّ.

التدقيق: فشل التوليد كان يُبتلَع ويبقى ``mode="evidence_only"`` بلا تمييز عن التصميم. هذا الحارس
الساكن (نمط اختبارات ai_evidence_runtime في tests_v9) يؤكّد أنّ الردّ صار يميّز أربع حالات صريحة
ويُظهرها في الاستجابة — حتى لا يبدو الجواب المُدهوَر (فشل مزوّد) كأنّه evidence-only بالتصميم.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "services" / "ai_agronomist" / "ai_evidence_runtime.py"


def _src() -> str:
    return SRC.read_text(encoding="utf-8")


def test_generation_status_four_states_defined():
    s = _src()
    for state in (
        '"not_attempted"',  # ليس chat / غير مسموح للمستأجِر
        '"blocked_by_policy"',  # حاصرته بوّابة السياسة (fail-closed بالتصميم)
        '"attempted_failed"',  # حُوول التوليد وفشل (مُدهوَر) — الحالة الحرِجة
        '"succeeded"',  # نجح التوليد
    ):
        assert state in s, f"حالة توليد ناقصة: {state}"


def test_attempted_failed_set_on_none_result():
    s = _src()
    # يُضبَط attempted_failed حين يعود التوليد None **بعد المحاولة** (لا يُخلَط بالحصر/عدم المحاولة).
    assert 'generation_status = "succeeded" if gen is not None else "attempted_failed"' in s


def test_generation_status_surfaced_in_response():
    s = _src()
    assert '"generation_status": generation_status' in s
    # الافتراض الصادق: لم يُحاوَل (لا يُدَّعى نجاح ضمنيّ).
    assert 'generation_status = "not_attempted"' in s
