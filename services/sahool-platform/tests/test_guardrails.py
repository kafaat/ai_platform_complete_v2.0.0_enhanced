"""Tests for unified guardrails (inspired by A/B law 24): red lines halt any recommendation
regardless of success metrics. Guardrails govern over success."""

from core.guardrails import GuardrailSeverity, check_guardrails


class TestHaltConditions:
    def test_phi_unsatisfied_halts(self):
        # CRITICAL: PHI لم ينقضِ → توقّف مهما كان غيره
        r = check_guardrails(
            pesticide_phi_satisfied=False, has_governing_data=True, zone_factor_calibrated=True
        )
        assert not r.passed
        assert r.halted

    def test_missing_governing_data_halts(self):
        r = check_guardrails(has_governing_data=False)
        assert not r.passed
        assert r.halted

    def test_severe_salinity_halts(self):
        r = check_guardrails(
            soil_ec_ds_m=10.0,
            crop_salinity_threshold_ds_m=6.0,
            has_governing_data=True,
            zone_factor_calibrated=True,
        )
        assert not r.passed

    def test_deficit_salt_buildup_halts(self):
        # CRITICAL: عجز حادّ بماء مالح → توقّف (الفيزياء ترفض)
        r = check_guardrails(
            deficit_salinity_risk="high", has_governing_data=True, zone_factor_calibrated=True
        )
        assert not r.passed
        assert r.halted

    def test_halt_caps_confidence_to_none(self):
        r = check_guardrails(pesticide_phi_satisfied=False, has_governing_data=True)
        assert r.confidence_cap == "none"


class TestWarnConditions:
    def test_uncalibrated_warns_not_halts(self):
        # لا معايرة → تحذير (سقف medium) لا توقّف
        r = check_guardrails(
            pesticide_phi_satisfied=True, has_governing_data=True, zone_factor_calibrated=False
        )
        assert r.passed  # لم تتوقّف
        assert r.confidence_cap == "medium"

    def test_salinity_above_threshold_warns(self):
        # ملوحة فوق العتبة قليلاً → تحذير لا توقّف
        r = check_guardrails(
            soil_ec_ds_m=7.0,
            crop_salinity_threshold_ds_m=6.0,
            has_governing_data=True,
            zone_factor_calibrated=True,
        )
        assert r.passed
        assert any(b.severity == GuardrailSeverity.WARN for b in r.breaches)


class TestPassThrough:
    def test_all_clear_passes(self):
        r = check_guardrails(
            pesticide_phi_satisfied=True,
            has_governing_data=True,
            soil_ec_ds_m=3.0,
            crop_salinity_threshold_ds_m=6.0,
            zone_factor_calibrated=True,
        )
        assert r.passed
        assert not r.breaches

    def test_guardrail_governs_over_success(self):
        # المبدأ الجوهري: حتى لو كل شيء "ناجح"، خط أحمر واحد يوقف
        r = check_guardrails(
            pesticide_phi_satisfied=False,  # خط أحمر وحيد
            has_governing_data=True,
            soil_ec_ds_m=2.0,
            crop_salinity_threshold_ds_m=6.0,
            zone_factor_calibrated=True,
        )
        assert not r.passed  # توقّفت رغم أن كل شيء آخر سليم
