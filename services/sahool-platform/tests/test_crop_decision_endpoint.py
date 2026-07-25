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
    crop_decision_endpoint,
)
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _patch_engine_gdd(monkeypatch):
    """WS-C.1c Zero-Legacy: مسار compose يجلب GDD من المحرّك (async) — نُبدِّله بمزيّف في الوحدة."""

    async def _fake_gdd(*, daily_t_min, daily_t_max, base_c, upper_cutoff_c, method, **_kw):
        daily = []
        for mn, mx in zip(daily_t_min, daily_t_max, strict=False):
            tmax = max(min(mx, upper_cutoff_c) if upper_cutoff_c is not None else mx, base_c)
            tmin = max(mn, base_c)
            daily.append(round(max(0.0, (tmax + tmin) / 2.0 - base_c), 3))
        return {
            "product": "gdd",
            "calculation_version": "gdd/daily/1.0.0",
            "daily_gdd": daily,
            "accumulated_gdd": round(sum(daily), 3),
            "thresholds_used": {
                "base_c": base_c,
                "upper_cutoff_c": upper_cutoff_c,
                "method": method,
            },
            "valid_period": {"days": len(daily)},
            "limitations": [],
        }

    import api.routers.crop_twin as mod

    monkeypatch.setattr(mod, "get_gdd_product", _fake_gdd)


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


async def test_unified_shape():
    out = await compose_crop_decision(req=_req(), user=_USER)
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


async def test_economic_state_reserved():
    out = await compose_crop_decision(req=_req(), user=_USER)
    assert out["economic_state"]["status"] == "not_configured"
    assert "crop_price" in out["economic_state"]["required_inputs"]


async def test_policy_reflected():
    out = await compose_crop_decision(req=_req(policy="yield_max"), user=_USER)
    assert out["irrigation"]["policy"] == "yield_max"
    assert out["irrigation_plan"]["policy"] == "yield_max"


async def test_fertilization_decision_present():
    out = await compose_crop_decision(req=_req(), user=_USER)
    assert "remaining_need_kg_ha" in out["fertilization"]
    assert out["fertilization"]["uptake_to_date_kg_ha"] >= 0.0


async def test_calibrated_false_and_confidence():
    out = await compose_crop_decision(req=_req(), user=_USER)
    assert out["calibrated"] is False
    assert 0.0 <= out["confidence"] <= 1.0
    assert out["data_quality"] != "high"  # غير معايَر


async def test_water_deficit_flag():
    # استنزاف ابتدائيّ مرتفع + ETc ⇒ عجز مائيّ.
    out = await compose_crop_decision(
        req=_req(forecast=_days(4), management=ComposeManagement(initial_depletion_mm=80.0)),
        user=_USER,
    )
    codes = {f["code"] for f in out["stress_flags"]}
    assert "water_deficit" in codes


async def test_endpoint_is_permanent_preview_even_with_flag_on(monkeypatch):
    """DECISION-CENTER-UNIFY-01 (الشريحة 2): النقطة معاينةٌ **دائمةٌ** — لا كتابة آمِرة موازية
    حتى لو ضُبِطت الراية القديمة (أُزيل باب الكتابة المباشرة، لا مجرّد إطفاء افتراضيّ)."""
    monkeypatch.setenv("CROP_TWIN_DIRECT_DECISION_ENABLED", "1")
    out = await crop_decision_endpoint(req=_req(), user=_USER)
    assert out["preview_only"] is True
    assert out["persisted"] is False
