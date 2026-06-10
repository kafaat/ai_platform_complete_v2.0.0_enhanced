"""اختبارات وحدة خطّ أبحاث SAHOOL الزراعيّة.

Unit tests for the SAHOOL Agronomic Research Pipeline.
All tests are deterministic and use only stdlib + pydantic + pytest.
"""

from __future__ import annotations

import pytest

from sahool_ai.research import (
    CONNECTORS,
    CausalLink,
    Factor,
    SubQuery,
    Synthesis,
    decompose_query,
    extract_causal_links,
    extract_numeric_values,
    extract_temporal_patterns,
    generate_json_report,
    generate_map_data,
    generate_markdown_report,
    retrieve_all,
    run_pipeline,
    synthesize_findings,
)

# ── استعلام القانون (Canonical query) ────────────────────────────────────────
CANONICAL_QUERY = "لماذا انخفض NDVI في القطاع الشمالي؟"

# ── نتائج وهميّة كاملة للقطاع الشمالي ────────────────────────────────────────
NORTH_MOCK_RESULTS: dict = {
    "sentinel_hub": {
        "values": [0.72, 0.68, 0.61, 0.54, 0.49],
        "trend": "declining",
        "change_pct": -32.0,
        "dates": ["2026-05-01", "2026-05-08", "2026-05-15", "2026-05-22", "2026-05-29"],
    },
    "weather_api": {
        "rainfall_mm": 12.0,
        "avg_temp_c": 34.5,
        "anomalies": [
            {"type": "drought", "severity": "high"},
            {"type": "heat_wave", "severity": "medium"},
        ],
    },
    "soil_sensors": {
        "moisture_pct": 18.0,
        "ph": 7.8,
        "npk": {"n": 12.0, "p": 8.0, "k": 95.0},
    },
    "irrigation_logs": {
        "scheduled_events": 14,
        "actual_events": 6,
        "missed_days": [
            "2026-05-03",
            "2026-05-07",
            "2026-05-10",
            "2026-05-14",
            "2026-05-17",
            "2026-05-21",
            "2026-05-24",
            "2026-05-28",
        ],
        "adherence_pct": 42.9,
    },
    "qdrant_rag": {
        "documents": ["doc1", "doc2"],
        "sources": ["src1"],
        "confidence": 0.82,
    },
}

EMPTY_RESULTS: dict = {}


# ═══════════════════════════════════════════════════════════════════════════════
# DECOMPOSER TESTS
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_decomposer_canonical_query_sources() -> None:
    """الاستعلام القانوني يُنتج المصادر الخمسة المطلوبة."""
    sqs = decompose_query(CANONICAL_QUERY)
    sources = {sq.source for sq in sqs}
    expected = {"sentinel_hub", "weather_api", "soil_sensors", "irrigation_logs", "qdrant_rag"}
    assert sources == expected, f"مصادر مفقودة: {expected - sources}"


@pytest.mark.unit
def test_decomposer_canonical_query_region() -> None:
    """الاستعلام القانوني يُكتشف منه القطاع الشمالي."""
    sqs = decompose_query(CANONICAL_QUERY)
    regions = {sq.params.get("region") for sq in sqs if "region" in sq.params}
    assert "north_sector" in regions


@pytest.mark.unit
def test_decomposer_canonical_query_type() -> None:
    """الاستعلام القانوني يُنتج نوع ndvi_analysis."""
    sqs = decompose_query(CANONICAL_QUERY)
    types = {sq.type for sq in sqs}
    assert "ndvi_analysis" in types


@pytest.mark.unit
def test_decomposer_always_includes_qdrant_rag() -> None:
    """كلّ استعلام يشمل دائماً مصدر qdrant_rag."""
    for query in [
        CANONICAL_QUERY,
        "irrigation optimization needed",
        "تسميد النيتروجين",
        "unknown random text",
    ]:
        sqs = decompose_query(query)
        sources = {sq.source for sq in sqs}
        assert "qdrant_rag" in sources, f"qdrant_rag مفقود للاستعلام: {query}"


@pytest.mark.unit
def test_decomposer_yield_prediction_pattern() -> None:
    """نمط توقّع الإنتاج يُفعَّل بالكلمة المفتاحية العربية."""
    sqs = decompose_query("ما هو توقّع الغلّة هذا الموسم؟")
    types = {sq.type for sq in sqs}
    assert "yield_prediction" in types


@pytest.mark.unit
def test_decomposer_pest_alert_pattern() -> None:
    """نمط تنبيه الآفات يُفعَّل."""
    sqs = decompose_query("هناك آفات حشرات في الحقل")
    types = {sq.type for sq in sqs}
    assert "pest_alert" in types


@pytest.mark.unit
def test_decomposer_irrigation_optimization_pattern() -> None:
    """نمط تحسين الري يُفعَّل."""
    sqs = decompose_query("تحسين الري للمحاصيل")
    types = {sq.type for sq in sqs}
    assert "irrigation_optimization" in types


@pytest.mark.unit
def test_decomposer_soil_deficiency_pattern() -> None:
    """نمط نقص التربة يُفعَّل."""
    sqs = decompose_query("نقص المغذّيات في التربة")
    types = {sq.type for sq in sqs}
    assert "soil_deficiency" in types


@pytest.mark.unit
def test_decomposer_water_stress_pattern() -> None:
    """نمط الإجهاد المائي يُفعَّل."""
    sqs = decompose_query("الجفاف يضرب القطاع الغربي")
    types = {sq.type for sq in sqs}
    assert "water_stress" in types


@pytest.mark.unit
def test_decomposer_disease_pattern() -> None:
    """نمط مرض المحصول يُفعَّل."""
    sqs = decompose_query("انتشر مرض فطري في الحقل الشرقي")
    types = {sq.type for sq in sqs}
    assert "disease_detection" in types


@pytest.mark.unit
def test_decomposer_weed_pattern() -> None:
    """نمط الحشائش يُفعَّل."""
    sqs = decompose_query("الحشائش الضارّة تغطّي النصف الجنوبي")
    types = {sq.type for sq in sqs}
    assert "weed_detection" in types


@pytest.mark.unit
def test_decomposer_fertilizer_pattern() -> None:
    """نمط التسميد يُفعَّل بكلمة NPK الإنجليزية."""
    sqs = decompose_query("NPK levels are low in the field")
    types = {sq.type for sq in sqs}
    assert "fertilizer_recommendation" in types


@pytest.mark.unit
def test_decomposer_weather_anomaly_pattern() -> None:
    """نمط الشذوذ المناخي يُفعَّل."""
    sqs = decompose_query("شذوذ مناخي في منطقة الزراعة")
    types = {sq.type for sq in sqs}
    assert "weather_anomaly" in types


@pytest.mark.unit
def test_decomposer_english_ndvi_variant() -> None:
    """متغيّر NDVI الإنجليزي يُنتج نفس المصادر."""
    sqs = decompose_query("Why did NDVI decline in the northern sector?")
    sources = {sq.source for sq in sqs}
    assert "sentinel_hub" in sources
    assert "qdrant_rag" in sources
    regions = {sq.params.get("region") for sq in sqs if "region" in sq.params}
    assert "north_sector" in regions


@pytest.mark.unit
def test_decomposer_region_detection_all_directions() -> None:
    """كشف المناطق الأربع يعمل صحيحاً."""
    cases = [
        ("القطاع الجنوبي", "south_sector"),
        ("القطاع الشرقي", "east_sector"),
        ("القطاع الغربي", "west_sector"),
        ("north field", "north_sector"),
        ("southern region", "south_sector"),
        ("eastern area", "east_sector"),
        ("western zone", "west_sector"),
    ]
    for query, expected_region in cases:
        sqs = decompose_query(query)
        regions = {sq.params.get("region") for sq in sqs if "region" in sq.params}
        assert expected_region in regions, f"المنطقة {expected_region} لم تُكتشف في: {query!r}"


@pytest.mark.unit
def test_decomposer_fallback_generic_decomposition() -> None:
    """الاستعلام العامّ الذي لا يطابق أيّ نمط يُعطي decomposition احتياطيّاً."""
    sqs = decompose_query("xyz_completely_unknown_query_12345")
    sources = {sq.source for sq in sqs}
    # Fallback always includes sentinel_hub, weather_api, qdrant_rag
    assert "sentinel_hub" in sources
    assert "weather_api" in sources
    assert "qdrant_rag" in sources


@pytest.mark.unit
def test_decomposer_subquery_is_subquery_model() -> None:
    """كلّ عنصر في النتيجة هو نموذج SubQuery صحيح."""
    sqs = decompose_query(CANONICAL_QUERY)
    for sq in sqs:
        assert isinstance(sq, SubQuery)
        assert sq.source
        assert sq.type
        assert isinstance(sq.params, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# RETRIEVER TESTS
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_retriever_returns_all_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """retrieve_all يُرجع بيانات من كلّ مصدر مدرج في CONNECTORS."""
    sqs = decompose_query(CANONICAL_QUERY)
    results = retrieve_all(sqs)
    assert "sentinel_hub" in results
    assert "weather_api" in results
    assert "soil_sensors" in results
    assert "irrigation_logs" in results
    assert "qdrant_rag" in results


@pytest.mark.unit
def test_retriever_partial_results_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """retrieve_all يُكمل العمل ويُرجع نتائج جزئيّة عند فشل مصدر واحد."""

    def _failing_connector(params: dict, timeout: float = 10.0) -> dict:
        raise RuntimeError("محاكاة خطأ اتّصال")

    monkeypatch.setitem(CONNECTORS, "weather_api", _failing_connector)

    sqs = decompose_query(CANONICAL_QUERY)
    results = retrieve_all(sqs)

    # weather_api should contain error key
    assert "error" in results.get("weather_api", {})
    # Other sources should still return data
    assert "sentinel_hub" in results
    assert "error" not in results.get("sentinel_hub", {})


@pytest.mark.unit
def test_retriever_sentinel_hub_shape() -> None:
    """Sentinel Hub mock يُرجع الشكل الصحيح."""
    from sahool_ai.research.retriever import sentinel_hub_ndvi

    result = sentinel_hub_ndvi({"region": "north_sector"})
    assert "values" in result
    assert "trend" in result
    assert "change_pct" in result
    assert "dates" in result
    assert isinstance(result["values"], list)
    assert result["trend"] in ("declining", "stable", "improving")


@pytest.mark.unit
def test_retriever_weather_api_shape() -> None:
    """Weather API mock يُرجع الشكل الصحيح."""
    from sahool_ai.research.retriever import weather_api

    result = weather_api({"region": "north_sector"})
    assert "rainfall_mm" in result
    assert "avg_temp_c" in result
    assert "anomalies" in result
    assert isinstance(result["anomalies"], list)


@pytest.mark.unit
def test_retriever_soil_sensors_shape() -> None:
    """Soil sensors mock يُرجع الشكل الصحيح."""
    from sahool_ai.research.retriever import soil_sensors

    result = soil_sensors({"region": "north_sector"})
    assert "moisture_pct" in result
    assert "ph" in result
    assert "npk" in result
    assert all(k in result["npk"] for k in ("n", "p", "k"))


@pytest.mark.unit
def test_retriever_irrigation_logs_shape() -> None:
    """Irrigation logs mock يُرجع الشكل الصحيح."""
    from sahool_ai.research.retriever import irrigation_logs

    result = irrigation_logs({"region": "north_sector"})
    assert "scheduled_events" in result
    assert "actual_events" in result
    assert "missed_days" in result
    assert "adherence_pct" in result


@pytest.mark.unit
def test_retriever_qdrant_rag_shape() -> None:
    """Qdrant RAG mock يُرجع الشكل الصحيح."""
    from sahool_ai.research.retriever import qdrant_rag

    result = qdrant_rag({"query": "test", "collection": "agronomic_knowledge"})
    assert "documents" in result
    assert "sources" in result
    assert "confidence" in result
    assert isinstance(result["documents"], list)
    assert 0.0 <= result["confidence"] <= 1.0


@pytest.mark.unit
def test_retriever_unknown_source_returns_error() -> None:
    """مصدر غير معروف يُرجع قاموساً يحتوي على مفتاح error."""
    sqs = [SubQuery(type="test", source="unknown_source_xyz", params={})]
    results = retrieve_all(sqs)
    assert "error" in results.get("unknown_source_xyz", {})


@pytest.mark.unit
def test_retriever_monkeypatched_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    """يمكن استبدال الموصّلات عبر CONNECTORS للاختبار."""

    def _mock_sentinel(params: dict, timeout: float = 10.0) -> dict:
        return {"values": [0.9], "trend": "improving", "change_pct": 5.0, "dates": ["2026-06-01"]}

    monkeypatch.setitem(CONNECTORS, "sentinel_hub", _mock_sentinel)
    sqs = [SubQuery(type="ndvi_analysis", source="sentinel_hub", params={})]
    results = retrieve_all(sqs)
    assert results["sentinel_hub"]["trend"] == "improving"


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTOR TESTS
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_extractor_numeric_values_north_sector() -> None:
    """القيم الرقميّة مُستخرَجة بصحّة من بيانات القطاع الشمالي."""
    numeric = extract_numeric_values(NORTH_MOCK_RESULTS)
    assert numeric["ndvi_change_pct"] == pytest.approx(-32.0)
    assert numeric["ndvi_trend"] == "declining"
    assert numeric["rainfall_mm"] == pytest.approx(12.0)
    assert numeric["rainfall_deficit_mm"] == pytest.approx(68.0)  # 80 - 12
    assert numeric["soil_moisture_pct"] == pytest.approx(18.0)
    assert numeric["irrigation_adherence_pct"] == pytest.approx(42.9)
    assert numeric["irrigation_missed"] == 8
    assert numeric["rag_confidence"] == pytest.approx(0.82)


@pytest.mark.unit
def test_extractor_numeric_values_empty_data() -> None:
    """البيانات الفارغة لا تُسبّب خطأ وتُرجع قيماً افتراضيّة."""
    numeric = extract_numeric_values(EMPTY_RESULTS)
    assert numeric["ndvi_change_pct"] == 0.0
    assert numeric["rainfall_mm"] == 0.0
    assert numeric["rainfall_deficit_mm"] == 80.0  # full deficit
    assert numeric["irrigation_adherence_pct"] == 100.0
    assert numeric["rag_confidence"] == 0.0


@pytest.mark.unit
def test_extractor_numeric_values_error_source() -> None:
    """مصادر الخطأ تُعامَل كبيانات مفقودة بدون انهيار."""
    results = {
        "sentinel_hub": {"error": "اتّصال فاشل"},
        "weather_api": {"rainfall_mm": 50.0, "avg_temp_c": 28.0, "anomalies": []},
    }
    numeric = extract_numeric_values(results)
    assert numeric["ndvi_change_pct"] == 0.0
    assert numeric["rainfall_mm"] == pytest.approx(50.0)


@pytest.mark.unit
def test_extractor_temporal_patterns_north_sector() -> None:
    """الأنماط الزمنيّة مُستخرَجة بصحّة من بيانات القطاع الشمالي."""
    temporal = extract_temporal_patterns(NORTH_MOCK_RESULTS)
    assert "delay_events" in temporal
    assert "seasonal_deviation" in temporal
    assert "ndvi_dates" in temporal
    assert "missed_days" in temporal
    assert temporal["seasonal_deviation"] == "below_average"
    assert len(temporal["ndvi_dates"]) == 5


@pytest.mark.unit
def test_extractor_temporal_patterns_empty_data() -> None:
    """الأنماط الزمنيّة للبيانات الفارغة لا تُسبّب خطأ."""
    temporal = extract_temporal_patterns(EMPTY_RESULTS)
    assert temporal["delay_events"] == []
    assert temporal["seasonal_deviation"] == "normal"
    assert temporal["ndvi_dates"] == []
    assert temporal["missed_days"] == []


@pytest.mark.unit
def test_extractor_causal_links_north_sector() -> None:
    """الروابط السببيّة مُستنتَجة بصحّة من بيانات القطاع الشمالي."""
    links = extract_causal_links(NORTH_MOCK_RESULTS)
    assert len(links) > 0
    causes = {link.cause for link in links}
    # عجز مطري → انخفاض NDVI يجب أن يُستنتَج
    assert "عجز مطري" in causes


@pytest.mark.unit
def test_extractor_causal_links_confidence_range() -> None:
    """كلّ رابط سببي له ثقة في النطاق [0, 1]."""
    links = extract_causal_links(NORTH_MOCK_RESULTS)
    for link in links:
        assert isinstance(link, CausalLink)
        assert 0.0 <= link.confidence <= 1.0


@pytest.mark.unit
def test_extractor_causal_links_empty_data() -> None:
    """البيانات الفارغة لا تُسبّب انهياراً في الروابط السببيّة."""
    links = extract_causal_links(EMPTY_RESULTS)
    assert isinstance(links, list)
    # No links expected from empty data
    assert len(links) == 0


@pytest.mark.unit
def test_extractor_causal_links_conflicting_sources() -> None:
    """مصدر صحيح + مصدر خاطئ → نتائج جزئيّة بدون انهيار."""
    mixed_results = {
        "sentinel_hub": {
            "values": [0.7, 0.5],
            "trend": "declining",
            "change_pct": -28.0,
            "dates": ["2026-05-01", "2026-05-29"],
        },
        "weather_api": {"error": "timeout"},
    }
    links = extract_causal_links(mixed_results)
    assert isinstance(links, list)


# ═══════════════════════════════════════════════════════════════════════════════
# SYNTHESIZER TESTS
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_synthesizer_confidence_in_range() -> None:
    """الثقة الإجمالية في نطاق [0, 1]."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    assert 0.0 <= synthesis.confidence <= 1.0


@pytest.mark.unit
def test_synthesizer_recommendations_non_empty_arabic() -> None:
    """التوصيات غير فارغة وتحتوي على نصّ عربي."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    assert len(synthesis.recommendations) > 0
    # At least one recommendation should contain Arabic characters
    arabic_recs = [r for r in synthesis.recommendations if any("؀" <= c <= "ۿ" for c in r)]
    assert len(arabic_recs) > 0, "لا توصيات عربيّة وُجدت"


@pytest.mark.unit
def test_synthesizer_deterministic_output() -> None:
    """نفس المدخلات تُنتج دائماً نفس المخرجات (حتميّة كاملة)."""
    result1 = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    result2 = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    assert result1.summary == result2.summary
    assert result1.confidence == result2.confidence
    assert result1.recommendations == result2.recommendations
    assert len(result1.factors) == len(result2.factors)


@pytest.mark.unit
def test_synthesizer_returns_synthesis_model() -> None:
    """القيمة المُرجَعة هي نموذج Synthesis صحيح."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    assert isinstance(synthesis, Synthesis)
    assert isinstance(synthesis.factors, list)
    for f in synthesis.factors:
        assert isinstance(f, Factor)
        assert f.severity in ("low", "medium", "high")


@pytest.mark.unit
def test_synthesizer_empty_data_no_crash() -> None:
    """البيانات الفارغة لا تُسبّب انهياراً وتُرجع synthesis مع توصية."""
    synthesis = synthesize_findings(EMPTY_RESULTS, "استعلام فارغ")
    assert isinstance(synthesis, Synthesis)
    assert len(synthesis.recommendations) >= 1
    assert 0.0 <= synthesis.confidence <= 1.0


@pytest.mark.unit
def test_synthesizer_summary_contains_query() -> None:
    """الملخّص يحتوي على نصّ الاستعلام الأصلي."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    assert CANONICAL_QUERY in synthesis.summary


@pytest.mark.unit
def test_synthesizer_factors_have_valid_confidence() -> None:
    """كلّ عامل له ثقة في نطاق [0, 1]."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    for factor in synthesis.factors:
        assert 0.0 <= factor.confidence <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# REPORTER TESTS
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_reporter_json_expected_keys() -> None:
    """تقرير JSON يحتوي على المفاتيح المطلوبة."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    report = generate_json_report(synthesis)
    required_keys = {
        "summary",
        "factors",
        "recommendations",
        "confidence",
        "alert_level",
        "factor_count",
    }
    assert required_keys.issubset(report.keys()), f"مفاتيح مفقودة: {required_keys - report.keys()}"


@pytest.mark.unit
def test_reporter_json_confidence_rounded() -> None:
    """قيمة الثقة في تقرير JSON مُقرَّبة وفي النطاق الصحيح."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    report = generate_json_report(synthesis)
    assert 0.0 <= report["confidence"] <= 1.0


@pytest.mark.unit
def test_reporter_json_alert_level_valid() -> None:
    """مستوى التنبيه في تقرير JSON له قيمة صحيحة."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    report = generate_json_report(synthesis)
    assert report["alert_level"] in ("critical", "warning", "info")


@pytest.mark.unit
def test_reporter_markdown_contains_arabic_headers() -> None:
    """تقرير Markdown يحتوي على الأقسام العربيّة المطلوبة."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    md = generate_markdown_report(synthesis)
    assert "## الملخّص" in md
    assert "## العوامل" in md
    assert "## التوصيات" in md
    assert "## مستوى الثقة" in md


@pytest.mark.unit
def test_reporter_markdown_is_string() -> None:
    """generate_markdown_report تُرجع نصّاً."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    md = generate_markdown_report(synthesis)
    assert isinstance(md, str)
    assert len(md) > 0


@pytest.mark.unit
def test_reporter_map_data_valid_geojson() -> None:
    """map_data هو GeoJSON FeatureCollection صالح."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    gj = generate_map_data(synthesis, region="north_sector")
    assert gj["type"] == "FeatureCollection"
    assert "features" in gj
    assert isinstance(gj["features"], list)
    assert len(gj["features"]) >= 1


@pytest.mark.unit
def test_reporter_map_data_feature_structure() -> None:
    """كلّ Feature في GeoJSON لها geometry + properties صحيحتان."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    gj = generate_map_data(synthesis, region="north_sector")
    for feature in gj["features"]:
        assert feature["type"] == "Feature"
        assert "geometry" in feature
        assert "properties" in feature
        assert "type" in feature["geometry"]
        assert "coordinates" in feature["geometry"]
        assert "region" in feature["properties"]
        assert "alert_level" in feature["properties"]


@pytest.mark.unit
def test_reporter_map_data_no_region() -> None:
    """generate_map_data يعمل بدون منطقة محدَّدة."""
    synthesis = synthesize_findings(NORTH_MOCK_RESULTS, CANONICAL_QUERY)
    gj = generate_map_data(synthesis)
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE TESTS
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_pipeline_canonical_query_returns_expected_keys() -> None:
    """run_pipeline بالاستعلام القانوني يُرجع القاموس بمفاتيحه المطلوبة."""
    result = run_pipeline(CANONICAL_QUERY)
    assert "json" in result
    assert "markdown" in result
    assert "map_data" in result
    assert "query" in result
    assert "subquery_count" in result
    assert "sources_retrieved" in result


@pytest.mark.unit
def test_pipeline_canonical_query_json_valid() -> None:
    """json في نتيجة run_pipeline هو قاموس صحيح."""
    result = run_pipeline(CANONICAL_QUERY)
    assert isinstance(result["json"], dict)
    assert "summary" in result["json"]


@pytest.mark.unit
def test_pipeline_canonical_query_markdown_arabic() -> None:
    """markdown في نتيجة run_pipeline يحتوي على أقسام عربيّة."""
    result = run_pipeline(CANONICAL_QUERY)
    assert "## الملخّص" in result["markdown"]


@pytest.mark.unit
def test_pipeline_canonical_query_map_data_geojson() -> None:
    """map_data في نتيجة run_pipeline هو GeoJSON صالح."""
    result = run_pipeline(CANONICAL_QUERY)
    gj = result["map_data"]
    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) >= 1


@pytest.mark.unit
def test_pipeline_with_mocked_connectors(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_pipeline يعمل بموصّلات وهميّة مُستبدَلة عبر monkeypatch."""

    def _mock_sentinel(params: dict, timeout: float = 10.0) -> dict:
        return {
            "values": [0.8, 0.75],
            "trend": "stable",
            "change_pct": -6.25,
            "dates": ["2026-05-01", "2026-05-29"],
        }

    monkeypatch.setitem(CONNECTORS, "sentinel_hub", _mock_sentinel)
    result = run_pipeline("NDVI check for north")
    assert isinstance(result, dict)
    assert "json" in result


@pytest.mark.unit
def test_pipeline_subquery_count_positive() -> None:
    """عدد الاستعلامات الفرعيّة موجب."""
    result = run_pipeline(CANONICAL_QUERY)
    assert result["subquery_count"] > 0


@pytest.mark.unit
def test_pipeline_sources_retrieved_list() -> None:
    """sources_retrieved قائمة غير فارغة."""
    result = run_pipeline(CANONICAL_QUERY)
    assert isinstance(result["sources_retrieved"], list)
    assert len(result["sources_retrieved"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_models_confidence_clamping() -> None:
    """نماذج Pydantic تُطار قيم الثقة خارج [0,1]."""
    # CausalLink with confidence > 1 should be clamped to 1
    link = CausalLink(cause="test", effect="test", confidence=1.5, evidence=[])
    assert link.confidence == 1.0

    # Factor with negative confidence should be clamped to 0
    factor = Factor(name="test", description="test", severity="low", confidence=-0.5)
    assert factor.confidence == 0.0

    # Synthesis with confidence > 1 should be clamped to 1
    synth = Synthesis(summary="test", factors=[], recommendations=[], confidence=2.0)
    assert synth.confidence == 1.0
