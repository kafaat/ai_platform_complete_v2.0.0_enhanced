"""اختبار نقطة /api/v1/irrigation-plan (routers/irrigation_plan) — استدعاء مباشر.

نختبر المعالِج مباشرةً (يربط soil_water ⇒ policy ⇒ MPC)، متفادين TestClient/المصادقة:
(أ) اشتقاق TAW من النسيج؛ (ب) تجاوزه بـ taw_mm مباشرةً؛ (ج) السياسة تنعكس في الخطّة؛
(د) ميزانيّة الموسم تُحترَم؛ (هـ) شكل الاستجابة (soil/plan). بلا شبكة/قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه (تفادي دورة استيراد)
import pytest
from api.routers.irrigation_plan import (
    ForecastDayModel,
    IrrigationPlanRequest,
    compute_irrigation_plan,
)
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-irr",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="مُخطِّط",
)


def _days(n, et0=10.0, kc=1.0, rain=0.0):
    return [ForecastDayModel(et0_mm=et0, kc=kc, rain_mm=rain) for _ in range(n)]


def test_derives_taw_from_texture():
    # loam = 175 مم/م × عمق 1.0 = 175.
    req = IrrigationPlanRequest(
        forecast=_days(6), soil_texture="loam", root_depth_m=1.0, raw_fraction=0.5
    )
    out = compute_irrigation_plan(req=req, user=_USER)
    assert out["soil"]["taw_mm"] == pytest.approx(175.0)
    assert out["taw_mm_used"] == pytest.approx(175.0)
    assert out["plan"]["taw_mm"] == pytest.approx(175.0)
    assert out["soil"]["calibrated"] is False


def test_explicit_taw_overrides_texture():
    req = IrrigationPlanRequest(
        forecast=_days(6), soil_texture="loam", root_depth_m=1.0, taw_mm=100.0, raw_fraction=0.5
    )
    out = compute_irrigation_plan(req=req, user=_USER)
    assert out["taw_mm_used"] == pytest.approx(100.0)
    assert out["plan"]["raw_mm"] == pytest.approx(50.0)  # 0.5 × 100


def test_policy_reflected_in_plan():
    req = IrrigationPlanRequest(
        forecast=_days(6), taw_mm=100.0, raw_fraction=0.5, policy="yield_max"
    )
    out = compute_irrigation_plan(req=req, user=_USER)
    assert out["plan"]["policy"] == "yield_max"
    ev = next(d for d in out["plan"]["days"] if d["irrigation_mm"] > 0)
    assert ev["dr_end_mm"] == pytest.approx(0.0)  # ملء كامل


def test_season_budget_respected():
    req = IrrigationPlanRequest(
        forecast=_days(30),
        taw_mm=100.0,
        raw_fraction=0.5,
        policy="yield_max",
        season_budget_mm=60.0,
    )
    out = compute_irrigation_plan(req=req, user=_USER)
    assert out["plan"]["total_irrigation_mm"] <= 60.0 + 1e-9
    assert out["plan"]["budget_exhausted"] is True


def test_profit_without_prices_falls_back_to_water_saving():
    req = IrrigationPlanRequest(forecast=_days(6), taw_mm=100.0, raw_fraction=0.5, policy="profit")
    out = compute_irrigation_plan(req=req, user=_USER)
    assert out["plan"]["policy"] == "water_saving"


def test_response_shape():
    req = IrrigationPlanRequest(forecast=_days(3), taw_mm=100.0, raw_fraction=0.5)
    out = compute_irrigation_plan(req=req, user=_USER)
    assert set(out) >= {"soil", "taw_mm_used", "quality", "plan"}
    assert set(out["plan"]) >= {"policy", "taw_mm", "raw_mm", "total_irrigation_mm", "days"}


def test_quality_block_structured():
    # taw_mm مُمرَّر مباشرةً ⇒ لا default_soil/estimated_root_depth ⇒ medium (uncalibrated).
    req = IrrigationPlanRequest(forecast=_days(3), taw_mm=100.0, raw_fraction=0.5)
    out = compute_irrigation_plan(req=req, user=_USER)
    q = out["quality"]
    assert set(q) >= {"confidence", "data_quality", "assumptions", "assumptions_ar"}
    assert "uncalibrated_model" in q["assumptions"]
    assert q["data_quality"] in {"low", "medium", "high"}
    assert q["data_quality"] != "high"  # غير معايَر ⇒ لا high أبداً


def test_quality_flags_default_soil_and_depth():
    # نسيج مجهول + بلا عمق + اشتقاق TAW (لا taw_mm) ⇒ افتراضات أكثر ⇒ ثقة أدنى.
    req = IrrigationPlanRequest(forecast=_days(3), soil_texture="moon_dust", raw_fraction=0.5)
    out = compute_irrigation_plan(req=req, user=_USER)
    assert "default_soil" in out["quality"]["assumptions"]
    assert "estimated_root_depth" in out["quality"]["assumptions"]


def test_quality_flags_policy_fallback():
    # profit بلا أسعار ⇒ تراجع ⇒ policy_fallback في الافتراضات.
    req = IrrigationPlanRequest(forecast=_days(3), taw_mm=100.0, raw_fraction=0.5, policy="profit")
    out = compute_irrigation_plan(req=req, user=_USER)
    assert out["plan"]["policy"] == "water_saving"
    assert "policy_fallback" in out["quality"]["assumptions"]
