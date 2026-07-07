"""تحقّق V65 — بطاقة ذكاء الحقل الموحّدة (تجميع صادق، أقسام missing صريحة).

- كلّ قسم اختياريّ إمّا حاضر أو ``missing`` بسبب — لا اختلاق.
- NDVI الحاليّ مقابل التاريخيّ: شذوذ + تصنيف (فوق/تحت/قرب) عند توفّر تاريخ كافٍ.
- توصية الاستطلاع تتصاعد مع التنبيهات/المناطق الضعيفة.
- الاكتمال نسبة الأقسام الحاضرة؛ الأقسام المفقودة مُدرَجة.
- منطق صرف؛ يستهلك المُمرَّر فقط (لا جلب).
"""

from __future__ import annotations

from core.field_intelligence_card import (
    assemble_field_intelligence_card,
    card_signals_from_db_rows,
    provider_status_signal,
    soil_baseline_signal,
)

_ANALYZE = {
    "field_id": "f-1",
    "generated_at": "2026-07-07T00:00:00Z",
    "confidence": 0.71,
    "confidence_reason": "3 live sources",
    "provenance": {"weather": {}, "soil": {}, "satellite": {}},
    "operational_truths": {"ndvi": 0.42, "water_deficit": 18.0},
    "alerts": [
        {"severity": "warning", "kind": "water_stress"},
        {"severity": "info", "kind": "note"},
    ],
}


def test_card_assembles_with_honest_missing_sections():
    card = assemble_field_intelligence_card(_ANALYZE)
    assert card["schema"] == "sahool.field_intelligence_card/1"
    assert card["field_id"] == "f-1"
    secs = card["sections"]
    # لا مشهد/حالة مزوّد مُمرَّرة ⇒ missing صريح (لا اختلاق).
    assert secs["latest_scene"]["status"] == "missing"
    assert secs["provider_status"]["status"] == "missing"
    # NDVI حاضر لكن بلا تاريخ ⇒ missing (insufficient_history).
    assert secs["ndvi_vs_historical"]["status"] == "missing"
    # العجز المائيّ من الحقائق التشغيليّة ⇒ حاضر.
    assert secs["water_deficit"]["status"] == "present"
    assert secs["water_deficit"]["value"] == 18.0
    assert "latest_scene" in card["missing_sections"]


def test_ndvi_vs_historical_labels_anomaly():
    card = assemble_field_intelligence_card(
        _ANALYZE, ndvi_current=0.70, ndvi_history=[0.40, 0.42, 0.41]
    )
    nvh = card["sections"]["ndvi_vs_historical"]
    assert nvh["status"] == "present"
    assert nvh["label"] == "above_historical"
    assert nvh["anomaly"] > 0
    assert nvh["n_history"] == 3


def test_below_and_near_historical_labels():
    below = assemble_field_intelligence_card(
        _ANALYZE, ndvi_current=0.20, ndvi_history=[0.45, 0.46, 0.44]
    )["sections"]["ndvi_vs_historical"]
    assert below["label"] == "below_historical"
    near = assemble_field_intelligence_card(
        _ANALYZE, ndvi_current=0.43, ndvi_history=[0.42, 0.43, 0.44]
    )["sections"]["ndvi_vs_historical"]
    assert near["label"] == "near_historical"


def test_latest_scene_and_provider_status_present_when_supplied():
    scene = {
        "scene_id": "S2_X",
        "acquisition_date": "2026-07-01T08:00:00Z",
        "provider": "element84",
        "cloud_cover": 4.0,
        "cog_ready": True,
    }
    card = assemble_field_intelligence_card(
        _ANALYZE, latest_scene=scene, provider_status={"element84": "active"}
    )
    assert card["sections"]["latest_scene"]["status"] == "present"
    assert card["sections"]["latest_scene"]["acquisition_date"] == "2026-07-01T08:00:00Z"
    assert card["sections"]["provider_status"]["status"] == "present"


def test_weak_zones_and_scouting_escalation():
    zones = [
        {"zone_id": "pz-low-1", "productivity_class": "low"},
        {"zone_id": "pz-high-1", "productivity_class": "high"},
    ]
    card = assemble_field_intelligence_card(_ANALYZE, weak_zones=zones)
    wz = card["sections"]["weak_zones"]
    assert wz["status"] == "present" and wz["count"] == 1 and wz["zone_ids"] == ["pz-low-1"]
    scout = card["sections"]["scouting_recommendation"]
    # تنبيه warning + منطقة ضعيفة ⇒ استطلاع عالي الأولويّة.
    assert scout["action"] == "scout" and scout["priority"] == "high"


def test_risk_alerts_and_confidence_always_present():
    card = assemble_field_intelligence_card(_ANALYZE)
    ra = card["sections"]["risk_alerts"]
    assert ra["count"] == 2 and ra["top_severity"] == "warning"
    assert card["sections"]["confidence"]["value"] == 0.71


def test_completeness_increases_with_more_signals():
    bare = assemble_field_intelligence_card({"field_id": "f"})["completeness"]
    rich = assemble_field_intelligence_card(
        _ANALYZE,
        latest_scene={"scene_id": "s"},
        provider_status={"element84": "active"},
        ndvi_current=0.5,
        ndvi_history=[0.4, 0.41],
        weak_zones=[{"zone_id": "z", "productivity_class": "low"}],
    )["completeness"]
    assert rich > bare


def test_empty_analyze_does_not_crash():
    card = assemble_field_intelligence_card({})
    assert card["completeness"] == 0.0
    assert card["sections"]["confidence"]["value"] is None
    assert card["sections"]["risk_alerts"]["count"] == 0


def test_field_condition_missing_without_diagnostic_truths():
    # صدق: _ANALYZE يحمل ndvi/water_deficit فقط (لا مفاتيح تشخيصيّة) ⇒ missing صريح.
    card = assemble_field_intelligence_card(_ANALYZE)
    assert card["sections"]["field_condition"]["status"] == "missing"
    assert card["sections"]["field_condition"]["reason"] == "no_condition_signals"


def test_field_condition_surfaces_precomputed_diagnosis():
    analyze = {
        "field_id": "f-2",
        "operational_truths": {
            "effective_status": "salinity_limited",
            "effective_status_reason": "ملوحة حرجة تحكم الحالة",
            "crop_vigor": 0.383,
            "crop_vigor_confidence": "medium",
            "salinity_class": "critical",
            "salinity_risk": 0.75,
            "heat_risk": 0.4,
            "ndvi_trend": "decreasing",
        },
    }
    fc = assemble_field_intelligence_card(analyze)["sections"]["field_condition"]
    assert fc["status"] == "present"
    assert fc["effective_status"] == "salinity_limited"
    assert fc["primary_driver"] == "salinity_limited"  # المُحرِّك = الحالة الفعليّة
    assert fc["salinity_class"] == "critical" and fc["salinity_risk"] == 0.75
    assert fc["crop_vigor"] == 0.383 and fc["ndvi_trend"] == "decreasing"


def test_field_condition_infers_driver_from_risk_when_no_status():
    # لا effective_status لكن ملوحة حرجة ⇒ يُستنتَج المُحرِّك (صدق: من دليل حاضر لا تخمين).
    analyze = {"operational_truths": {"salinity_class": "critical", "salinity_risk": 0.9}}
    fc = assemble_field_intelligence_card(analyze)["sections"]["field_condition"]
    assert fc["status"] == "present" and fc["primary_driver"] == "salinity_limited"
    # حرارة شديدة بلا حالة ⇒ heat_limited.
    hot = assemble_field_intelligence_card({"operational_truths": {"heat_risk": 0.85}})["sections"][
        "field_condition"
    ]
    assert hot["primary_driver"] == "heat_limited"


# ── P1 cross-service: خطّ أساس التربة SoilGrids (منطق صرف + سقوط آمن) ──────────────
def test_soil_baseline_signal_from_soilgrids_response():
    resp = {
        "source": "soilgrids",
        "properties": {
            "clay_pct": 22.5,
            "sand_pct": 40.0,
            "silt_pct": 37.5,
            "ph": 7.4,
            "soc_pct": 1.2,
            "cec": 18.0,
        },
        "texture": {"key": "loam", "label_ar": "طَفال"},
    }
    sig = soil_baseline_signal(resp)
    assert sig["texture"] == "طَفال" and sig["clay_pct"] == 22.5 and sig["ph"] == 7.4
    card = assemble_field_intelligence_card({"field_id": "f"}, soil_baseline=sig)
    sb = card["sections"]["soil_baseline"]
    assert sb["status"] == "present" and sb["clay_pct"] == 22.5
    # صدق: تحذير خطّ الأساس 250م حاضر (ليس بديل مختبر).
    assert "250" in sb["warning"]


def test_soil_baseline_signal_honest_when_unavailable():
    # soil-service متعذّر (None)/مشوّه ⇒ {} ⇒ القسم يبقى missing بصدق (لا اختلاق).
    assert soil_baseline_signal(None) == {}
    assert soil_baseline_signal({"error": "soilgrids_unavailable"}) == {}
    assert soil_baseline_signal({"properties": {}}) == {}
    card = assemble_field_intelligence_card(
        {"field_id": "f"}, soil_baseline=soil_baseline_signal(None)
    )
    assert card["sections"]["soil_baseline"]["status"] == "missing"
    assert card["sections"]["soil_baseline"]["reason"] == "no_soil_baseline_supplied"


# ── P1: تغذية البطاقة من صفوف DB (منطق صرف) ──────────────────────────────────────
def test_card_signals_from_db_rows_builds_scene_and_ndvi():
    ndvi_rows = [{"mean": 0.62}, {"mean": 0.55}, {"mean": 0.58}]  # تنازليّ بالتاريخ
    scene = {
        "scene_id": "S2_X",
        "acquisition_date": "2026-07-01",
        "cloud_pct": 4.0,
        "provider": "element84",
        "has_cog": True,
    }
    sig = card_signals_from_db_rows(ndvi_rows, scene)
    assert sig["ndvi_current"] == 0.62 and sig["ndvi_history"] == [0.62, 0.55, 0.58]
    assert sig["latest_scene"]["scene_id"] == "S2_X"
    # مُغذّاة إلى البطاقة ⇒ أقسام حاضرة (لا missing).
    card = assemble_field_intelligence_card({"field_id": "f"}, **sig)
    assert card["sections"]["latest_scene"]["status"] == "present"
    assert card["sections"]["ndvi_vs_historical"]["status"] == "present"


def test_card_signals_empty_when_no_data():
    # صدق: لا بيانات ⇒ إشارات فارغة ⇒ أقسام البطاقة تبقى missing (لا اختلاق).
    assert card_signals_from_db_rows([], None) == {}
    assert card_signals_from_db_rows(None, None) == {}
    card = assemble_field_intelligence_card(
        {"field_id": "f"}, **card_signals_from_db_rows([], None)
    )
    assert card["sections"]["latest_scene"]["status"] == "missing"


# ── P1 cross-service: provider_status من استجابة raster (منطق صرف + سقوط آمن) ──────
def test_provider_status_signal_from_raster_response():
    resp = {
        "default_historical_provider": "element84",
        "active": ["element84", "cdse", "local_cog"],
        "planned": ["wapor", "nasa_hls"],
    }
    sig = provider_status_signal(resp)
    assert sig["default"] == "element84"
    assert "element84" in sig["active"] and "wapor" in sig["planned"]
    # مُغذّى ⇒ قسم provider_status حاضر في البطاقة.
    card = assemble_field_intelligence_card({"field_id": "f"}, provider_status=sig)
    assert card["sections"]["provider_status"]["status"] == "present"


def test_provider_status_signal_honest_when_raster_unavailable():
    # raster متعذّر (None) أو استجابة مشوّهة ⇒ {} ⇒ القسم يبقى missing بصدق (لا اختلاق).
    assert provider_status_signal(None) == {}
    assert provider_status_signal({"nope": 1}) == {}
    card = assemble_field_intelligence_card(
        {"field_id": "f"}, provider_status=provider_status_signal(None)
    )
    assert card["sections"]["provider_status"]["status"] == "missing"
