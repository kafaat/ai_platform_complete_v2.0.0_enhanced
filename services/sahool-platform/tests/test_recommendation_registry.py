"""اختبارات سجلّ محرّكات التوصيات (api.recommendations_hub) — منطق نقيّ.

يغطّي: الاستبطان (list_engines) للمحرّكات الخمسة، التوافق الخلفيّ (build_recommendations
بلا سياسة = نفس استدعاء البنّائين مباشرةً)، والتفعيل/التعطيل بالمُعرّف (enabled_ids).
لا حاجة لقاعدة أو شبكة — كلّ شيء offline.
"""

from datetime import date, timedelta

from api.recommendations_hub import (
    _REGISTRY,
    RecommendationContext,
    build_recommendations,
    list_engines,
)

# سياق يُشغّل ≥2 محرّك: ريّ (et0_mm) + أمراض (temp_c/humidity_pct) + تسميد (دائماً).
_CTX = RecommendationContext(
    field_id="f1",
    crop="wheat",
    stage="mid",
    et0_mm=8.0,
    soil_moisture_pct=20.0,
    temp_c=24.0,
    humidity_pct=88.0,
    rain_mm_3d=12.0,
    # **أُضيف المطرُ الآنيُّ والمتوقَّع إلى السياق «الكامل».** كانا يغيبان فيأخذان
    # `0.0` من العقد، فيقرأ محرّكُ الريّ «لا مطر» حيث الحقيقةُ «لا بيانات» — وهو
    # `IRRIGATION-READS-MISSING-RAIN-AS-NO-RAIN-01`. وبعد أن صار العقدُ
    # `float | None` صار غيابُهما يُصمِت المحرّك بحقّ، فوجب أن يحملهما سياقٌ
    # يدّعي الاكتمال. والصفرُ الصريح هنا **رصدٌ** لا غياب.
    rain_recent_mm=0.0,
    forecast_rain_mm=0.0,
    sowing_date=date.today() - timedelta(days=60),
)


def test_list_engines_returns_all_five() -> None:
    engines = list_engines()
    assert [e["id"] for e in engines] == [
        "irrigation",
        "fertilizer",
        "disease",
        "yield",
        "salinity_caution",
    ]
    by_id = {e["id"]: e for e in engines}
    assert by_id["irrigation"]["category"] == "irrigation"
    assert by_id["fertilizer"]["category"] == "fertilizer"
    assert by_id["disease"]["category"] == "disease"
    assert by_id["yield"]["category"] == "yield"
    assert by_id["salinity_caution"]["category"] == "irrigation"
    # metadata required_inputs مُشتقّة بصدق من بوّابة كلّ بنّاء.
    assert by_id["irrigation"]["required_inputs"] == [
        "et0_mm",
        "rain_recent_mm",
        "forecast_rain_mm",
    ]
    assert by_id["fertilizer"]["required_inputs"] == []
    assert by_id["disease"]["required_inputs"] == ["temp_c", "humidity_pct", "rain_mm_3d"]
    assert by_id["yield"]["required_inputs"] == ["sowing_date", "crop"]
    assert by_id["salinity_caution"]["required_inputs"] == ["salinity_class"]
    assert all(e["default_enabled"] for e in engines)


def test_no_policy_is_behaviour_identical_to_direct_builders() -> None:
    """build_recommendations(None) = نفس البنّائين بنفس الترتيب قبل الفرز."""
    direct = [r for e in _REGISTRY if (r := e.builder(_CTX)) is not None]
    via_hub = build_recommendations(_CTX)
    # نفس المجموعة (تطابق التوصيات نفسها) — يثبت أنّ السجلّ لا يضيف/يحذف شيئاً.
    assert {r.to_dict()["title_ar"] for r in via_hub} == {r.to_dict()["title_ar"] for r in direct}
    # السياق يُشغّل ≥2 محرّك (ريّ + تسميد + أمراض على الأقلّ).
    cats = {r.category for r in via_hub}
    assert {"irrigation", "fertilizer", "disease"}.issubset(cats)
    # الإخراج مفروز بالأولويّة (الأعلى أولاً) — ثبات العرض.
    prios = [r.priority for r in via_hub]
    order = {"high": 0, "medium": 1, "low": 2}
    assert prios == sorted(prios, key=lambda p: order[p])


def test_enabled_ids_filters_to_single_engine() -> None:
    recs = build_recommendations(_CTX, enabled_ids={"irrigation"})
    assert recs, "irrigation محرّك مُفعَّل ويجب أن يُنتج توصية مع هذا السياق"
    assert {r.category for r in recs} == {"irrigation"}


def test_empty_policy_returns_nothing() -> None:
    assert build_recommendations(_CTX, enabled_ids=set()) == []
