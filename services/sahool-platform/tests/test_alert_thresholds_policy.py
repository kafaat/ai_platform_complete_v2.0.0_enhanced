"""اختبارات عتبات محرّك التنبيهات القابلة للسياسة (AlertThresholds) — منطق صرف.

يتحقّق أنّ الافتراضات == ثوابت اليوم، وأنّ thresholds=None مطابق تماماً
لتمرير AlertThresholds() الافتراضيّة، وأنّ thresholds_from_policy يطبّق
التجاوزات الصحيحة فقط ويتجاهل المفاتيح المجهولة والقيم المُشوّهة — دون أيّ رفع.
لا حاجة لقاعدة أو شبكة.
"""

from api.alert_rules import (
    FROST_RISK_CRITICAL_TMIN_C,
    FROST_RISK_TMIN_C,
    HEAT_STRESS_CRITICAL_TMAX_C,
    HEAT_STRESS_TMAX_C,
    HEAVY_RAIN_CRITICAL_MM,
    HEAVY_RAIN_MM,
    LOW_MOISTURE_IRRIGATION_MM,
    LOW_MOISTURE_SOIL_PCT,
    AlertThresholds,
    FieldAlertContext,
    evaluate_field_alerts,
    thresholds_from_policy,
)

FID = "fld_policy"


def _rep_ctx() -> FieldAlertContext:
    """سياق تمثيليّ يُطلِق عدّة قواعد (رطوبة/مطر/حرارة/صقيع)."""
    return FieldAlertContext(
        field_id=FID,
        soil_moisture_pct=20.0,
        forecast_rain_mm=25.0,
        temp_c=22.0,
        humidity_pct=85.0,
        rain_mm_3d=15.0,
        tmax_c=38.0,
        tmin_c=1.0,
        crop="tomato",
    )


class TestDefaultsEqualToday:
    def test_fields_equal_documented_constants(self):
        t = AlertThresholds()
        assert t.LOW_MOISTURE_SOIL_PCT == LOW_MOISTURE_SOIL_PCT == 30.0
        assert t.LOW_MOISTURE_IRRIGATION_MM == LOW_MOISTURE_IRRIGATION_MM == 8.0
        assert t.HEAVY_RAIN_MM == HEAVY_RAIN_MM == 20.0
        assert t.HEAVY_RAIN_CRITICAL_MM == HEAVY_RAIN_CRITICAL_MM == 40.0
        assert t.HEAT_STRESS_TMAX_C == HEAT_STRESS_TMAX_C == 35.0
        assert t.HEAT_STRESS_CRITICAL_TMAX_C == HEAT_STRESS_CRITICAL_TMAX_C == 40.0
        assert t.FROST_RISK_TMIN_C == FROST_RISK_TMIN_C == 2.0
        assert t.FROST_RISK_CRITICAL_TMIN_C == FROST_RISK_CRITICAL_TMIN_C == 0.0


class TestBehaviorIdentical:
    def test_none_equals_explicit_defaults(self):
        ctx = _rep_ctx()
        assert evaluate_field_alerts(ctx) == evaluate_field_alerts(
            ctx, thresholds=AlertThresholds()
        )

    def test_empty_ctx_identical(self):
        ctx = FieldAlertContext(field_id=FID)
        assert evaluate_field_alerts(ctx) == evaluate_field_alerts(
            ctx, thresholds=AlertThresholds()
        )


class TestPolicyOverrides:
    def test_overrides_only_named_field(self):
        t = thresholds_from_policy({"HEAT_STRESS_TMAX_C": 30.0})
        assert t.HEAT_STRESS_TMAX_C == 30.0
        # بقيّة الحقول تبقى على الافتراض.
        assert t.LOW_MOISTURE_SOIL_PCT == LOW_MOISTURE_SOIL_PCT
        assert t.HEAVY_RAIN_MM == HEAVY_RAIN_MM
        assert t.FROST_RISK_TMIN_C == FROST_RISK_TMIN_C

    def test_override_changes_firing(self):
        ctx = FieldAlertContext(field_id=FID, tmax_c=32.0)
        # الافتراض ٣٥°م ⇒ لا إجهاد حراريّ.
        assert evaluate_field_alerts(ctx) == []
        # خفض العتبة إلى ٣٠°م ⇒ يُطلق إجهاد حراريّ.
        t = thresholds_from_policy({"HEAT_STRESS_TMAX_C": 30.0})
        out = evaluate_field_alerts(ctx, thresholds=t)
        assert [a.alert_type for a in out] == ["heat_stress"]

    def test_int_and_string_numbers_coerced(self):
        t = thresholds_from_policy({"HEAVY_RAIN_MM": 10, "FROST_RISK_TMIN_C": "5"})
        assert t.HEAVY_RAIN_MM == 10.0
        assert t.FROST_RISK_TMIN_C == 5.0


class TestMalformedPolicy:
    def test_non_numeric_falls_back_to_default(self):
        t = thresholds_from_policy({"HEAT_STRESS_TMAX_C": "x"})
        assert t.HEAT_STRESS_TMAX_C == HEAT_STRESS_TMAX_C

    def test_none_gives_defaults(self):
        assert thresholds_from_policy(None) == AlertThresholds()

    def test_empty_dict_gives_defaults(self):
        assert thresholds_from_policy({}) == AlertThresholds()

    def test_unknown_keys_ignored(self):
        t = thresholds_from_policy({"NOT_A_FIELD": 99.0, "HEAVY_RAIN_MM": 12.0})
        assert t.HEAVY_RAIN_MM == 12.0
        assert not hasattr(t, "NOT_A_FIELD")

    def test_bool_ignored(self):
        # bool هو فرع من int؛ نتجاهله صراحةً لتفادي True->1.0.
        t = thresholds_from_policy({"HEAVY_RAIN_MM": True})
        assert t.HEAVY_RAIN_MM == HEAVY_RAIN_MM

    def test_none_value_falls_back(self):
        t = thresholds_from_policy({"HEAVY_RAIN_MM": None})
        assert t.HEAVY_RAIN_MM == HEAVY_RAIN_MM

    def test_does_not_raise_on_garbage(self):
        # لا يرفع أبداً حتّى مع مدخلات غريبة.
        assert thresholds_from_policy({"HEAVY_RAIN_MM": [1, 2]}) == AlertThresholds()
        assert thresholds_from_policy("not a dict") == AlertThresholds()
