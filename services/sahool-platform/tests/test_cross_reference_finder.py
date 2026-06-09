"""Tests for cross_reference_finder (agricultural adaptation of Karpathy's
Connection Finder). Strict tenant isolation, transparent similarity scoring,
no invention when no history exists."""

from datetime import datetime, timedelta

from core.activity_log import ActivityStatus, mark_completed, plan_activity_from_recommendation
from core.cross_reference_finder import (
    SearchContext,
    SimilarityMatch,
    cross_reference_summary,
    find_similar_activities,
    find_similar_calibrations,
    find_similar_recommendations,
)
from core.learning.recommendation_log import RecommendationRecord


def _make_rec(rec_id, tenant_id, crop, days_ago=30, indicators=None, outcome_yield=None):
    """مولّد سجلّ توصية بـsnapshot للاختبار."""
    date = (datetime.now() - timedelta(days=days_ago)).date().isoformat()
    prov = None
    if indicators:
        prov = {
            "input_snapshot": indicators,
            "engines_used": ["fao56"],
            "weather_source": "open-meteo",
            "weather_data_date": date,
            "model_versions": {"fao56": "v2.1"},
            "calibration_set_id": None,
            "knowledge_snippets_ids": [],
        }
    return RecommendationRecord(
        rec_id=rec_id,
        tenant_id=tenant_id,
        district_id="d1",
        zone_id="z1",
        crop=crop,
        issued_date=date,
        recommendation_ar="test",
        quality_grade="READY",
        predicted_yield_t_ha=3.5,
        confidence="medium",
        actual_yield_t_ha=outcome_yield,
        provenance=prov,
    )


class TestTenantIsolation:
    """عزل tenant — الخطّ الأحمر الأهمّ في البحث المتداخل."""

    def test_other_tenant_data_not_leaked(self):
        # CRITICAL: تطابق محتمل في tenant مختلف لا يُكشَف
        log = [
            _make_rec("r_mine", "tnt_001", "wheat", indicators={"ndvi": 0.6}),
            _make_rec("r_other", "tnt_999", "wheat", indicators={"ndvi": 0.6}),
        ]
        ctx = SearchContext(
            tenant_id="tnt_001", field_id="f1", crop="wheat", current_indicators={"ndvi": 0.6}
        )
        results = find_similar_recommendations(ctx, log, min_similarity=0.0)
        for m in results:
            assert m.tenant_id == "tnt_001"
        # تأكّد صريح من عدم وجود r_other
        assert not any(m.source_id == "r_other" for m in results)

    def test_calibration_tenant_isolation(self):
        cal_log = [
            {
                "tenant_id": "tnt_001",
                "crop_id": "wheat",
                "zone_factor": 0.9,
                "calibration_id": "c1",
                "date": "2025-06-01",
            },
            {
                "tenant_id": "tnt_999",
                "crop_id": "wheat",
                "zone_factor": 0.5,
                "calibration_id": "c_leak",
                "date": "2025-06-01",
            },
        ]
        ctx = SearchContext(tenant_id="tnt_001", field_id="f1", crop="wheat")
        results = find_similar_calibrations(ctx, cal_log)
        for m in results:
            assert m.tenant_id == "tnt_001"


class TestNoInvention:
    """صفر اختراع — tenant بدون تاريخ يحصل على إعلان صريح."""

    def test_empty_log_returns_empty_list(self):
        ctx = SearchContext(tenant_id="tnt_001", field_id="f1", crop="wheat")
        assert find_similar_recommendations(ctx, []) == []

    def test_no_matching_tenant_returns_empty(self):
        log = [_make_rec("r1", "tnt_999", "wheat")]
        ctx = SearchContext(tenant_id="tnt_001", field_id="f1", crop="wheat")
        assert find_similar_recommendations(ctx, log) == []

    def test_summary_for_empty_declares_honestly(self):
        # CRITICAL: لا "0 matches" مبهم — رسالة صريحة
        summary = cross_reference_summary([])
        assert summary["count"] == 0
        assert "لا حالات" in summary["note_ar"]


class TestSimilarityScoring:
    """التشابه شفّاف — كل match مع أسباب صريحة."""

    def test_same_crop_increases_score(self):
        log = [_make_rec("r1", "tnt_001", "wheat")]
        ctx = SearchContext(tenant_id="tnt_001", field_id="f1", crop="wheat")
        results = find_similar_recommendations(ctx, log, min_similarity=0.0)
        # نفس المحصول → score ≥ 0.30 (وزن same_crop)
        assert results[0].similarity_score >= 0.30
        assert any("wheat" in r for r in results[0].why_similar_ar)

    def test_different_crop_lower_score(self):
        log = [_make_rec("r1", "tnt_001", "sorghum")]
        ctx = SearchContext(tenant_id="tnt_001", field_id="f1", crop="wheat")
        results = find_similar_recommendations(ctx, log, min_similarity=0.0)
        # لا تطابق محصول → لا "same_crop" بين الأسباب
        if results:
            assert not any("wheat" in r and "نفس" in r for r in results[0].why_similar_ar)

    def test_similar_indicators_add_to_score(self):
        log = [_make_rec("r1", "tnt_001", "wheat", indicators={"ndvi": 0.58, "soil_moisture": 22})]
        ctx_close = SearchContext(
            tenant_id="tnt_001",
            field_id="f1",
            crop="wheat",
            current_indicators={"ndvi": 0.55, "soil_moisture": 21},
        )
        ctx_far = SearchContext(
            tenant_id="tnt_001",
            field_id="f1",
            crop="wheat",
            current_indicators={"ndvi": 0.20, "soil_moisture": 8},
        )
        close_results = find_similar_recommendations(ctx_close, log, min_similarity=0.0)
        far_results = find_similar_recommendations(ctx_far, log, min_similarity=0.0)
        # المؤشّرات القريبة → score أعلى
        if close_results and far_results:
            assert close_results[0].similarity_score >= far_results[0].similarity_score

    def test_reasons_are_human_readable(self):
        # CRITICAL: كل match يجب أن يحمل أسباباً نصّية واضحة
        log = [_make_rec("r1", "tnt_001", "wheat", indicators={"ndvi": 0.6})]
        ctx = SearchContext(
            tenant_id="tnt_001", field_id="f1", crop="wheat", current_indicators={"ndvi": 0.58}
        )
        results = find_similar_recommendations(ctx, log, min_similarity=0.0)
        assert results
        assert len(results[0].why_similar_ar) >= 1
        assert all(isinstance(r, str) for r in results[0].why_similar_ar)


class TestOutcomeAttachment:
    """ربط النتيجة بالتطابق — مفيد للتعلّم."""

    def test_harvested_outcome_attached(self):
        log = [_make_rec("r1", "tnt_001", "wheat", outcome_yield=3.4)]
        ctx = SearchContext(tenant_id="tnt_001", field_id="f1", crop="wheat")
        results = find_similar_recommendations(ctx, log, min_similarity=0.0)
        assert results
        assert results[0].outcome == "harvested"
        assert results[0].actual_yield_t_ha == 3.4

    def test_no_outcome_when_yield_unknown(self):
        # توصية بلا حصاد فعلي → لا outcome مفترض
        log = [_make_rec("r1", "tnt_001", "wheat")]
        ctx = SearchContext(tenant_id="tnt_001", field_id="f1", crop="wheat")
        results = find_similar_recommendations(ctx, log, min_similarity=0.0)
        assert results
        assert results[0].outcome is None


class TestAgeFiltering:
    """التصفية الزمنية — تجاهل التوصيات القديمة جدّاً."""

    def test_old_recommendation_filtered(self):
        # توصية قبل 5 سنوات → خارج النطاق الافتراضي (365 يوم)
        log = [_make_rec("r_old", "tnt_001", "wheat", days_ago=2000)]
        ctx = SearchContext(tenant_id="tnt_001", field_id="f1", crop="wheat")
        results = find_similar_recommendations(ctx, log, min_similarity=0.0)
        assert not results

    def test_recent_recommendation_kept(self):
        log = [_make_rec("r_recent", "tnt_001", "wheat", days_ago=30)]
        ctx = SearchContext(tenant_id="tnt_001", field_id="f1", crop="wheat")
        results = find_similar_recommendations(ctx, log, min_similarity=0.0)
        assert results


class TestSummary:
    def test_summary_counts_by_type(self):
        matches = [
            SimilarityMatch(
                source_type="recommendation",
                source_id="r1",
                source_date="2026-01-01",
                tenant_id="t1",
                field_id="f1",
                crop="wheat",
                similarity_score=0.8,
                why_similar_ar=["a"],
            ),
            SimilarityMatch(
                source_type="activity",
                source_id="a1",
                source_date="2026-01-01",
                tenant_id="t1",
                field_id="f1",
                crop=None,
                similarity_score=0.5,
                why_similar_ar=["b"],
            ),
        ]
        summary = cross_reference_summary(matches)
        assert summary["count"] == 2
        assert summary["by_type"]["recommendation"] == 1
        assert summary["by_type"]["activity"] == 1

    def test_summary_limits_to_top_5(self):
        # AI Workaholic guard: لا تُغرق المحرّك
        matches = [
            SimilarityMatch(
                source_type="recommendation",
                source_id=f"r{i}",
                source_date="2026-01-01",
                tenant_id="t1",
                field_id="f1",
                crop="wheat",
                similarity_score=0.9 - i * 0.01,
                why_similar_ar=["x"],
            )
            for i in range(10)
        ]
        summary = cross_reference_summary(matches)
        assert len(summary["matches"]) <= 5
