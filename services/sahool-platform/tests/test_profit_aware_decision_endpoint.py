"""اختبار نقطة /api/v1/crop-twin/decision/profit-aware — استدعاء مباشر.

يثبت: (أ) economic_state يُملأ من الخطّة+الأسعار (لا not_configured)؛ (ب) auto_policy
يختار السياسة من سياق التكلفة (بئر عميق ⇒ profit_max)؛ (ج) policy_decision يحمل
السبب؛ (د) غياب أسعار ⇒ economic_state partial/missing لا اختلاق؛ (هـ) calibrated=false.
بلا شبكة/قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.crop_twin import (
    ComposeForecastDay,
    ComposeManagement,
    ComposeSoil,
    ProfitAwareDecisionRequest,
    compose_profit_aware_decision,
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
    user_id="u-pa",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="ربح",
)


def _days(n):
    return [ComposeForecastDay(t_min_c=12.0, t_max_c=32.0, et0_mm=8.0, kc=1.1) for _ in range(n)]


def _req(**kw):
    base = dict(
        crop="wheat",
        stage="mid",
        forecast=_days(10),
        soil=ComposeSoil(texture="loam", root_depth_m=1.0),
        management=ComposeManagement(target_uptake_kg_ha=120.0, initial_depletion_mm=40.0),
    )
    base.update(kw)
    return ProfitAwareDecisionRequest(**base)


async def test_economic_state_filled():
    out = await compose_profit_aware_decision(
        req=_req(
            expected_yield_t_ha=5.0,
            crop_price_per_t=400.0,
            water_price_per_m3=0.05,
            energy_kwh_ha=500.0,
            energy_price_per_kwh=0.1,
            fertilizer_price_per_kg=0.8,
        ),
        user=_USER,
    )
    econ = out["economic_state"]
    assert econ["status"] in {"ok", "partial"}
    assert econ["gross_revenue"] == pytest.approx(2000.0)  # 5 × 400
    assert econ["water_cost"] is not None  # من ماء الخطّة × السعر
    assert "status" in econ and econ["status"] != "not_configured"


async def test_auto_policy_deep_well_resolves_profit_max():
    # بئر عميق + طاقة غالية ⇒ الاقتصاد يحلّ profit_max. مع أسعار ⇒ يُطبَّق فعلاً.
    out = await compose_profit_aware_decision(
        req=_req(
            auto_policy=True,
            water_source="deep_well",
            energy_cost="expensive",
            water_price_per_m3=0.2,
            yield_value_per_ha=2000.0,
        ),
        user=_USER,
    )
    assert out["policy_decision"]["auto"] is True
    assert out["policy_decision"]["resolved_policy"] == "profit_max"
    assert out["policy_decision"]["applied_policy"] == "profit_max"  # الأسعار متوفّرة
    assert any("PROFIT_MAX" in r for r in out["policy_decision"]["reasons_ar"])


async def test_auto_policy_profit_falls_back_without_prices():
    # صدق: الاقتصاد يحلّ profit_max لكن بلا أسعار ⇒ الخطّة تتراجع (applied ≠ resolved).
    out = await compose_profit_aware_decision(
        req=_req(auto_policy=True, water_source="deep_well", energy_cost="expensive"),
        user=_USER,
    )
    assert out["policy_decision"]["resolved_policy"] == "profit_max"
    assert out["policy_decision"]["applied_policy"] == "water_saving"


async def test_manual_policy_when_auto_off():
    out = await compose_profit_aware_decision(
        req=_req(policy="yield_max", auto_policy=False), user=_USER
    )
    assert out["policy_decision"]["auto"] is False
    assert out["policy_decision"]["applied_policy"] == "yield_max"


async def test_missing_prices_not_fabricated():
    out = await compose_profit_aware_decision(req=_req(), user=_USER)  # بلا أسعار
    econ = out["economic_state"]
    assert econ["gross_revenue"] is None
    assert "crop_price_per_t" in econ["missing_inputs"]
    assert econ["status"] in {"partial", "not_configured"}


async def test_flood_costs_more_water_than_drip():
    # الغمر (Ea 0.55) يسحب ماءً إجماليّاً أكبر من التقطير (Ea 0.90) لنفس الصافي ⇒ تكلفة ماء أعلى.
    common = dict(expected_yield_t_ha=5.0, crop_price_per_t=400.0, water_price_per_m3=0.1)
    flood = await compose_profit_aware_decision(
        req=_req(irrigation_method="flood", **common), user=_USER
    )
    drip = await compose_profit_aware_decision(
        req=_req(irrigation_method="drip", **common), user=_USER
    )
    assert flood["economic_state"]["water_cost"] is not None
    assert drip["economic_state"]["water_cost"] is not None
    assert flood["economic_state"]["water_cost"] > drip["economic_state"]["water_cost"]
    assert flood["gross_irrigation_mm"] > drip["gross_irrigation_mm"]


async def test_response_carries_gross_and_method():
    out = await compose_profit_aware_decision(req=_req(irrigation_method="drip"), user=_USER)
    assert out["irrigation_method"] == "drip"
    assert "gross_irrigation_mm" in out
    assert out["gross_irrigation_mm"] >= out["irrigation_plan"]["total_irrigation_mm"]


async def test_calibrated_false_and_unified_shape():
    out = await compose_profit_aware_decision(
        req=_req(expected_yield_t_ha=5.0, crop_price_per_t=400.0), user=_USER
    )
    assert out["calibrated"] is False
    assert set(out) >= {"irrigation", "fertilization", "risks", "economic_state", "policy_decision"}
