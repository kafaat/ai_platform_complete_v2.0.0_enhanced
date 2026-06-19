"""اختبار نقطة /api/v1/outcome/measure (routers/outcome) — استدعاء مباشر.

يثبت: (أ) شكل الاستجابة (metrics + success_flags + completeness)؛ (ب) تقييم صحيح
من المُخطَّط/المرصود؛ (ج) الناقص needs_data؛ (د) field_id يمرّ. بلا شبكة/قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.outcome import (
    OutcomeActual,
    OutcomePlanned,
    OutcomeRequest,
    measure_decision_outcome,
)
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-out",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="نتيجة",
)


def test_shape_and_evaluation():
    req = OutcomeRequest(
        field_id="f1",
        planned=OutcomePlanned(recommended_irrigation_mm=100.0, predicted_stress_days=3),
        actual=OutcomeActual(actual_irrigation_mm=100.0, observed_stress_days=1),
    )
    out = measure_decision_outcome(req=req, user=_USER)
    assert set(out) >= {"metrics", "success_flags", "data_completeness", "field_id"}
    assert out["field_id"] == "f1"
    by = {m["key"]: m for m in out["metrics"]}
    assert by["irrigation"]["status"] == "followed"
    assert by["stress"]["status"] == "better"
    assert "stress_better" in out["success_flags"]


def test_missing_actual_needs_data():
    req = OutcomeRequest(
        planned=OutcomePlanned(expected_yield_t_ha=5.0),
        actual=OutcomeActual(),
    )
    out = measure_decision_outcome(req=req, user=_USER)
    by = {m["key"]: m for m in out["metrics"]}
    assert by["yield"]["status"] == "needs_data"
    assert out["data_completeness"] == 0.0
