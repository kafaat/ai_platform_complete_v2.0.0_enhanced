"""اختبارات بوّابة اتّساق/نضارة حالة الريّ (WS-D.2) — نقيّة، fail-closed، لا قصّ."""

from api.irrigation_state_guard import assess_irrigation_state


def test_ready_when_consistent_and_fresh():
    out = assess_irrigation_state(
        depletion_mm=48.0, taw_mm=90.0, ledger_age_hours=10.0, taw_source="soil_lab"
    )
    assert out["status"] == "recommendation_ready"
    assert out["available"] is True
    assert out["depletion_fraction"] == round(48.0 / 90.0, 3)
    assert out["limitations"] == []  # مختبر + طازج ⇒ لا قيود


def test_missing_depletion_is_insufficient_not_zero():
    # مفقود ≠ صفر: غياب Dr ⇒ لا توصية (لا يُفترَض استنزاف صفر).
    out = assess_irrigation_state(depletion_mm=None, taw_mm=90.0)
    assert out["status"] == "insufficient_data"
    assert out["available"] is False
    assert "missing_depletion_mm" in out["limitations"]
    assert out["depletion_fraction"] is None


def test_missing_taw_is_insufficient():
    out = assess_irrigation_state(depletion_mm=48.0, taw_mm=None)
    assert out["status"] == "insufficient_data"
    assert out["available"] is False
    assert "missing_taw_mm" in out["limitations"]


def test_depletion_exceeds_taw_is_inconsistent_no_clamp():
    # Dr > TAW (اختلاف طوابع/خطأ تسوية) ⇒ inconsistent_state، unavailable، لا قصّ إلى TAW.
    out = assess_irrigation_state(depletion_mm=120.0, taw_mm=90.0, ledger_age_hours=1.0)
    assert out["status"] == "inconsistent_state"
    assert out["available"] is False
    assert "depletion_exceeds_taw" in out["limitations"]
    # الكسر يُبلَّغ للشفافيّة (>1) لكن لا تُنتَج توصية.
    assert out["depletion_fraction"] == round(120.0 / 90.0, 3)


def test_negative_depletion_is_inconsistent():
    out = assess_irrigation_state(depletion_mm=-5.0, taw_mm=90.0)
    assert out["status"] == "inconsistent_state"
    assert out["available"] is False


def test_taw_zero_is_inconsistent():
    out = assess_irrigation_state(depletion_mm=10.0, taw_mm=0.0)
    assert out["status"] == "inconsistent_state"
    assert out["available"] is False


def test_stale_ledger_is_limitation_not_block():
    # استنزاف قديم (> العتبة) ⇒ قيد مُعلَن، لا حجب (يبقى ready بتحذير).
    out = assess_irrigation_state(
        depletion_mm=48.0, taw_mm=90.0, ledger_age_hours=200.0, taw_source="soil_lab"
    )
    assert out["status"] == "recommendation_ready"
    assert out["available"] is True
    assert "stale_water_ledger" in out["limitations"]


def test_uncalibrated_taw_source_flagged():
    # TAW من نسيج احتياطيّ (غير معايَر) ⇒ قيد taw_uncalibrated (لا حجب).
    out = assess_irrigation_state(
        depletion_mm=48.0, taw_mm=90.0, ledger_age_hours=1.0, taw_source="texture_fallback"
    )
    assert out["available"] is True
    assert "taw_uncalibrated" in out["limitations"]
