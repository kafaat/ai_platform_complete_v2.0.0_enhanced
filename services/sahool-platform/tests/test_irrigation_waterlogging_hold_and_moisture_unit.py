"""توصية الريّ: حجز الغدق من تقييم صرف soil-service + هويّة وحدة رطوبة التربة.

(أ) خطر الغدق لم يكن يحجب الريّ قطّ: الصرف كان نصّاً حرّاً يُستعمل للغسل فقط، ومسار الحقل
لا يمرّره. الآن ``waterlogging`` مُدخَلٌ نقيّ: خطرٌ ≥ العتبة أو حاجة صرف تحت سطحيّ/مركّب ⇒
``should_irrigate=False`` و``trigger_reason="waterlogging_risk"`` وغسل = 0؛ وغيابُ التقييم
لا يحجب لكنّه يُعلَن ``drainage_unknown``.

(ب) نسبة رطوبة عارية كانت تُقرأ «ماءً متاحاً» افتراضاً فترفع الإلحاح. الآن تحكمها
``shared.contracts.soil.moisture_policy`` (SOIL-MOISTURE-ELIGIBILITY-01).
"""

from datetime import UTC, datetime, timedelta

import pytest
from api.irrigation_models import IrrigationRecommendationRequest
from api.irrigation_recommendation_policy import (
    HOLD_WATERLOGGING_RISK,
    LIMIT_DRAINAGE_UNKNOWN,
    WATERLOGGING_HOLD_RISK,
    recommend_irrigation,
    waterlogging_blocks_irrigation,
)
from api.soil_hydraulic_client import parse_drainage_assessment

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

# ملوحة + بيانات غسل كاملة + صرف سريع ⇒ غسلٌ موجب لولا الغدق.
_LEACHING_READY = dict(
    soil_ece=6.0,
    soil_ec_age_days=30,
    crop_salt_tolerance_ece=6.0,
    water_ec=1.5,
    irrigation_efficiency=0.85,
    drainage="fast",
)
# TAW=100 · p=0.5 ⇒ RAW=50؛ Dr=60 فوق عتبة الإطلاق (water_saving).
_OVER_TRIGGER = dict(depletion_mm=60.0, taw_mm=100.0, raw_fraction=0.5, policy="water_saving")


def _rec(**over) -> dict:
    kw = dict(
        et0_mm=6.0,
        crop="wheat",
        stage="mid",
        rain_recent_mm=0.0,
        forecast_rain_mm=0.0,
        force_net_only=False,
        now=_NOW,
    )
    kw.update(over)
    return recommend_irrigation(**kw)


# ── (أ) الغدق ─────────────────────────────────────────────────────────


def test_high_waterlogging_risk_holds_irrigation_over_trigger_and_blocks_leaching():
    free = _rec(**_OVER_TRIGGER, **_LEACHING_READY, waterlogging={"risk": 0.1})
    assert free["should_irrigate"] is True
    assert free["salinity_leaching_mm"] > 0  # الشاهد الموجب: الغسل كان سيُضاف

    held = _rec(**_OVER_TRIGGER, **_LEACHING_READY, waterlogging={"risk": 0.75})
    assert held["should_irrigate"] is False
    assert held["trigger_reason"] == HOLD_WATERLOGGING_RISK
    assert held["waterlogging_hold"] is True
    assert held["salinity_leaching_mm"] == 0.0
    assert held["target_refill_mm"] is None
    assert held["urgency"] == "none"
    assert LIMIT_DRAINAGE_UNKNOWN not in held["limitations"]


@pytest.mark.parametrize("need", ["subsurface", "combined", "Subsurface "])
def test_subsurface_or_combined_drainage_need_holds_even_at_low_risk(need):
    out = _rec(**_OVER_TRIGGER, waterlogging={"risk": 0.2, "drainage_need": need})
    assert out["should_irrigate"] is False
    assert out["trigger_reason"] == HOLD_WATERLOGGING_RISK


def test_hold_overrides_critical_water_stress_urgency_and_forecast_hold():
    out = _rec(
        **_OVER_TRIGGER,
        forecast_rain_mm=20.0,
        water_stress_class="critical",
        waterlogging={"risk": WATERLOGGING_HOLD_RISK},  # العتبة نفسها تحجب (≥)
    )
    assert out["should_irrigate"] is False
    assert out["trigger_reason"] == HOLD_WATERLOGGING_RISK
    assert out["urgency"] == "none"


def test_hold_applies_without_depletion_data():
    out = _rec(waterlogging={"drainage_need": "combined"})
    assert out["should_irrigate"] is False
    assert out["trigger_reason"] == HOLD_WATERLOGGING_RISK


@pytest.mark.parametrize(
    "waterlogging",
    [{"risk": 0.59, "drainage_need": "monitor"}, {"drainage_need": "surface"}, {"risk": 0.0}],
)
def test_assessed_low_risk_does_not_hold_or_add_a_limitation(waterlogging):
    out = _rec(**_OVER_TRIGGER, waterlogging=waterlogging)
    assert out["should_irrigate"] is True
    assert out["waterlogging_hold"] is False
    assert LIMIT_DRAINAGE_UNKNOWN not in out["limitations"]


@pytest.mark.parametrize("waterlogging", [None, {}, {"risk": None, "drainage_need": None}])
def test_unavailable_assessment_adds_limitation_only(waterlogging):
    out = _rec(**_OVER_TRIGGER, **_LEACHING_READY, waterlogging=waterlogging)
    assert out["should_irrigate"] is True
    assert out["trigger_reason"] == "depletion_at_or_above_trigger"
    assert out["salinity_leaching_mm"] > 0
    assert LIMIT_DRAINAGE_UNKNOWN in out["limitations"]
    assert out["waterlogging_hold"] is False


def test_block_predicate_rejects_non_finite_and_boolean_risk():
    assert waterlogging_blocks_irrigation({"risk": float("nan")}) is None
    assert waterlogging_blocks_irrigation({"risk": True}) is None
    assert waterlogging_blocks_irrigation("subsurface") is None


# ── مُحلِّل استجابة soil-service (نقيّ، بلا شبكة) ───────────────────────


def test_parse_drainage_assessment_product():
    parsed = parse_drainage_assessment(
        {
            "product_id": "dap_1",
            "generated_at": "2026-11-01T00:00:00Z",
            "drainage_need": "subsurface",
            "waterlogging_risk": 0.42,
            "engineering_confidence": 0.5,
        }
    )
    assert parsed == {
        "risk": 0.42,
        "drainage_need": "subsurface",
        "assessment_id": "dap_1",
        "generated_at": "2026-11-01T00:00:00Z",
    }
    assert waterlogging_blocks_irrigation(parsed) is True


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"waterlogging_risk": 1.7, "drainage_need": "flooded"},
        {"waterlogging_risk": "0.9"},
        {"detail": "drainage assessment not found"},
    ],
)
def test_parse_drainage_assessment_unreadable_is_unknown_not_safe(payload):
    assert parse_drainage_assessment(payload) is None


def test_parse_keeps_valid_half_of_a_partially_invalid_payload():
    parsed = parse_drainage_assessment({"waterlogging_risk": -1, "drainage_need": "combined"})
    assert parsed["risk"] is None and parsed["drainage_need"] == "combined"


# ── (ب) هويّة وحدة رطوبة التربة ────────────────────────────────────────


def test_bare_soil_moisture_is_undeclared_and_cannot_raise_urgency():
    plain = _rec(et0_mm=5.0)
    bare = _rec(et0_mm=5.0, soil_moisture_pct=20.0)
    assert bare["urgency"] == plain["urgency"] != "high"
    assert "soil_moisture_sensor_unit_undeclared" in bare["limitations"]


def test_declared_fresh_accepted_available_water_raises_urgency():
    out = _rec(
        et0_mm=5.0,
        soil_moisture_pct=20.0,
        soil_moisture_unit_kind="available_pct",
        soil_moisture_quality_status="accepted",
        soil_moisture_observed_at=_NOW - timedelta(hours=1),
    )
    assert out["urgency"] == "high"
    assert not [x for x in out["limitations"] if x.startswith("soil_moisture")]


@pytest.mark.parametrize(
    ("unit", "quality", "age_h", "limitation"),
    [
        ("vwc_pct", "accepted", 1, "soil_moisture_vwc_not_comparable_to_available_water"),
        ("available_pct", None, 1, "soil_moisture_sensor_quality_unproven"),
        ("available_pct", "accepted", 30, "soil_moisture_sensor_reading_stale"),
        ("available_pct", "accepted", None, "soil_moisture_sensor_freshness_unproven"),
    ],
)
def test_ineligible_reading_stays_out_of_urgency(unit, quality, age_h, limitation):
    out = _rec(
        et0_mm=5.0,
        soil_moisture_pct=20.0,
        soil_moisture_unit_kind=unit,
        soil_moisture_quality_status=quality,
        soil_moisture_observed_at=None if age_h is None else _NOW - timedelta(hours=age_h),
    )
    assert out["urgency"] != "high"
    assert limitation in out["limitations"]


def test_request_model_defaults_unit_to_undeclared_and_forwards_identity():
    req = IrrigationRecommendationRequest(t_min_c=10.0, t_max_c=25.0, soil_moisture_pct=20.0)
    assert req.soil_moisture_inputs() == {
        "soil_moisture_pct": 20.0,
        "soil_moisture_unit_kind": None,
        "soil_moisture_observed_at": None,
        "soil_moisture_quality_status": None,
    }
    out = _rec(et0_mm=5.0, **req.soil_moisture_inputs())
    assert "soil_moisture_sensor_unit_undeclared" in out["limitations"]
