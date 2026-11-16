"""W0-11 (``fields-4``/``crop-5``): تقدير العائد لا يقرأ الغياب صفرَ إجهاد.

**الفجوة:** ``LifecycleFeatures`` و``YieldEstimateRequest`` كانا يفترضان كلّ مدخلٍ صفراً، فطلبٌ
لا يحمل إلّا المحصول (هكذا يطلبه الجوّال بعد حفظ الحقل) يُقرأ «صفر إجهاد، صفر جفاف، صفر آفات»
ويُعيد العائد المستهدف كاملاً (القمح 2800 kg/ha) بثقة 55٪ — رقمٌ يبدو مقيساً وهو افتراض.
والمسار كان بلا ``require_permission`` ولا فحص أنّ الحقل يخصّ المستأجِر.

**ما يثبته هذا الملفّ (بلا قاعدة):**
  • غياب أدلّة حالة المحصول كلّها ⇒ ``unavailable_insufficient_evidence`` بلا رقم.
  • مدخلاتٌ لا تصف الحالة (مدّة، ريّات، أمطار) لا تكفي لرقم.
  • دليلٌ جزئيّ ⇒ تقدير مع ``missing_inputs``، ومستوى إجهاد مجهول لا «لا إجهاد».
  • النقطة: دورٌ بلا ``field:view`` ⇒ 403؛ تعذّر القاعدة ⇒ 503 لا تقدير (إغلاق عند الفشل).

مستأجِرٌ آخر ⇒ 404 يُقاس على قاعدة حيّة في
``tests_v9/test_yield_estimate_tenant_live_pg.py`` (RLS الحقيقيّ لا يُقلَّد هنا).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import api.main as api_main  # noqa: E402  (يُحمَّل أوّلاً لكسر الاستيراد الدائريّ)
from api.api_models import YieldEstimateRequest  # noqa: E402
from api.yield_heuristics import (  # noqa: E402
    CROP_TARGET_YIELDS,
    YIELD_CONDITION_EVIDENCE,
    LifecycleFeatures,
    StressLevel,
    detect_anomalies,
    estimate_yield,
)
from core.authorization import Permission, has_permission  # noqa: E402
from core.canonical_schemas import UserRole, UserSchema  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_TENANT = "00000000-0000-0000-0000-0000000000b1"
_ROUTE = "/api/v1/fields/fld-w011/yield-estimate"


# ─── الوحدة: الغياب مجهول ─────────────────────────────────────────────


def test_no_evidence_is_unavailable_not_full_target_yield():
    est = estimate_yield(LifecycleFeatures(field_id="f", crop="wheat"))
    assert est.estimated_yield_kg_ha is None, (
        f"بلا أدلّة يجب ألّا يُعاد رقم؛ أُعيد {est.estimated_yield_kg_ha} "
        f"(الهدف الكامل {CROP_TARGET_YIELDS['wheat']})"
    )
    assert est.yield_status == "unavailable_insufficient_evidence", est.yield_status
    assert est.yield_score is None, "لا نسبة من الهدف بلا تقدير"
    assert est.confidence == 0, "لا ثقة في تقديرٍ غير موجود"
    assert est.stress_level == StressLevel.UNKNOWN, "غياب الدليل ليس «لا إجهاد»"
    assert set(est.missing_inputs) == set(YIELD_CONDITION_EVIDENCE), est.missing_inputs
    assert "insufficient_evidence_no_yield_estimate" in est.warnings, est.warnings


def test_inputs_that_do_not_describe_crop_condition_are_not_enough():
    # مدّة نموّ طبيعيّة + ريّات + أمطار: لا شيء منها يقول إنّ المحصول بلا إجهاد أو آفات.
    est = estimate_yield(
        LifecycleFeatures(
            field_id="f",
            crop="wheat",
            days_in_growing=90,
            irrigation_count=6,
            rain_events=5,
            fertilizer_applications=2,
        )
    )
    assert est.estimated_yield_kg_ha is None, (
        f"مدخلات لا تصف الحالة أعطت رقماً: {est.estimated_yield_kg_ha}"
    )
    assert est.yield_status == "unavailable_insufficient_evidence", est.yield_status


def test_partial_evidence_estimates_and_names_the_unknown_inputs():
    est = estimate_yield(LifecycleFeatures(field_id="f", crop="wheat", pest_alerts=2))
    assert est.yield_status == "estimated", est.yield_status
    assert est.estimated_yield_kg_ha == round(2800 * 0.90, 0), est.estimated_yield_kg_ha
    assert set(est.missing_inputs) == {
        "moisture_stress_events",
        "drought_streak_days",
        "avg_ndvi_growing",
    }, est.missing_inputs
    assert est.stress_level == StressLevel.UNKNOWN, "الإجهاد المائي لم يُرصد ⇒ مستواه مجهول، لا NONE"
    assert "مدخلات مجهولة" in est.rationale_ar, est.rationale_ar


def test_unknown_moisture_does_not_earn_the_stress_free_irrigation_bonus():
    est = estimate_yield(
        LifecycleFeatures(field_id="f", crop="wheat", irrigation_count=6, pest_alerts=0)
    )
    assert not any("ري منتظم" in c for c in est.contributors), (
        f"مكافأة «ري منتظم بدون إجهاد» مُنحت والإجهاد مجهول: {est.contributors}"
    )
    assert est.yield_score == 1.0, est.yield_score


def test_observed_drought_alone_still_classifies_stress():
    est = estimate_yield(LifecycleFeatures(field_id="f", crop="wheat", drought_streak_days=22))
    assert est.stress_level == StressLevel.CRITICAL, est.stress_level


def test_explicit_zeros_are_observations_and_estimate_the_target():
    est = estimate_yield(
        LifecycleFeatures(
            field_id="f",
            crop="wheat",
            moisture_stress_events=0,
            drought_streak_days=0,
            pest_alerts=0,
        )
    )
    assert est.estimated_yield_kg_ha == CROP_TARGET_YIELDS["wheat"], est.estimated_yield_kg_ha
    assert est.stress_level == StressLevel.NONE, est.stress_level
    assert est.missing_inputs == ["avg_ndvi_growing"], est.missing_inputs


def test_anomalies_on_unknown_inputs_are_empty_not_a_crash():
    assert detect_anomalies(LifecycleFeatures(field_id="f", crop="wheat")) == [], (
        "المجهول لا يُكشَف منه شذوذ"
    )


# ─── نموذج الطلب: الغائب None لا صفر ──────────────────────────────────


def test_request_model_leaves_absent_inputs_unknown():
    req = YieldEstimateRequest(crop="wheat")
    for name in (
        "days_in_growing",
        "irrigation_count",
        "moisture_stress_events",
        "pest_alerts",
        "fertilizer_applications",
        "avg_ndvi_growing",
        "drought_streak_days",
        "rain_events",
    ):
        assert getattr(req, name) is None, f"{name} الغائب صار {getattr(req, name)!r} لا None"


def test_request_model_rejects_negative_counts():
    with pytest.raises(ValueError):
        YieldEstimateRequest(crop="wheat", pest_alerts=-3)


# ─── النقطة: صلاحية ثمّ مستأجِر، وإغلاق عند الفشل ─────────────────────


def _user(role: UserRole) -> UserSchema:
    return UserSchema(user_id="u-w011", tenant_id=_TENANT, role=role, name_ar="مختبِر")


def _client_as(monkeypatch, role: UserRole) -> TestClient:
    user = _user(role)
    monkeypatch.setitem(api_main.app.dependency_overrides, api_main.get_current_user, lambda: user)
    monkeypatch.setattr(api_main, "_DB_POOL", None)
    return TestClient(api_main.app, raise_server_exceptions=False)


def test_role_without_field_view_is_forbidden(monkeypatch):
    assert not has_permission(_user(UserRole.PLATFORM_ADMIN), Permission.FIELD_VIEW), (
        "افتراض الاختبار: platform_admin بلا field:view"
    )
    r = _client_as(monkeypatch, UserRole.PLATFORM_ADMIN).post(_ROUTE, json={"crop": "wheat"})
    assert r.status_code == 403, f"دور بلا field:view يجب أن يُرفض 403؛ أُعيد {r.status_code}"


def test_database_unavailable_fails_closed_without_an_estimate(monkeypatch):
    assert has_permission(_user(UserRole.VIEWER), Permission.FIELD_VIEW), (
        "افتراض: viewer يملك field:view"
    )
    r = _client_as(monkeypatch, UserRole.VIEWER).post(
        _ROUTE, json={"crop": "wheat", "moisture_stress_events": 0, "pest_alerts": 0}
    )
    assert r.status_code == 503, (
        f"ملكيّة الحقل لم يُتحقَّق منها ⇒ 503 لا تقدير؛ أُعيد {r.status_code}: {r.text[:200]}"
    )
    assert "estimated_yield_kg_ha" not in r.text, "لا رقم عائد في ردّ الفشل"
