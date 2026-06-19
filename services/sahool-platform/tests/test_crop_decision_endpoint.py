"""اختبار نقطة /api/v1/crop-twin/decision (routers/crop_twin) — استدعاء مباشر.

نختبر المعالِج مباشرةً (crop_twin + خطّة الريّ + unified_decision): (أ) الشكل الموحّد
(ريّ+تسميد+مخاطر+ثقة)؛ (ب) economic_state محجوز؛ (ج) السياسة تنعكس في الخطّة؛ (د)
أعلام موحّدة؛ (هـ) calibrated=false. بلا شبكة/قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.crop_twin import (
    ComposeForecastDay,
    ComposeManagement,
    ComposeSoil,
    CropDecisionRequest,
    compose_crop_decision,
)
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-dec",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="قرار",
)


def _days(n):
    return [ComposeForecastDay(t_min_c=10.0, t_max_c=30.0, et0_mm=8.0, kc=1.1) for _ in range(n)]


def _req(**kw):
    base = dict(
        crop="wheat",
        stage="mid",
        forecast=_days(10),
        soil=ComposeSoil(texture="loam", root_depth_m=1.0),
        management=ComposeManagement(target_uptake_kg_ha=120.0, initial_depletion_mm=40.0),
    )
    base.update(kw)
    return CropDecisionRequest(**base)


def test_unified_shape():
    out = compose_crop_decision(req=_req(), user=_USER)
    assert set(out) >= {
        "irrigation",
        "fertilization",
        "risks",
        "confidence",
        "economic_state",
        "stress_flags",
        "phenology",
        "water_state",
        "nutrient_state",
        "irrigation_plan",
    }


def test_economic_state_reserved():
    out = compose_crop_decision(req=_req(), user=_USER)
    assert out["economic_state"]["status"] == "not_configured"
    assert "crop_price" in out["economic_state"]["required_inputs"]


def test_policy_reflected():
    out = compose_crop_decision(req=_req(policy="yield_max"), user=_USER)
    assert out["irrigation"]["policy"] == "yield_max"
    assert out["irrigation_plan"]["policy"] == "yield_max"


def test_fertilization_decision_present():
    out = compose_crop_decision(req=_req(), user=_USER)
    assert "remaining_need_kg_ha" in out["fertilization"]
    assert out["fertilization"]["uptake_to_date_kg_ha"] >= 0.0


def test_calibrated_false_and_confidence():
    out = compose_crop_decision(req=_req(), user=_USER)
    assert out["calibrated"] is False
    assert 0.0 <= out["confidence"] <= 1.0
    assert out["data_quality"] != "high"  # غير معايَر


def test_water_deficit_flag():
    # استنزاف ابتدائيّ مرتفع + ETc ⇒ عجز مائيّ.
    out = compose_crop_decision(
        req=_req(forecast=_days(4), management=ComposeManagement(initial_depletion_mm=80.0)),
        user=_USER,
    )
    codes = {f["code"] for f in out["stress_flags"]}
    assert "water_deficit" in codes
