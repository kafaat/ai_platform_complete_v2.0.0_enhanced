"""Tests for recommendation_replay (forensic agriculture).
Reviewers identified this as 'more important than ISOXML/K-Means/ML': why was
the recommendation issued? Can we replay it accurately 8 months later?
Principle: missing provenance → declared explicitly, never invented."""

from core.learning.recommendation_log import RecommendationRecord
from core.recommendation_replay import audit_chain, detect_drift, explain_recommendation


def _make_rec_with_provenance(rec_id="r1", versions=None, snapshot=None):
    """مولّد سجلّ توصية بـprovenance كاملة لتسهيل الاختبارات."""
    return RecommendationRecord(
        rec_id=rec_id,
        tenant_id="t1",
        district_id="d1",
        zone_id="z1",
        crop="wheat",
        issued_date="2026-05-28",
        recommendation_ar="اروِ 20مم",
        quality_grade="READY",
        predicted_yield_t_ha=3.5,
        confidence="medium",
        provenance={
            "model_versions": versions or {"fao56": "v2.1", "wofost": "7.2"},
            "weather_source": "open-meteo",
            "weather_data_date": "2026-05-28",
            "input_snapshot": snapshot or {"ndvi": 0.6, "ec": 1.2},
            "engines_used": ["fao56", "wofost"],
            "calibration_set_id": "cal_v1",
            "knowledge_snippets_ids": [],
        },
    )


def _make_rec_without_provenance():
    """توصية قديمة بلا تتبّع — للاختبار الحرج 'لا اختراع'."""
    return RecommendationRecord(
        rec_id="r_old",
        tenant_id="t1",
        district_id="d1",
        zone_id="z1",
        crop="wheat",
        issued_date="2025-03-01",
        recommendation_ar="توصية قديمة",
        quality_grade="LIMITED",
        predicted_yield_t_ha=None,
        confidence="low",
    )


class TestExplainRecommendation:
    def test_traced_recommendation_explained(self):
        rec = _make_rec_with_provenance()
        result = explain_recommendation(rec)
        assert result["has_provenance"]
        assert "fao56" in result["explanation_ar"]
        assert "open-meteo" in result["explanation_ar"]

    def test_untraced_recommendation_declares_honestly(self):
        # CRITICAL: لا اختراع — توصية بلا تتبّع تُعلن ذلك صراحةً
        rec = _make_rec_without_provenance()
        result = explain_recommendation(rec)
        assert not result["has_provenance"]
        assert "قبل تفعيل التتبّع" in result["explanation_ar"]

    def test_explanation_includes_input_snapshot(self):
        rec = _make_rec_with_provenance(snapshot={"ndvi": 0.55, "soil_moisture": 22.0})
        result = explain_recommendation(rec)
        assert "0.55" in result["explanation_ar"]
        assert "22.0" in result["explanation_ar"]

    def test_explanation_lists_engines_used(self):
        rec = _make_rec_with_provenance()
        result = explain_recommendation(rec)
        assert "fao56" in result["explanation_ar"]
        assert "wofost" in result["explanation_ar"]


class TestDriftDetection:
    def test_same_versions_no_drift(self):
        # النسخ متطابقة → النموذج مستقرّ
        rec = _make_rec_with_provenance(versions={"fao56": "v2.1", "wofost": "7.2"})
        report = detect_drift(rec, {"fao56": "v2.1", "wofost": "7.2"})
        assert not report.drift_detected
        assert report.consistency_check["status"] == "stable"

    def test_version_change_detects_drift(self):
        # CRITICAL: تطوّر نسخة محرّك = انحراف يجب إعلانه
        rec = _make_rec_with_provenance(versions={"fao56": "v2.1", "wofost": "7.2"})
        report = detect_drift(rec, {"fao56": "v2.3", "wofost": "7.2"})
        assert report.drift_detected
        assert len(report.drift_reasons_ar) == 1
        assert "fao56" in report.drift_reasons_ar[0]
        assert "v2.1" in report.drift_reasons_ar[0]
        assert "v2.3" in report.drift_reasons_ar[0]

    def test_multiple_drifts_all_reported(self):
        # كل محرّك متغيّر يُعلَن (لا إخفاء)
        rec = _make_rec_with_provenance(
            versions={"fao56": "v2.1", "wofost": "7.2", "fuzzy": "v1.0"}
        )
        report = detect_drift(rec, {"fao56": "v2.3", "wofost": "7.3", "fuzzy": "v1.0"})
        assert report.drift_detected
        assert len(report.drift_reasons_ar) == 2  # fao56 و wofost

    def test_untraced_recommendation_no_false_drift(self):
        # CRITICAL: توصية بلا provenance → لا نُعلن drift كذباً
        rec = _make_rec_without_provenance()
        report = detect_drift(rec, {"fao56": "v2.3"})
        assert not report.drift_detected  # لا مرجع للمقارنة
        assert report.consistency_check["status"] == "unknown"


class TestAuditChain:
    def test_audit_reports_trace_rate(self):
        recs = [
            _make_rec_with_provenance("r1"),
            _make_rec_with_provenance("r2"),
            _make_rec_without_provenance(),
        ]
        audit = audit_chain(recs, {"fao56": "v2.1", "wofost": "7.2"})
        assert audit["total"] == 3
        assert audit["traced"] == 2
        assert audit["untraced"] == 1
        assert audit["trace_rate"] == 0.67

    def test_audit_counts_drift(self):
        # نسخ مختلفة → كل التوصيات المتتبّعة بانحراف
        recs = [_make_rec_with_provenance("r1"), _make_rec_with_provenance("r2")]
        audit = audit_chain(recs, {"fao56": "v9.9", "wofost": "9.9"})
        assert audit["drift_detected_count"] == 2

    def test_empty_log_handled_gracefully(self):
        # CRITICAL: قائمة فارغة → لا اختراع لمعدّل
        audit = audit_chain([], {"fao56": "v2.1"})
        assert audit["total"] == 0
        assert "لا توصيات" in audit["summary_ar"]

    def test_all_traced_clean_summary(self):
        recs = [_make_rec_with_provenance("r1"), _make_rec_with_provenance("r2")]
        audit = audit_chain(recs, {"fao56": "v2.1", "wofost": "7.2"})
        assert audit["trace_rate"] == 1.0
        assert "كل التوصيات قابلة للمراجعة" in audit["summary_ar"]
