"""اختبارات محرّك الحالة الزراعيّة الموحّدة — قاعدة الأرجحيّة الحاسمة.

فجوة تغطية (مراجعة الجولة ٣): قاعدة «الملوحة الحرجة تتجاوز NDVI الإيجابي»
(SAL-SOIL-03، ECe≥8) كانت بلا قفل انحدار. هنا نثبّتها + المسار الطبيعيّ (الحيويّة
الجيّدة تقود) + إعلان التعارض الصريح.
"""

from core.agronomic_state_engine import (
    CanonicalFieldState,
    EconomicContext,
    SignalInput,
    assess_economics,
    compare_seasons,
    compose_field_state,
    state_to_event_row,
)


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


# ── حدود عتبات الملوحة (SAL-SOIL-*): قفل انحدار `>=` لا `>` ──


def test_salinity_class_boundary_at_critical_threshold():
    # EC=8.0 بالضبط (≥ SALINITY_CRITICAL_ECE) ⇒ critical، لا moderate.
    # يقفل أنّ الشرط `ec >= 8.0` لا `ec > 8.0`.
    state = compose_field_state("f", [SignalInput(source="soil_ec", value=8.0)])
    assert state.operational_truths["salinity_class"] == "critical"
    # المخاطرة = min(8/16, 1) = 0.5 (حساب يدوي من الكود).
    assert state.operational_truths["salinity_risk"] == 0.5


def test_salinity_class_just_below_critical_is_moderate():
    # EC=7.99 (< 8) ⇒ moderate لا critical — جانب العتبة الآخر.
    state = compose_field_state("f", [SignalInput(source="soil_ec", value=7.99)])
    assert state.operational_truths["salinity_class"] == "moderate"


def test_salinity_class_boundary_at_moderate_threshold():
    # EC=4.0 بالضبط (≥ SALINITY_MODERATE_ECE) ⇒ moderate.
    # EC=3.99 (< 4) ⇒ low. يقفل حدّ `>= 4.0`.
    moderate = compose_field_state("f", [SignalInput(source="soil_ec", value=4.0)])
    assert moderate.operational_truths["salinity_class"] == "moderate"
    assert moderate.operational_truths["salinity_risk"] == 0.25  # 4/16
    low = compose_field_state("f", [SignalInput(source="soil_ec", value=3.99)])
    assert low.operational_truths["salinity_class"] == "low"


def test_salinity_risk_is_capped_at_one_for_extreme_ec():
    # EC=20 ⇒ المخاطرة = min(20/16, 1) = 1.0 (لا تتجاوز 1 رغم الـEC العالي).
    state = compose_field_state("f", [SignalInput(source="soil_ec", value=20.0)])
    assert state.operational_truths["salinity_risk"] == 1.0


# ── حدود عتبة الإجهاد الحراري (HEAT-01): heat >= 0.8 ──


def test_heat_severe_overrides_at_boundary():
    # heat=0.8 بالضبط (≥ 0.8) ⇒ heat_limited يتقدّم على الحيويّة الجيّدة.
    state = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.8), SignalInput(source="weather", value=0.8)],
    )
    assert state.operational_truths["effective_status"] == "heat_limited"
    assert state.operational_truths["effective_status_rule"] == "HEAT-01"


def test_heat_just_below_threshold_does_not_override():
    # heat=0.79 (< 0.8) ⇒ لا تجاوز، الحيويّة الجيّدة تقود.
    state = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.8), SignalInput(source="weather", value=0.79)],
    )
    assert state.operational_truths["effective_status"] == "vigor_led"


# ── حدود عتبة الحيويّة المنخفضة (RS-VIGOR-01): vigor < 0.4 ──


def test_low_vigor_boundary_strictly_below_point_four():
    # vigor=0.4 بالضبط ليس < 0.4 ⇒ vigor_led (لا vigor_stressed).
    led = compose_field_state("f", [SignalInput(source="ndvi", value=0.4)])
    assert led.operational_truths["crop_vigor"] == 0.4
    assert led.operational_truths["effective_status"] == "vigor_led"
    # vigor=0.39 (< 0.4) ⇒ vigor_stressed.
    stressed = compose_field_state("f", [SignalInput(source="ndvi", value=0.39)])
    assert stressed.operational_truths["crop_vigor"] == 0.39
    assert stressed.operational_truths["effective_status"] == "vigor_stressed"
    assert stressed.operational_truths["effective_status_rule"] == "RS-VIGOR-01"


# ── ترتيب الأسبقيّة بين القيود (arbitration ordering) ──


def test_salinity_critical_outranks_declining_trend():
    # ملوحة حرجة + اتّجاه هابط معاً ⇒ الملوحة (الأعلى أولويّةً) تحكم.
    state = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.7), SignalInput(source="soil_ec", value=10.0)],
        ndvi_trend_values=[0.7, 0.68, 0.66, 0.64, 0.62],
    )
    assert state.operational_truths["effective_status"] == "salinity_limited"


def test_heat_severe_outranks_declining_trend():
    # إجهاد حراري حادّ + اتّجاه هابط ⇒ الحرارة (أعلى أولويّةً من الاتّجاه) تحكم.
    state = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.7), SignalInput(source="weather", value=0.9)],
        ndvi_trend_values=[0.7, 0.68, 0.66, 0.64, 0.62],
    )
    assert state.operational_truths["effective_status"] == "heat_limited"


def test_declining_trend_warns_when_no_higher_constraint():
    # اتّجاه هابط أملس (CV منخفض) بلا ملوحة/حرارة ⇒ trend_warning (MON-TREND-01).
    state = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.7)],
        ndvi_trend_values=[0.7, 0.68, 0.66, 0.64, 0.62],
    )
    assert state.operational_truths["ndvi_trend"] == "decreasing"
    assert state.operational_truths["effective_status"] == "trend_warning"
    assert state.operational_truths["effective_status_rule"] == "MON-TREND-01"


# ── إعلان التعارض مشروط بإيجابيّة المؤشّر (vigor > 0.5) ──


def test_override_not_logged_as_contradiction_when_vigor_not_positive():
    # ملوحة حرجة تتجاوز حيويّة 0.45 (ليست > 0.5) ⇒ لا تعارض مُسجّل (لا مؤشّر
    # إيجابي حقيقي ليُعلَن أنّه تجووز). الحالة الفعليّة تبقى salinity_limited.
    state = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.45), SignalInput(source="soil_ec", value=10.0)],
    )
    assert state.operational_truths["effective_status"] == "salinity_limited"
    assert state.contradictions == []


def test_heat_override_logs_explicit_contradiction():
    # حرارة حادّة تتجاوز حيويّة 0.7 (> 0.5) ⇒ تعارض مُعلَن بمعرّف heat_severe.
    state = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.7), SignalInput(source="weather", value=0.9)],
    )
    assert any(
        isinstance(c, dict)
        and c.get("type") == "positive_signal_overridden_by_heat_severe"
        and c.get("source_rule") == "HEAT-01"
        for c in state.contradictions
    )


# ── الصدق: غياب الإشارات يُعلَن لا يُختلق ──


def test_no_signals_declares_missing_and_no_fabricated_status():
    # بلا إشارات ⇒ لا حالة فعليّة مُختلقة، والثقة "none"، والنواقص مُعلَنة.
    state = compose_field_state("f", [])
    assert "effective_status" not in state.operational_truths
    assert state.confidence == "none"
    assert "spectral_indices (ndvi/ndre/ndsi)" in state.missing_signals
    assert "soil_ec (الملوحة)" in state.missing_signals


def test_missing_soil_ec_is_declared_not_assumed_low():
    # حضور NDVI وحده دون soil_ec ⇒ لا salinity_class مُختلق، والنقص مُعلَن.
    state = compose_field_state("f", [SignalInput(source="ndvi", value=0.8)])
    assert "salinity_class" not in state.operational_truths
    assert "soil_ec (الملوحة)" in state.missing_signals


def test_insufficient_trend_samples_not_fabricated():
    # 3 قيم فقط (< 4) ⇒ لا يُحسَب ndvi_trend (لا اختراع اتّجاه من عيّنة قاصرة).
    state = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.7)],
        ndvi_trend_values=[0.7, 0.6, 0.5],
    )
    assert "ndvi_trend" not in state.operational_truths


# ── الثقة (fuse_confidence): السقف الأدنى يحكم ──


def test_confidence_ceiling_ndvi_only_is_medium():
    # NDVI مصدر استقرائي سقفه medium ⇒ الثقة الكلّيّة medium لا high.
    state = compose_field_state("f", [SignalInput(source="ndvi", value=0.8)])
    assert state.confidence == "medium"


def test_confidence_lab_grade_soil_ec_is_high():
    # soil_ec يُترجَم لـ«ec» (مخبري) سقفه high ⇒ الثقة high.
    state = compose_field_state("f", [SignalInput(source="soil_ec", value=5.0)])
    assert state.confidence == "high"


def test_confidence_limited_by_weakest_source():
    # NDVI (medium) + soil_ec (high) ⇒ السقف الأدنى = medium يحكم.
    state = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.8), SignalInput(source="soil_ec", value=5.0)],
    )
    assert state.confidence == "medium"


# ── مقاومة السحاب (cloud-aware fusion): تحويل الوزن للرادار ──


def test_heavy_cloud_shifts_dominance_to_sar():
    # غطاء سحب 50% ⇒ الرادار (sar) يصبح العائلة المهيمنة (البصري مُخفّض الوزن).
    state = compose_field_state(
        "f",
        [
            SignalInput(source="ndvi", value=0.7),
            SignalInput(source="rvi", value=0.6),
            SignalInput(source="cloud_cover", value=50.0),
        ],
    )
    assert state.operational_truths["crop_vigor_dominant"] == "sar"
    assert state.operational_truths["cloud_cover_pct"] == 50.0


def test_clear_sky_keeps_optical_dominant():
    # بلا سحب ⇒ البصري (optical) يبقى مهيمناً (وزن متساوٍ، أوّل أعلى).
    state = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.7), SignalInput(source="rvi", value=0.6)],
    )
    assert state.operational_truths["crop_vigor_dominant"] == "optical"


# ── assess_economics: قاعدة «العائد < التكلفة ⇒ لا تدخّل» ──


def test_economics_justified_when_gain_exceeds_cost():
    # عائد 150 > تكلفة 100 ⇒ مُبرَّر اقتصاديّاً، نسبة العائد/التكلفة 1.5.
    result = assess_economics(EconomicContext(intervention_cost=100.0, expected_gain=150.0))
    assert result["benefit_cost_ratio"] == 1.5
    assert result["economically_justified"] is True
    assert "economic_note_ar" not in result


def test_economics_not_justified_emits_no_intervention_note():
    # عائد 80 < تكلفة 100 ⇒ غير مُبرَّر، مع ملاحظة «لا تدخّل» الصريحة.
    result = assess_economics(EconomicContext(intervention_cost=100.0, expected_gain=80.0))
    assert result["benefit_cost_ratio"] == 0.8
    assert result["economically_justified"] is False
    assert "economic_note_ar" in result


def test_economics_zero_cost_avoids_division_and_is_not_justified():
    # تكلفة صفر ⇒ لا قسمة (نسبة None)، وغير مُبرَّر (الشرط cost > 0 يفشل).
    result = assess_economics(EconomicContext(intervention_cost=0.0, expected_gain=80.0))
    assert result["benefit_cost_ratio"] is None
    assert result["economically_justified"] is False


def test_economics_input_costs_total_and_per_hectare():
    # يجمع الأرقام فقط (يتجاهل القيم غير العدديّة) ويحسب التكلفة لكلّ هكتار.
    result = assess_economics(
        EconomicContext(input_costs={"seeds": 100, "labor": 50, "bad": "x"}, area_ha=2.0)
    )
    assert result["input_cost_total"] == 150
    assert result["cost_per_hectare"] == 75.0


# ── state_to_event_row: سيادة البيانات تتطلّب tenant_id (RLS) ──


def test_state_to_event_row_requires_tenant_id():
    # حالة بلا tenant_id ⇒ ValueError (لا حفظ بلا مالك/RLS).
    state = compose_field_state("f", [SignalInput(source="ndvi", value=0.8)])
    raised = False
    try:
        state_to_event_row(state)
    except ValueError:
        raised = True
    assert raised


def test_state_to_event_row_builds_canonical_event():
    # صفّ حدث مطابق للمخطّط: نوع الحدث، الكيان، المستأجر، المصدر «ai»، الحمولة dict.
    state = compose_field_state("f1", [SignalInput(source="ndvi", value=0.8)], tenant_id="t1")
    row = state_to_event_row(state, actor_id="a1", command_id="c1")
    assert row["event_type"] == "field.canonical_state_computed"
    assert row["entity_type"] == "field"
    assert row["entity_id"] == "f1"
    assert row["tenant_id"] == "t1"
    assert row["actor_id"] == "a1"
    assert row["source"] == "ai"
    assert isinstance(row["payload"], dict)


# ── explain_decision + to_dict/from_dict (replay/audit lineage) ──


def test_explain_decision_surfaces_winning_rule_and_conflicts():
    # سلسلة التفسير تُظهر الحالة الفعليّة، القاعدة الفائزة، والتعارض المحسوم.
    state = compose_field_state(
        "f1",
        [SignalInput(source="ndvi", value=0.85), SignalInput(source="soil_ec", value=10.0)],
        tenant_id="t1",
    )
    explanation = state.explain_decision()
    assert explanation["decision"]["effective_status"] == "salinity_limited"
    assert explanation["decision"]["winning_rule"] == "SAL-SOIL-03"
    assert len(explanation["conflicts_resolved"]) == 1


def test_to_dict_from_dict_roundtrip_preserves_state():
    # التسلسل ثمّ إعادة البناء يحفظ الحقول الجوهريّة (للمقارنة الموسميّة/replay).
    state = compose_field_state(
        "f9",
        [SignalInput(source="ndvi", value=0.85), SignalInput(source="soil_ec", value=10.0)],
        tenant_id="t1",
    )
    rebuilt = CanonicalFieldState.from_dict(state.to_dict())
    assert rebuilt.field_id == "f9"
    assert rebuilt.tenant_id == "t1"
    assert rebuilt.operational_truths["effective_status"] == "salinity_limited"


# ── compare_seasons: مقارنة المتاح فقط + تنبيهات التدهور ──


def test_compare_seasons_flags_rising_salinity_and_vigor_drop():
    # حيويّة هابطة (-25%) وملوحة صاعدة ⇒ تنبيهان صريحان + دلتا محسوبة.
    current = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.6), SignalInput(source="soil_ec", value=12.0)],
        tenant_id="t1",
    )
    previous = compose_field_state(
        "f",
        [SignalInput(source="ndvi", value=0.8), SignalInput(source="soil_ec", value=2.0)],
        tenant_id="t1",
    )
    result = compare_seasons(current, previous)
    assert result["deltas"]["crop_vigor"]["delta"] == -0.2
    assert result["deltas"]["crop_vigor"]["pct_change"] == -25.0
    assert result["deltas"]["salinity_risk"]["delta"] == 0.63
    # تنبيها الملوحة الصاعدة والحيويّة الهابطة موجودان.
    assert any("الملوحة ترتفع" in n for n in result["notes_ar"])
    assert any("الحيويّة أدنى" in n for n in result["notes_ar"])


def test_compare_seasons_declares_metric_missing_in_one_season():
    # مقياس (kc) غائب في كلا الموسمين ⇒ يُعلَن «غير متاح» لا يُختلق دلتا له.
    current = compose_field_state("f", [SignalInput(source="ndvi", value=0.6)], tenant_id="t1")
    previous = compose_field_state("f", [SignalInput(source="ndvi", value=0.7)], tenant_id="t1")
    result = compare_seasons(current, previous)
    assert "kc" not in result["deltas"]
    assert any("kc" in n and "غير متاح" in n for n in result["notes_ar"])
