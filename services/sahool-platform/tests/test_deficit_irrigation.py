"""Tests for deficit irrigation salinity trade-off: moderate deficit OK with fresh water,
severe deficit + saline water REJECTED (salt buildup), yield penalties match literature."""
from core.engines.deficit_irrigation import (
    evaluate_deficit_irrigation, soc_water_capacity_gain, _interp_penalty)


class TestYieldPenalty:
    def test_full_irrigation_no_penalty(self):
        assert _interp_penalty(100) == 0.0

    def test_severe_deficit_high_penalty(self):
        # 40% ETc → ~50% خسارة (Nature Sci Rep 2025)
        assert _interp_penalty(40) >= 0.45

    def test_moderate_deficit_low_penalty(self):
        # 80% ETc → ~7% خسارة
        assert _interp_penalty(80) <= 0.10


class TestSalinityTradeoff:
    def test_moderate_deficit_fresh_water_recommended(self):
        r = evaluate_deficit_irrigation(etc_fraction=85, water_ec_ds_m=0.8,
            crop_salinity_threshold_ds_m=6.0)
        assert r.recommended
        assert r.salinity_risk == "low"

    def test_severe_deficit_saline_water_rejected(self):
        # CRITICAL: عجز حادّ + ماء مالح → مرفوض (تراكم أملاح، الفيزياء تحكم)
        r = evaluate_deficit_irrigation(etc_fraction=50, water_ec_ds_m=4.0,
            crop_salinity_threshold_ds_m=6.0)
        assert not r.recommended
        assert r.salinity_risk == "high"
        assert any("تراكم أملاح" in w for w in r.warnings_ar)

    def test_severe_deficit_high_yield_penalty(self):
        r = evaluate_deficit_irrigation(etc_fraction=40, water_ec_ds_m=0.5,
            crop_salinity_threshold_ds_m=6.0)
        assert r.yield_penalty_pct >= 0.45
        assert not r.recommended

    def test_unknown_water_ec_warns(self):
        # ملوحة الماء مجهولة → تحذير صريح (لا تقييم بثقة)
        r = evaluate_deficit_irrigation(etc_fraction=70, water_ec_ds_m=None,
            crop_salinity_threshold_ds_m=6.0)
        assert any("غير معروف" in w for w in r.warnings_ar)

    def test_always_carries_estimate_caveat(self):
        # دائماً تقديري (سقف متوسّط) — لا ادّعاء دقّة
        r = evaluate_deficit_irrigation(etc_fraction=85, water_ec_ds_m=0.8,
            crop_salinity_threshold_ds_m=6.0)
        assert r.confidence in ("medium", "low")
        assert any("تقدير" in w for w in r.warnings_ar)


class TestSocWaterCapacity:
    def test_soc_increases_water_capacity(self):
        # 1% SOC → 1.5-2.5 مم/30سم (الأدبيات)
        g = soc_water_capacity_gain(1.0)
        assert g["awc_gain_mm_low"] == 1.5
        assert g["awc_gain_mm_high"] == 2.5

    def test_scales_with_depth(self):
        shallow = soc_water_capacity_gain(1.0, soil_depth_cm=30.0)
        deep = soc_water_capacity_gain(1.0, soil_depth_cm=60.0)
        assert deep["awc_gain_mm_high"] > shallow["awc_gain_mm_high"]


class TestRainfedGuard:
    """تصحيح بعد مراجعة: المحرّك للمروي لا المطري (الريّ التكميلي مفهوم مختلف)."""

    def test_rainfed_returns_not_applicable(self):
        # CRITICAL: حقل مطري → لا توصية عجز (المفهوم لا ينطبق)
        r = evaluate_deficit_irrigation(etc_fraction=80, water_ec_ds_m=0.8,
            crop_salinity_threshold_ds_m=6.0, is_irrigated=False)
        assert not r.recommended
        assert r.confidence == "none"
        assert any("مطري" in w for w in r.warnings_ar)

    def test_irrigated_still_works(self):
        # المروي (الافتراضي) يعمل كالسابق
        r = evaluate_deficit_irrigation(etc_fraction=85, water_ec_ds_m=0.8,
            crop_salinity_threshold_ds_m=6.0, is_irrigated=True)
        assert r.recommended
