"""اختبارات محرّك الحالة الزراعيّة الموحّدة — قاعدة الأرجحيّة الحاسمة.

فجوة تغطية (مراجعة الجولة ٣): قاعدة «الملوحة الحرجة تتجاوز NDVI الإيجابي»
(SAL-SOIL-03، ECe≥8) كانت بلا قفل انحدار. هنا نثبّتها + المسار الطبيعيّ (الحيويّة
الجيّدة تقود) + إعلان التعارض الصريح.
"""

from core.agronomic_state_engine import SignalInput, compose_field_state


def test_critical_salinity_overrides_positive_ndvi():
    # NDVI عالٍ (حيويّة 0.85) لكن ملوحة تربة حرجة (EC=10 ≥ 8) ⇒ الملوحة تحكم.
    state = compose_field_state(
        "f1",
        [SignalInput(source="ndvi", value=0.85), SignalInput(source="soil_ec", value=10.0)],
        tenant_id="t1",
    )
    truths = state.operational_truths
    assert truths["salinity_class"] == "critical"
    assert truths["crop_vigor"] == 0.85  # الإشارة الإيجابيّة موجودة فعلاً
    # القرار الفعليّ: الملوحة الحرجة لا الحيويّة اللحظيّة.
    assert truths["effective_status"] == "salinity_limited"
    assert truths["effective_status_rule"] == "SAL-SOIL-03"
    # التعارض مُعلَن صراحةً (لا يُخفى أنّ مؤشّراً إيجابيّاً تجاوزته الملوحة).
    assert any(
        isinstance(c, dict) and c.get("resolution") == "salinity_critical_overrides"
        for c in state.contradictions
    )


def test_good_vigor_leads_when_no_dominant_constraint():
    state = compose_field_state("f2", [SignalInput(source="ndvi", value=0.8)], tenant_id="t1")
    assert state.operational_truths["effective_status"] == "vigor_led"
    assert state.contradictions == []  # لا تجاوز ⇒ لا تعارض


def test_moderate_salinity_does_not_override_positive_vigor():
    # ملوحة معتدلة (EC=5، دون 8) لا تُصنَّف critical ⇒ لا تتجاوز الحيويّة الجيّدة.
    state = compose_field_state(
        "f3",
        [SignalInput(source="ndvi", value=0.8), SignalInput(source="soil_ec", value=5.0)],
        tenant_id="t1",
    )
    assert state.operational_truths.get("salinity_class") != "critical"
    assert state.operational_truths["effective_status"] == "vigor_led"
