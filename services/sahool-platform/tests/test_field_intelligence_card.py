"""تحقّق V65 — بطاقة ذكاء الحقل الموحّدة (تجميع صادق، أقسام missing صريحة).

- كلّ قسم اختياريّ إمّا حاضر أو ``missing`` بسبب — لا اختلاق.
- NDVI الحاليّ مقابل التاريخيّ: شذوذ + تصنيف (فوق/تحت/قرب) عند توفّر تاريخ كافٍ.
- توصية الاستطلاع تتصاعد مع التنبيهات/المناطق الضعيفة.
- الاكتمال نسبة الأقسام الحاضرة؛ الأقسام المفقودة مُدرَجة.
- منطق صرف؛ يستهلك المُمرَّر فقط (لا جلب).
"""

from __future__ import annotations

from core.field_intelligence_card import assemble_field_intelligence_card

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
