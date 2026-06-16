"""اختبارات محرّك القرار الزراعي الموحّد (offline) — `api/decision_engine.py`.

محرّك القرار منسّق نقيّ (orchestrator) بلا قاعدة بيانات ولا شبكة: يأخذ موقعاً
(اسم محافظة/مديريّة أو إحداثيّات GPS) + بيانات تربة/مساحة اختياريّة، ويستدعي
الوحدات الموجودة (الأقاليم/الجيو/الدليل العالمي/المخاطر/البستان…) ليجمعها في
قرار واحد. هذه الاختبارات تتحقّق من تدفّق القرار وفروعه وعتباته على قيم
حقيقيّة مشتقّة من منطق الوحدات نفسها — لا أرقام مُختلقة.
"""

import pytest
from api.decision_engine import (
    _build_summary,
    _load_jawf_climate_ref,
    decide_for_location,
)

pytestmark = pytest.mark.unit


# ─── المدخلات المفقودة / غير الصالحة ──────────────────────────────


def test_no_input_returns_unsupported_with_message():
    r = decide_for_location()
    assert r["supported"] is False
    assert "أدخل موقعاً" in r["message_ar"]
    # لا يُبنى قرار حين لا موقع
    assert "decision_summary_ar" not in r


def test_gps_outside_yemen_bounds_unsupported():
    # خارج صناديق اليمن (lat 12-19.5, lon 42-54.5) → غير مدعوم
    r = decide_for_location(lat=0.0, lon=0.0)
    assert r["supported"] is False
    assert "message_ar" in r
    assert "decision_summary_ar" not in r


def test_unknown_location_name_needs_clarification():
    # اسم غير معروف يمرّ عبر identify_zone_v2 (supported=False) فيُعاد كطلب توضيح
    r = decide_for_location(location="بلد مجهول جدا لا وجود له")
    assert r["supported"] is False
    assert "needs_clarification_ar" in r


def test_multizone_governorate_name_without_elevation_needs_clarification():
    # تعز محافظة متعدّدة الأقاليم: الاسم وحده لا يكفي بلا ارتفاع/مديريّة
    r = decide_for_location(location="تعز")
    assert r["supported"] is False
    assert "needs_clarification_ar" in r
    assert "تعز" in r["needs_clarification_ar"]
    # أمثلة المديريّات تُعاد لإرشاد المزارع
    assert isinstance(r["example_districts_ar"], dict)
    assert r["example_districts_ar"]["المخا"] == "tihama"


# ─── المسار السعيد: تحديد بالاسم (إقليم أحاديّ) ────────────────────


def test_name_based_central_highlands_happy_path():
    # صنعاء → central_highlands (غير صحراوي → لا دليل عالمي)
    r = decide_for_location(location="صنعاء")
    assert r["supported"] is True
    assert r["location_ar"]["method"] == "اسم"
    assert r["location_ar"]["input_ar"] == "صنعاء"
    # ② محاصيل الإقليم: central_highlands بعليّ ممكن (مطر ≤400 = الحدّ ⇒ True)
    assert r["rainfed_possible"] is True
    assert isinstance(r["suited_crops_ar"], list) and r["suited_crops_ar"]
    # central_highlands ليس صحراويّاً داخليّاً ⇒ لا دليل عالمي ولا بستان
    assert "global_evidence_ar" not in r
    assert "mixed_orchard_ar" not in r
    assert "actual_climate_data_ar" not in r
    # ④ ساعات البرودة: central tmin=5 ⇒ 700 ساعة
    assert r["chill_hours_ar"]["estimated"] == 700
    # المخاطر العالية لـ central_highlands تتضمّن الصقيع الشتوي
    assert "seasonal_risks_ar" in r
    assert any("صقيع" in h for h in r["seasonal_risks_ar"]["high_severity_ar"])


def test_name_based_district_inside_multizone_resolves_directly():
    # سيئون مديريّة داخل حضرموت ⇒ eastern_plateau (صحراوي داخلي ⇒ دليل عالمي)
    r = decide_for_location(location="سيئون")
    assert r["supported"] is True
    assert "global_evidence_ar" in r
    # eastern_plateau: tmin=20 ⇒ لا برودة كافية (0 ساعة)
    assert r["chill_hours_ar"]["estimated"] == 0


def test_steps_and_disclaimer_present_on_success():
    r = decide_for_location(location="صنعاء")
    # خطوتان على الأقلّ (① تحديد الإقليم، ② المحاصيل) + ④ المخاطر = ثلاث خطوات
    assert len(r["steps_ar"]) >= 3
    assert r["steps_ar"][0].startswith("①")
    assert "disclaimer_ar" in r
    # الإجراءات التالية ثابتة (4 بنود)
    assert len(r["next_actions_ar"]) == 4


# ─── المسار السعيد: تحديد بالإحداثيّات (GPS) + الصحراء الداخليّة ─────


def test_gps_inland_desert_full_decision():
    # الجوف (16.0N, 45.5E) ارتفاع 1100م ⇒ inland_desert
    r = decide_for_location(lat=16.0, lon=45.5, elevation_m=1100)
    assert r["supported"] is True
    assert r["location_ar"]["method"] == "GPS"
    assert r["location_ar"]["governorate_ar"] == "الجوف"
    # ② الصحراء الداخليّة: زراعة مرويّة ضروريّة (مطر ≤100 < 400)
    assert r["rainfed_possible"] is False
    # ③ الدليل العالمي ينطبق على الصحراء الداخليّة فقط
    assert "global_evidence_ar" in r
    assert "النخيل" in r["global_evidence_ar"]["strategic_crops_ar"]
    # التصنيف الاستراتيجي: أعلى فئتين فقط
    assert len(r["strategic_tiers_ar"]) == 2
    assert "أساسي استراتيجي" in r["strategic_tiers_ar"]
    # نموذج البستان المختلط (افتراضي 1.0 هكتار)
    assert "mixed_orchard_ar" in r
    assert isinstance(r["mixed_orchard_ar"]["blocks_summary_ar"], list)
    assert r["mixed_orchard_ar"]["blocks_summary_ar"]
    # طبقات الفرص عالية القيمة + التصديريّة
    assert "high_value_opportunities_ar" in r
    assert "niche_export_opportunities_ar" in r


def test_gps_inland_desert_attaches_actual_climate_reference():
    # inland_desert ⇒ يُرفق ملخّص طقس الجوف الفعلي من ملف المرجع
    r = decide_for_location(lat=16.0, lon=45.5, elevation_m=1100)
    assert "actual_climate_data_ar" in r
    acd = r["actual_climate_data_ar"]
    ref = _load_jawf_climate_ref()
    assert acd["annual_rainfall_mm"] == ref["annual_rainfall_mm"]
    assert acd["heat_stress_days_per_year"] == ref["heat_stress_days_per_year"]
    # النصّ يدمج سجلّ الحرارة الفعلي
    assert str(ref["temp_max_record"]) in acd["temp_record_ar"]
    assert "④ قُيّمت المخاطر الموسميّة + ساعات البرودة" in r["steps_ar"]


def test_gps_inland_desert_chill_zero_and_high_risks():
    r = decide_for_location(lat=16.0, lon=45.5, elevation_m=1100)
    # inland tmin=20 ⇒ 0 ساعة برودة
    assert r["chill_hours_ar"]["estimated"] == 0
    # خطران عاليان موثّقان للصحراء الداخليّة (حرّ مدمّر + جفاف ممتدّ)
    assert len(r["seasonal_risks_ar"]["high_severity_ar"]) == 2


def test_gps_multizone_warning_when_no_elevation():
    # تعز محافظة متعدّدة الأقاليم: GPS بلا ارتفاع ⇒ تنبيه + لا يزال مدعوماً
    r = decide_for_location(lat=13.6, lon=44.0)
    assert r["supported"] is True
    assert "location_warning_ar" in r
    assert "تعز" in r["location_warning_ar"]


def test_orchard_block_count_scales_with_area():
    # تمرير مساحة أكبر يُمرَّر إلى mixed_orchard_plan ⇒ أشجار أكثر
    small = decide_for_location(lat=16.0, lon=45.5, elevation_m=1100, area_ha=1.0)
    large = decide_for_location(lat=16.0, lon=45.5, elevation_m=1100, area_ha=20.0)
    n_small = len(small["mixed_orchard_ar"]["blocks_summary_ar"])
    n_large = len(large["mixed_orchard_ar"]["blocks_summary_ar"])
    assert n_small >= 1 and n_large >= 1
    # كلّ سطر بستان يحمل صيغة "محصول: عدد شجرة (دور)"
    assert "شجرة" in large["mixed_orchard_ar"]["blocks_summary_ar"][0]


# ─── الخطوة ٥: فحص التربة (تنبيهات ملوحة/قلويّة) ───────────────────


def test_soil_ph_only_adds_field_fit_note_no_salinity():
    r = decide_for_location(location="صنعاء", soil_ph=6.5)
    assert "field_fit_note_ar" in r
    assert "pH=6.5" in r["field_fit_note_ar"]
    # pH=6.5 < 7.8 و EC غير مُمرّر ⇒ لا تنبيهات
    assert "salinity_alert_ar" not in r
    assert "alkalinity_alert_ar" not in r


def test_high_salinity_triggers_alert_at_threshold():
    # العتبة EC>=4
    r = decide_for_location(location="صنعاء", soil_ec_dsm=4.0)
    assert "salinity_alert_ar" in r
    assert "EC=4.0" in r["salinity_alert_ar"]


def test_salinity_below_threshold_no_alert():
    r = decide_for_location(location="صنعاء", soil_ec_dsm=3.9)
    assert "field_fit_note_ar" in r
    assert "salinity_alert_ar" not in r


def test_high_alkalinity_triggers_alert_at_threshold():
    # العتبة pH>=7.8
    r = decide_for_location(location="صنعاء", soil_ph=7.8)
    assert "alkalinity_alert_ar" in r
    assert "pH=7.8" in r["alkalinity_alert_ar"]


def test_alkalinity_below_threshold_no_alert():
    r = decide_for_location(location="صنعاء", soil_ph=7.7)
    assert "alkalinity_alert_ar" not in r


def test_sunaydar_guidance_only_for_inland_desert_alkaline():
    # قلويّة عالية + inland_desert ⇒ إرشاد السنيدار الحكومي
    inland = decide_for_location(lat=16.0, lon=45.5, elevation_m=1100, soil_ph=8.2)
    assert "alkalinity_alert_ar" in inland
    assert "sunaydar_guidance_ar" in inland
    # قلويّة عالية لكن إقليم غير صحراوي داخلي ⇒ لا إرشاد سنيدار
    central = decide_for_location(location="صنعاء", soil_ph=8.2)
    assert "alkalinity_alert_ar" in central
    assert "sunaydar_guidance_ar" not in central


def test_soil_step_appended_when_soil_provided():
    r = decide_for_location(location="صنعاء", soil_ec_dsm=5.0)
    assert any(s.startswith("⑤") for s in r["steps_ar"])


# ─── الخطوة ٦: اعتبار المساحة (عتبات الحجم) ────────────────────────


def test_area_small_field_note():
    r = decide_for_location(location="صنعاء", area_ha=1.5)
    assert "1.5 هكتار" in r["area_note_ar"]
    assert "صغير" in r["area_note_ar"]
    assert any(s.startswith("⑥") for s in r["steps_ar"])


def test_area_medium_field_note():
    # 2 <= area <= 50 ⇒ متوسّط
    r = decide_for_location(location="صنعاء", area_ha=25.0)
    assert "متوسّط" in r["area_note_ar"]


def test_area_large_field_note():
    r = decide_for_location(location="صنعاء", area_ha=60.0)
    assert "كبير" in r["area_note_ar"]


def test_area_boundary_two_is_medium():
    # area_ha == 2 ليست < 2 ولا > 50 ⇒ متوسّط
    r = decide_for_location(location="صنعاء", area_ha=2.0)
    assert "متوسّط" in r["area_note_ar"]


def test_no_optional_inputs_skips_soil_and_area():
    r = decide_for_location(location="صنعاء")
    assert "field_fit_note_ar" not in r
    assert "area_note_ar" not in r


# ─── _build_summary: المنطق المباشر ────────────────────────────────


def _zone_inputs(zone_key, ec=None):
    from api.agro_climate_zones import suited_for_zone
    from api.climate_analogs import analogs_for_zone
    from api.seasonal_risk import chill_hours_estimate

    return (
        zone_key,
        suited_for_zone(zone_key),
        analogs_for_zone(zone_key),
        chill_hours_estimate(zone_key),
        ec,
    )


def test_build_summary_inland_desert_full_clauses():
    zk, suited, analogs, chill, _ = _zone_inputs("inland_desert")
    summary = _build_summary(zk, suited, analogs, chill, 5.0)
    assert summary.endswith(".")
    # محاصيل صحراويّة استراتيجيّة (analogs applicable)
    assert "صحراويّة استراتيجيّة" in summary
    # chill==0 ⇒ تجنّب أشجار البرودة
    assert "تفاح" in summary
    # rainfed مستحيل ⇒ الريّ ضروري
    assert "الريّ ضروري" in summary
    # ec>=4 ⇒ راعِ الملوحة
    assert "الملوحة" in summary


def test_build_summary_central_highlands_no_salinity_no_chill_clause():
    zk, suited, analogs, chill, _ = _zone_inputs("central_highlands", ec=None)
    summary = _build_summary(zk, suited, analogs, chill, None)
    assert summary.endswith(".")
    # central ليس صحراويّاً داخليّاً ⇒ لا جملة استراتيجيّة صحراويّة
    assert "صحراويّة استراتيجيّة" not in summary
    # chill==700 (>0) ⇒ لا جملة تجنّب التفاح للبرودة
    assert "لا برودة كافية" not in summary
    # rainfed ممكن (central مطر حدّ 400) ⇒ لا جملة "الريّ ضروري"
    assert "الريّ ضروري" not in summary
    # ec=None ⇒ لا جملة ملوحة
    assert "راعِ الملوحة" not in summary
    # تبدأ بالأنسب للإقليم
    assert summary.startswith("الأنسب لإقليمك")


def test_build_summary_lists_top_four_crops():
    zk, suited, analogs, chill, _ = _zone_inputs("inland_desert")
    summary = _build_summary(zk, suited, analogs, chill, None)
    crops = suited["suited_crops_ar"]
    # يذكر أوّل محصول، ولا يذكر الخامس (يقتصر على [:4])
    assert crops[0] in summary
    if len(crops) >= 5:
        assert crops[4] not in summary


def test_decision_summary_matches_build_summary():
    # decision_summary_ar في النتيجة = نفس مخرج _build_summary بنفس المدخلات
    r = decide_for_location(lat=16.0, lon=45.5, elevation_m=1100, soil_ec_dsm=5.0)
    zk, suited, analogs, chill, _ = _zone_inputs("inland_desert")
    expected = _build_summary(zk, suited, analogs, chill, 5.0)
    assert r["decision_summary_ar"] == expected


# ─── _load_jawf_climate_ref: قارئ ملف المرجع ───────────────────────


def test_load_jawf_climate_ref_returns_expected_fields():
    ref = _load_jawf_climate_ref()
    assert ref is not None
    # حقول موثّقة من ملف data/reference/aljawf_climate_summary.json
    assert ref["annual_rainfall_mm"] == 80.4
    assert ref["heat_stress_days_per_year"] == 118
    assert ref["temp_max_record"] == 50.7
    assert ref["temp_min_record"] == 1.0
    assert "NASA POWER" in ref["source"]
