"""Tests for implementation verification: passive (intent) vs physical (effect),
physical governs over claim, no fabrication when no signal (UNCONFIRMED is honest)."""

from core.implementation_verification import (
    ImplementationStatus,
    combined_verification,
    verify_passive,
    verify_physical,
)


class TestPassive:
    def test_yes_is_claimed_not_implemented(self):
        # CRITICAL: قول المزارع "نعم" = نيّة (CLAIMED) لا أثر مؤكّد (IMPLEMENTED)
        r = verify_passive("نعم")
        assert r.status == ImplementationStatus.CLAIMED
        assert r.confidence == "low"

    def test_no_is_rejected(self):
        r = verify_passive("لا", why_rejected="الماء مكلف")
        assert r.status == ImplementationStatus.REJECTED
        assert "مكلف" in r.learn_signal

    def test_none_is_unconfirmed(self):
        r = verify_passive(None)
        assert r.status == ImplementationStatus.UNCONFIRMED


class TestPhysical:
    def test_effect_confirms_implementation(self):
        # رطوبة ارتفعت كما متوقّع → مؤكّد فيزيائياً (high)
        r = verify_physical(18.0, 25.0, expected_delta=6.0)
        assert r.status == ImplementationStatus.IMPLEMENTED
        assert r.confidence == "high"

    def test_partial_effect_insufficient(self):
        r = verify_physical(18.0, 19.0, expected_delta=6.0)
        assert r.status == ImplementationStatus.INSUFFICIENT

    def test_no_effect_rejected(self):
        r = verify_physical(18.0, 18.1, expected_delta=6.0)
        assert r.status == ImplementationStatus.REJECTED

    def test_no_sensor_unconfirmed(self):
        # لا قراءة → غير مؤكّد (لا اختراع)
        r = verify_physical(None, None, expected_delta=6.0)
        assert r.status == ImplementationStatus.UNCONFIRMED


class TestCombined:
    def test_physical_governs_over_claim(self):
        # CRITICAL: ادّعاء التنفيذ + لا أثر فيزيائي → الحسّاس يحكم (REJECTED)
        r = combined_verification(
            farmer_response="نعم", metric_before=18.0, metric_after=18.2, expected_delta=6.0
        )
        assert r.status == ImplementationStatus.REJECTED
        assert r.learn_signal == "claimed_but_no_physical_effect"

    def test_physical_confirms_when_available(self):
        r = combined_verification(
            farmer_response="نعم", metric_before=18.0, metric_after=25.0, expected_delta=6.0
        )
        assert r.status == ImplementationStatus.IMPLEMENTED

    def test_falls_back_to_passive_without_sensor(self):
        # بلا حسّاس → السلبي (CLAIMED)
        r = combined_verification(farmer_response="نعم")
        assert r.status == ImplementationStatus.CLAIMED

    def test_no_signal_at_all_unconfirmed(self):
        r = combined_verification()
        assert r.status == ImplementationStatus.UNCONFIRMED


class TestArbitrationEdgeCases:
    """حالات حدّية من المراجعة النقدية: الحسّاس قرينة لا حاكم معصوم."""

    def test_low_confidence_sensor_no_hard_reject(self):
        # CRITICAL: حسّاس منخفض الثقة + تعارض → لا رفض قاطع (قد يكون معطّلاً)
        from core.implementation_verification import ImplementationStatus, combined_verification

        r = combined_verification(
            farmer_response="نعم",
            metric_before=18,
            metric_after=18.2,
            expected_delta=6,
            sensor_confidence="low",
        )
        assert r.status == ImplementationStatus.UNCONFIRMED
        assert r.learn_signal == "low_confidence_sensor_mismatch"

    def test_subsurface_irrigation_no_hard_reject(self):
        # CRITICAL: ري تحت-سطحي لا يرفع الرطوبة السطحية → لا رفض قاطع
        from core.implementation_verification import ImplementationStatus, combined_verification

        r = combined_verification(
            farmer_response="نعم",
            metric_before=18,
            metric_after=18.2,
            expected_delta=6,
            subsurface_irrigation=True,
        )
        assert r.status == ImplementationStatus.UNCONFIRMED
        assert r.learn_signal == "subsurface_sensor_mismatch"

    def test_high_confidence_sensor_still_arbitrates_not_absolute(self):
        # حسّاس موثوق يترجّح لكن بسقف medium لا high (ليس قطعاً)
        from core.implementation_verification import ImplementationStatus, combined_verification

        r = combined_verification(
            farmer_response="نعم",
            metric_before=18,
            metric_after=18.2,
            expected_delta=6,
            sensor_confidence="high",
        )
        assert r.status == ImplementationStatus.REJECTED
        assert r.confidence == "medium"  # خُفّض من high — ليس تغلّباً مطلقاً

    def test_low_confidence_sensor_caps_positive_confirmation(self):
        # حسّاس منخفض الثقة يؤكّد التنفيذ لكن بسقف مخفّض
        from core.implementation_verification import ImplementationStatus, combined_verification

        r = combined_verification(
            metric_before=18, metric_after=25, expected_delta=6, sensor_confidence="medium"
        )
        assert r.status == ImplementationStatus.IMPLEMENTED
        assert r.confidence == "medium"  # لا high رغم الأثر


class TestMaestroIntegration:
    """نقطة أ من المراجعة: الوجود ≠ التكامل — هذا يحرس الاتصال الفعلي."""

    def test_followup_enriches_recommendation_log(self):
        from core.implementation_verification import verify_recommendation_followup

        rec = {"recommendation_id": "irr_001", "type": "irrigation"}
        out = verify_recommendation_followup(
            rec, farmer_response="نعم", metric_before=18, metric_after=25, expected_delta=6
        )
        assert "verification" in out
        assert out["verification"]["status"] == "implemented"
        assert out["recommendation_id"] == "irr_001"  # لا يعدّل الأصل

    def test_followup_preserves_original_fields(self):
        from core.implementation_verification import verify_recommendation_followup

        rec = {"recommendation_id": "x", "type": "fertilizer", "confidence": "medium"}
        out = verify_recommendation_followup(rec, farmer_response="لا")
        assert out["type"] == "fertilizer"
        assert out["confidence"] == "medium"
        assert out["verification"]["status"] == "rejected"

    def test_followup_carries_learn_signal(self):
        # التكامل يمرّر إشارة التعلّم (للـ calibration_loop)
        from core.implementation_verification import verify_recommendation_followup

        rec = {"recommendation_id": "y", "type": "irrigation"}
        out = verify_recommendation_followup(
            rec,
            farmer_response="نعم",
            metric_before=18,
            metric_after=18.2,
            expected_delta=6,
            sensor_confidence="low",
        )
        assert out["verification"]["learn_signal"] == "low_confidence_sensor_mismatch"
