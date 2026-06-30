from services.ai_agronomist.main import (
    _evidence_sources,
    _field_memory_evidence_ids,
    _grounding_context_text,
)


def _pack():
    return {
        "field_id": "field-1",
        "days": 730,
        "ai_context_summary_ar": "سياق الحقل خلال سنتين مع صور وطقس.",
        "imagery_timeline": {
            "total_dates": 8,
            "per_indicator": {"ndvi": {"total": 4}, "truecolor": {"total": 4}},
        },
        "weather_history": {
            "available": True,
            "summary": {
                "days": 730,
                "total_precipitation_mm": 122.5,
                "total_et0_mm": 1140.0,
                "avg_temp_c": 25.2,
            },
        },
        "operations_timeline": {"total": 3},
        "drawing_context": {"total": 2},
        "alerts_context": {"total": 1},
        "recommendations_context": {"total": 1},
        "readiness": {"warnings": ["warning-a"], "requires_imagery_backfill_24_months": False},
    }


def test_grounding_context_includes_two_year_field_memory():
    txt = _grounding_context_text(
        {"rag": [], "knowledge_graph": [], "canonical_field_state": {"ai_context_pack": _pack()}}
    )
    assert "ذاكرة الحقل لسنتين" in txt
    assert "المشاهد/المؤشرات التاريخية: 8" in txt
    assert "الطقس التاريخي: 730 يوم" in txt
    assert "warning-a" in txt


def test_field_memory_evidence_ids_are_explicit_and_bounded():
    ids = _field_memory_evidence_ids(_pack())
    assert "field-memory:field-1:imagery:8" in ids
    assert "field-memory:field-1:weather:730" in ids
    assert "field-memory:field-1:drawings:2" in ids


def test_evidence_sources_expose_user_facing_source_cards():
    sources = _evidence_sources(
        {"annotations": [{"id": "r1"}]},
        {"edges": [{"edge_id": "e1"}]},
        {"ai_context_pack": _pack()},
    )
    keys = {s["key"] for s in sources}
    assert {
        "rag",
        "knowledge_graph",
        "field_state",
        "imagery_timeline",
        "weather_history",
        "drawing_context",
    }.issubset(keys)
    assert next(s for s in sources if s["key"] == "imagery_timeline")["count"] == 8
