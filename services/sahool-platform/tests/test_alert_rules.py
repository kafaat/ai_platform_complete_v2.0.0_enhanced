"""اختبارات محرّك توليد التنبيهات (api.alert_rules) — منطق صرف offline.

يغطّي كلّ قاعدة (إطلاقها وعدم إطلاقها) على سياقات تمثيليّة + درجات الخطورة
الحرجة، وحذف التكرار في الترتيب، وأنّ السياق الفارغ لا يُطلِق شيئاً.
لا حاجة لقاعدة أو شبكة — disease_risk نقيّ مُعاد استخدامه.
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
    NDVI_DROP_CRITICAL,
    NDVI_DROP_WARN,
    FieldAlertContext,
    evaluate_field_alerts,
)

FID = "fld_test"


def _types(ctx: FieldAlertContext) -> set[str]:
    return {a.alert_type for a in evaluate_field_alerts(ctx)}


def _by_type(ctx: FieldAlertContext) -> dict[str, str]:
    """خريطة alert_type -> severity للتنبيهات المُطلَقة."""
    return {a.alert_type: a.severity for a in evaluate_field_alerts(ctx)}


class TestEmptyContext:
    def test_no_data_fires_nothing(self):
        assert evaluate_field_alerts(FieldAlertContext(field_id=FID)) == []


class TestLowMoisture:
    def test_fires_on_low_soil_moisture(self):
        ctx = FieldAlertContext(field_id=FID, soil_moisture_pct=LOW_MOISTURE_SOIL_PCT - 5)
        assert "low_moisture" in _types(ctx)

    def test_not_fired_when_soil_comfortable(self):
        ctx = FieldAlertContext(field_id=FID, soil_moisture_pct=LOW_MOISTURE_SOIL_PCT + 20)
        assert "low_moisture" not in _types(ctx)

    def test_boundary_exactly_at_threshold_not_fired(self):
        # العتبة صارمة (<)؛ القيمة عند الحدّ تماماً لا تُطلِق.
        ctx = FieldAlertContext(field_id=FID, soil_moisture_pct=LOW_MOISTURE_SOIL_PCT)
        assert "low_moisture" not in _types(ctx)

    def test_fires_on_high_irrigation_need_when_no_soil_reading(self):
        ctx = FieldAlertContext(field_id=FID, irrigation_need_mm=LOW_MOISTURE_IRRIGATION_MM + 2)
        assert "low_moisture" in _types(ctx)

    def test_irrigation_need_ignored_when_soil_reading_present(self):
        # رطوبة تربة مريحة تتجاوز احتياج الريّ المرتفع (قراءة مباشرة أوثق).
        ctx = FieldAlertContext(
            field_id=FID,
            soil_moisture_pct=70.0,
            irrigation_need_mm=LOW_MOISTURE_IRRIGATION_MM + 5,
        )
        assert "low_moisture" not in _types(ctx)

    def test_low_irrigation_need_does_not_fire(self):
        ctx = FieldAlertContext(field_id=FID, irrigation_need_mm=LOW_MOISTURE_IRRIGATION_MM - 4)
        assert "low_moisture" not in _types(ctx)


class TestHeavyRain:
    def test_fires_above_threshold(self):
        ctx = FieldAlertContext(field_id=FID, forecast_rain_mm=HEAVY_RAIN_MM + 5)
        assert _by_type(ctx).get("heavy_rain") == "warning"

    def test_not_fired_below_threshold(self):
        ctx = FieldAlertContext(field_id=FID, forecast_rain_mm=HEAVY_RAIN_MM - 5)
        assert "heavy_rain" not in _types(ctx)

    def test_critical_on_extreme_rain(self):
        ctx = FieldAlertContext(field_id=FID, forecast_rain_mm=HEAVY_RAIN_CRITICAL_MM + 10)
        assert _by_type(ctx).get("heavy_rain") == "critical"


class TestDiseaseRisk:
    def test_fires_on_high_risk_conditions(self):
        # رطوبة عالية + حرارة معتدلة + مطر تراكميّ ⇒ disease_risk='high' (3 عوامل).
        ctx = FieldAlertContext(field_id=FID, temp_c=22.0, humidity_pct=90.0, rain_mm_3d=15.0)
        sev = _by_type(ctx)
        assert sev.get("disease_risk") == "critical"

    def test_not_fired_on_low_risk(self):
        # حارّ وجافّ ⇒ خطر منخفض، لا تنبيه.
        ctx = FieldAlertContext(field_id=FID, temp_c=40.0, humidity_pct=20.0, rain_mm_3d=0.0)
        assert "disease_risk" not in _types(ctx)

    def test_not_fired_on_moderate_risk(self):
        # عاملان فقط (رطوبة عالية + حرارة معتدلة، بلا مطر) ⇒ moderate، لا تنبيه.
        ctx = FieldAlertContext(field_id=FID, temp_c=22.0, humidity_pct=90.0, rain_mm_3d=0.0)
        assert "disease_risk" not in _types(ctx)

    def test_not_fired_without_temp_or_humidity(self):
        assert "disease_risk" not in _types(FieldAlertContext(field_id=FID, temp_c=22.0))
        assert "disease_risk" not in _types(FieldAlertContext(field_id=FID, humidity_pct=90.0))


class TestHeatStress:
    def test_fires_above_threshold(self):
        ctx = FieldAlertContext(field_id=FID, tmax_c=HEAT_STRESS_TMAX_C + 2)
        assert _by_type(ctx).get("heat_stress") == "warning"

    def test_not_fired_below_threshold(self):
        ctx = FieldAlertContext(field_id=FID, tmax_c=HEAT_STRESS_TMAX_C - 5)
        assert "heat_stress" not in _types(ctx)

    def test_critical_on_extreme_heat(self):
        ctx = FieldAlertContext(field_id=FID, tmax_c=HEAT_STRESS_CRITICAL_TMAX_C + 3)
        assert _by_type(ctx).get("heat_stress") == "critical"


class TestGrowthStageEscalation:
    # tmax بين عتبة التحذير والعتبة الحرجة ⇒ عادةً "warning".
    _WARN_TMAX = (HEAT_STRESS_TMAX_C + HEAT_STRESS_CRITICAL_TMAX_C) / 2

    def test_heat_warning_escalates_to_critical_at_flowering(self):
        ctx = FieldAlertContext(field_id=FID, tmax_c=self._WARN_TMAX, growth_stage="mid")
        assert _by_type(ctx).get("heat_stress") == "critical"

    def test_heat_warning_unchanged_when_stage_unknown(self):
        # نفس الحرارة بلا طور معروف ⇒ يبقى "warning" (توافق خلفيّ).
        ctx = FieldAlertContext(field_id=FID, tmax_c=self._WARN_TMAX, growth_stage=None)
        assert _by_type(ctx).get("heat_stress") == "warning"

    def test_heat_warning_not_escalated_on_vegetative_stages(self):
        for stage in ("initial", "development", "late"):
            ctx = FieldAlertContext(field_id=FID, tmax_c=self._WARN_TMAX, growth_stage=stage)
            assert _by_type(ctx).get("heat_stress") == "warning"

    def test_heat_already_critical_stays_critical_regardless_of_stage(self):
        hot = HEAT_STRESS_CRITICAL_TMAX_C + 3
        for stage in ("mid", "initial", None):
            ctx = FieldAlertContext(field_id=FID, tmax_c=hot, growth_stage=stage)
            assert _by_type(ctx).get("heat_stress") == "critical"

    def test_heat_flowering_message_notes_flowering(self):
        ctx = FieldAlertContext(field_id=FID, tmax_c=self._WARN_TMAX, growth_stage="mid")
        alert = next(a for a in evaluate_field_alerts(ctx) if a.alert_type == "heat_stress")
        assert "التزهير" in alert.message_ar

    def test_low_moisture_warning_escalates_to_critical_at_flowering(self):
        ctx = FieldAlertContext(
            field_id=FID,
            soil_moisture_pct=LOW_MOISTURE_SOIL_PCT - 5,
            growth_stage="mid",
        )
        assert _by_type(ctx).get("low_moisture") == "critical"

    def test_low_moisture_warning_unchanged_on_initial_stage(self):
        ctx = FieldAlertContext(
            field_id=FID,
            soil_moisture_pct=LOW_MOISTURE_SOIL_PCT - 5,
            growth_stage="initial",
        )
        assert _by_type(ctx).get("low_moisture") == "warning"

    def test_low_moisture_warning_unchanged_when_stage_unknown(self):
        ctx = FieldAlertContext(field_id=FID, soil_moisture_pct=LOW_MOISTURE_SOIL_PCT - 5)
        assert _by_type(ctx).get("low_moisture") == "warning"

    def test_low_moisture_flowering_message_notes_flowering(self):
        ctx = FieldAlertContext(
            field_id=FID,
            soil_moisture_pct=LOW_MOISTURE_SOIL_PCT - 5,
            growth_stage="mid",
        )
        alert = next(a for a in evaluate_field_alerts(ctx) if a.alert_type == "low_moisture")
        assert "التزهير" in alert.message_ar


class TestFrostRisk:
    def test_fires_below_threshold(self):
        ctx = FieldAlertContext(field_id=FID, tmin_c=FROST_RISK_TMIN_C - 1)
        assert _by_type(ctx).get("frost_risk") == "warning"

    def test_not_fired_above_threshold(self):
        ctx = FieldAlertContext(field_id=FID, tmin_c=FROST_RISK_TMIN_C + 5)
        assert "frost_risk" not in _types(ctx)

    def test_critical_on_freezing(self):
        ctx = FieldAlertContext(field_id=FID, tmin_c=FROST_RISK_CRITICAL_TMIN_C - 1)
        assert _by_type(ctx).get("frost_risk") == "critical"


class TestVegetationStress:
    _BASELINE = 0.70

    def test_no_ndvi_values_fires_nothing(self):
        # توافق خلفيّ: الافتراض None ⇒ لا تنبيه إجهاد غطاء نباتيّ.
        assert "vegetation_stress" not in _types(FieldAlertContext(field_id=FID))

    def test_baseline_only_does_not_fire(self):
        ctx = FieldAlertContext(field_id=FID, ndvi_baseline=self._BASELINE)
        assert "vegetation_stress" not in _types(ctx)

    def test_current_only_does_not_fire(self):
        ctx = FieldAlertContext(field_id=FID, ndvi_current=0.40)
        assert "vegetation_stress" not in _types(ctx)

    def test_warning_on_moderate_drop(self):
        # هبوط ٠٫١٥ (بين عتبة التحذير والحرجة) ⇒ warning.
        ctx = FieldAlertContext(field_id=FID, ndvi_baseline=0.70, ndvi_current=0.55)
        assert _by_type(ctx).get("vegetation_stress") == "warning"

    def test_critical_on_large_drop(self):
        # هبوط ٠٫٢٥ (≥ العتبة الحرجة) ⇒ critical.
        ctx = FieldAlertContext(field_id=FID, ndvi_baseline=0.70, ndvi_current=0.45)
        assert _by_type(ctx).get("vegetation_stress") == "critical"

    def test_drop_below_warn_does_not_fire(self):
        small = NDVI_DROP_WARN / 2
        ctx = FieldAlertContext(
            field_id=FID, ndvi_baseline=self._BASELINE, ndvi_current=self._BASELINE - small
        )
        assert "vegetation_stress" not in _types(ctx)

    def test_drop_just_above_warn_fires_warning(self):
        # هبوط فوق عتبة التحذير بقليل ⇒ warning (العتبة شاملة: drop >= WARN).
        ctx = FieldAlertContext(
            field_id=FID,
            ndvi_baseline=self._BASELINE,
            ndvi_current=self._BASELINE - (NDVI_DROP_WARN + 0.01),
        )
        assert _by_type(ctx).get("vegetation_stress") == "warning"

    def test_warning_escalates_to_critical_at_flowering(self):
        warn = (NDVI_DROP_WARN + NDVI_DROP_CRITICAL) / 2
        ctx = FieldAlertContext(
            field_id=FID,
            ndvi_baseline=self._BASELINE,
            ndvi_current=self._BASELINE - warn,
            growth_stage="mid",
        )
        assert _by_type(ctx).get("vegetation_stress") == "critical"

    def test_warning_unchanged_on_initial_stage(self):
        warn = (NDVI_DROP_WARN + NDVI_DROP_CRITICAL) / 2
        ctx = FieldAlertContext(
            field_id=FID,
            ndvi_baseline=self._BASELINE,
            ndvi_current=self._BASELINE - warn,
            growth_stage="initial",
        )
        assert _by_type(ctx).get("vegetation_stress") == "warning"

    def test_message_frames_drop_as_scouting_trigger(self):
        ctx = FieldAlertContext(field_id=FID, ndvi_baseline=0.70, ndvi_current=0.55)
        alert = next(a for a in evaluate_field_alerts(ctx) if a.alert_type == "vegetation_stress")
        assert "كشف" in alert.message_ar
        assert "تشخيص" in alert.message_ar


class TestMultipleRules:
    def test_multiple_alerts_fire_in_stable_order(self):
        # رطوبة منخفضة + إجهاد حراريّ معاً.
        ctx = FieldAlertContext(
            field_id=FID,
            soil_moisture_pct=10.0,
            tmax_c=HEAT_STRESS_TMAX_C + 5,
        )
        result = evaluate_field_alerts(ctx)
        ordered = [a.alert_type for a in result]
        assert ordered == ["low_moisture", "heat_stress"]

    def test_vegetation_stress_appended_after_existing_rules(self):
        # رطوبة منخفضة + إجهاد حراريّ + هبوط NDVI ⇒ الترتيب يُحافظ على القواعد
        # السابقة ثمّ يُلحق vegetation_stress في النهاية (_RULES order).
        ctx = FieldAlertContext(
            field_id=FID,
            soil_moisture_pct=10.0,
            tmax_c=HEAT_STRESS_TMAX_C + 5,
            ndvi_baseline=0.70,
            ndvi_current=0.55,
        )
        ordered = [a.alert_type for a in evaluate_field_alerts(ctx)]
        assert ordered == ["low_moisture", "heat_stress", "vegetation_stress"]

    def test_each_alert_has_arabic_title_and_message(self):
        ctx = FieldAlertContext(field_id=FID, forecast_rain_mm=HEAVY_RAIN_MM + 1)
        for a in evaluate_field_alerts(ctx):
            assert a.title_ar.strip()
            assert a.message_ar.strip()
            assert a.severity in {"info", "warning", "critical"}
