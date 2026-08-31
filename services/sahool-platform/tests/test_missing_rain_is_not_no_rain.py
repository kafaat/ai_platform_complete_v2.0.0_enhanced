"""IRRIGATION-READS-MISSING-RAIN-AS-NO-RAIN-01 — الغيابُ لا يُقرأ «لا مطر».

**العطلُ مقيسٌ بالتنفيذ لا موصوفٌ.** مطرٌ غائبٌ يصل الحسابَ صفراً فيُعطي
`recommended_mm=7.5` و`urgency=moderate` و«خلال ٢٤ ساعة» — **أمرَ ريٍّ صريحاً**؛
وبالقراءة الحقيقيّة (١٢مم) يُعطي `0.0` و«لا حاجة للريّ». فالانحيازُ في اتّجاه
**الإذن**: غيابُ القياس يُنتِج ريّاً لا منعاً، وذلك في منطقةٍ شحيحة الماء.
وأسوأُ من الرقم أنّ `rationale_ar` **لا يذكر المطرَ بحرفٍ** عند الصفر، فيُقرأ
«حُسِب ولا مطرَ يُخصَم» لا «لا نعلم».

**وكان العلاجُ موجوداً في مسارٍ واحد فقط:** `field_workspace_weather` يفشل مغلقاً
(`WEATHER_PRECIPITATION_INCOMPLETE`)، بينما `fields.py` و`main.py` و
`recommendations_hub` تجمع `sum(... or 0.0)` بلا حارس — **علاجٌ ضيّقٌ تحت فجوةٍ
عريضة**، فالمزارعُ يُسقى أو لا يُسقى بحسب أيّ مسارٍ سأل.

وهذا الملفّ يقيس السلسلةَ لا موضعاً: **العقدُ** يقبل الغياب · **السياسةُ** واحدةٌ
لا ثلاث · **القرارُ** يصمت أو يفشل مغلقاً · و**الصفرُ المرصود يبقى رصداً**.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.connectors.openmeteo import _build_daily  # noqa: E402
from api.recommendations_hub import (  # noqa: E402
    RecommendationContext,
    build_recommendations,
    list_engines,
)
from api.weather_advice import (  # noqa: E402
    complete_rain_total,
    irrigation_advice,
    precipitation_incomplete_detail,
)

pytestmark = pytest.mark.unit


# ── ① الحافّة: العقدُ يقبل الغياب، ولا يُختلَق صفر ────────────────────
def test_the_edge_no_longer_invents_zero_for_an_absent_rain_reading():
    """**يُقاس موضعُ البناء لا الدالّةُ المساعدة — وهذا فرقٌ قِيس بالزرع.**

    أوّلُ صياغةٍ استدعت `_daily_at(..., None)` مُمرِّرةً الافتراضَ بيدها، فكانت
    تقيس سلوكَ المساعِدة لا ما يطلبه موضعُ الاستدعاء. زُرِعت عودةُ الحافّة إلى
    `_daily_at(..., i, 0)` **فنجت الطفرة**. فصار القياسُ على `_build_daily` نفسِها:
    حمولةٌ بلا `precipitation_sum` ⇒ `None`، ولا يُقبَل صفرٌ مكانَها.
    """
    payload = {
        "temperature_2m_max": [30.0],
        "temperature_2m_min": [18.0],
        "et0_fao_evapotranspiration": [5.0],
        "wind_speed_10m_max": [3.0],
        "weather_code": [0],
    }
    day = _build_daily(payload, 0, "2026-03-01")
    assert day.precipitation_mm is None, "غيابُ المطر اختُلِق صفراً عند الحافّة"

    observed = _build_daily({**payload, "precipitation_sum": [0.0]}, 0, "2026-03-01")
    assert observed.precipitation_mm == 0.0, "صفرٌ مرصودٌ ضاع"
    measured = _build_daily({**payload, "precipitation_sum": [4.0]}, 0, "2026-03-01")
    assert measured.precipitation_mm == 4.0


def test_a_context_that_omits_rain_is_unknown_rain_not_no_rain():
    """**العقدُ يُقاس بإغفاله لا بتمريره `None`.**

    الطفرةُ التي نجت أوّلاً أعادت `rain_recent_mm: float = 0.0`؛ وبايثون لا يفرض
    التصنيف وقتَ التشغيل، فتمريرُ `None` صراحةً يمرّ في الحالين ولا يقيس شيئاً.
    والفرقُ الحقيقيُّ في **الافتراض**: مستدعٍ لم يُمرِّر مطراً كان يحصل على `0.0`
    صامتاً — أي «لا مطر» من «لا بيانات». فيُبنى السياقُ هنا بلا حقول المطر أصلاً.
    """
    ctx = RecommendationContext(
        field_id="f1", crop="wheat", stage="mid", et0_mm=8.0, soil_moisture_pct=20.0
    )
    assert ctx.rain_recent_mm is None, "عقدٌ يختلق «لا مطر» لمستدعٍ لم يذكر المطر"
    assert ctx.forecast_rain_mm is None
    assert ctx.rain_mm_3d is None
    assert "irrigation" not in {r.category for r in build_recommendations(ctx)}


# ── ② السياسة: واحدةٌ، والصفرُ المرصود ليس غياباً ─────────────────────
def test_a_complete_series_totals_and_an_incomplete_one_names_its_gaps():
    assert complete_rain_total([1.0, 2.0, 3.0], expected_count=3) == (6.0, [])
    assert complete_rain_total([1.0, None, 3.0], expected_count=3) == (None, [1])
    # سلسلةٌ أقصر من المتوقَّع: الفترةُ الغائبةُ تُسمّى ولا تُعَدّ صفراً.
    assert complete_rain_total([1.0], expected_count=3) == (None, [1, 2])


def test_an_observed_zero_is_an_observation_not_a_gap():
    """الوجهُ الآخر للعقد — بلا هذا يصير الحارسُ إزعاجاً يُلتَفّ عليه.

    «لا مطر» قراءةٌ فيزيائيّة مشروعة، وحارسٌ يُحمِّر على الصفر المرصود يمنع
    توصيةً صحيحة في كلّ يومٍ جافّ.
    """
    assert complete_rain_total([0.0, 0.0], expected_count=2) == (0.0, [])


def test_the_fail_closed_error_body_is_one_shape():
    """رمزٌ واحدٌ للعطل الواحد — لا يُبلَّغ في مسارين برمزين."""
    detail = precipitation_incomplete_detail(
        context="field_irrigation_advice", missing_intervals=[0]
    )
    assert detail["code"] == "WEATHER_PRECIPITATION_INCOMPLETE"
    assert detail["missing_intervals"] == [0]
    assert detail["context"] == "field_irrigation_advice"


def test_the_workspace_router_delegates_instead_of_holding_a_second_judgement():
    """حكمان لحقيقةٍ واحدة ينحرفان — فالمسارُ يستخرج ويُفوّض، ولا يُعيد الحكم.

    **ويُتخطّى هذا وحدَه محلّيّاً لا في CI:** الموجِّه يستورد `fastapi`، وهي
    مُثبَّتةٌ في وظيفة *Platform Unit Tests* (`api/requirements.txt:6`) وغائبةٌ عن
    حاويتي. فـ«لم يُقَس هنا» يُعلَن ولا يُقرأ نجاحاً — وبقيّةُ الملفّ نقيّةٌ تعمل
    في الحالين.
    """
    pytest.importorskip("fastapi", reason="مُثبَّتةٌ في CI — انظر api/requirements.txt")
    from api.routers import field_workspace_weather as fww

    observed, missing = fww._complete_precipitation_total(
        [{"precipitation_mm": 1.0}, {"precipitation_mm": 2.0}], expected_count=2
    )
    assert (observed, missing) == (3.0, [])
    assert fww._complete_precipitation_total(
        [{"precipitation_mm": None}, {"precipitation_mm": 2.0}], expected_count=2
    ) == (None, [0])


# ── ③ القرار: الاتّجاه الذي يجعل العطل خطراً لا إزعاجاً ───────────────
def test_the_zero_coercion_would_have_ordered_an_irrigation_the_reading_forbids():
    """المرجعُ المضادّ — مكتوبٌ لأنّ الفرقَ هو الحمولة كلُّها.

    بلا مقارنةٍ يبدو التأكيدُ أدناه وصفاً لسلوكٍ عاديّ لا لعطلٍ أُصلِح.
    """
    invented = irrigation_advice(
        et0_mm=6.5,
        crop="tomato",
        stage="mid_season",
        rain_recent_mm=0.0,
        forecast_rain_mm=0.0,
        soil_moisture_pct=None,
    )
    measured = irrigation_advice(
        et0_mm=6.5,
        crop="tomato",
        stage="mid_season",
        rain_recent_mm=12.0,
        forecast_rain_mm=12.0,
        soil_moisture_pct=None,
    )
    assert invented["recommended_mm"] > 0 and invented["urgency"] != "none"
    assert measured["recommended_mm"] == 0.0 and measured["urgency"] == "none"
    # والتعليلُ عند الصفر لا يذكر المطرَ — فيُقرأ حساباً لا جهلاً.
    assert "المطر" not in invented["rationale_ar"]


def test_an_unknown_rain_silences_the_irrigation_recommendation():
    """لا رقمَ يُقدَّم على مطرٍ مجهول — والصمتُ هنا صدقٌ لا تعطيل."""
    base = dict(field_id="f1", crop="wheat", stage="mid", et0_mm=8.0, soil_moisture_pct=20.0)
    known = build_recommendations(
        RecommendationContext(**base, rain_recent_mm=0.0, forecast_rain_mm=0.0)
    )
    assert "irrigation" in {r.category for r in known}, "الحالةُ السويّة انكسرت"

    for missing in (
        {"rain_recent_mm": None, "forecast_rain_mm": 0.0},
        {"rain_recent_mm": 0.0, "forecast_rain_mm": None},
    ):
        recs = build_recommendations(RecommendationContext(**base, **missing))
        assert "irrigation" not in {r.category for r in recs}, f"أُوصيَ بالريّ ومطرٌ مجهول: {missing}"


def test_an_unknown_three_day_rain_silences_the_disease_recommendation():
    """المطرُ يدخل تهديفَ الخطر — وتصفيرُه ينحاز إلى **عدم** التحذير."""
    base = dict(field_id="f1", crop="wheat", stage="mid", temp_c=24.0, humidity_pct=88.0)
    known = build_recommendations(RecommendationContext(**base, rain_mm_3d=12.0))
    assert "disease" in {r.category for r in known}, "الحالةُ السويّة انكسرت"

    unknown = build_recommendations(RecommendationContext(**base, rain_mm_3d=None))
    assert "disease" not in {r.category for r in unknown}


def test_an_unknown_rain_silences_the_disease_alert_rule():
    """نفسُ الحكم في محرّك التنبيهات — لا يختلف الجوابُ بحسب أيّ سطحٍ سأل."""
    from api.alert_rules import AlertThresholds, FieldAlertContext, _disease_risk

    t = AlertThresholds()
    base = dict(field_id="f1", crop="wheat", temp_c=24.0, humidity_pct=88.0)
    assert _disease_risk(FieldAlertContext(**base, rain_mm_3d=None), t) is None


# ── ④ الإعلانُ يطابق الإنفاذ — وإلّا كان العلاجُ عطلاً من صنفه ────────
def test_the_declared_required_inputs_name_every_input_the_engine_actually_gates_on():
    """قاعدةٌ حقيقيّةٌ تحت وصفٍ يُطمئن هي عين ما تُغلقه هذه الشريحة.

    فلو ضُمّ المطرُ إلى الإنفاذ ولم يُضَمّ إلى الإعلان، لَقال `list_engines()`
    إنّ الريّ يحتاج `et0_mm` وحدَه — ويقرأ المستبطِنُ ذلك عقداً.
    """
    by_id = {e["id"]: e for e in list_engines()}
    assert set(by_id["irrigation"]["required_inputs"]) >= {
        "et0_mm",
        "rain_recent_mm",
        "forecast_rain_mm",
    }
    assert set(by_id["disease"]["required_inputs"]) >= {"temp_c", "humidity_pct", "rain_mm_3d"}
