"""Tests for recommendation_bridge: non-invasive integration of
cross_reference + authorization + provenance with existing engine."""
from datetime import datetime, timedelta
from core.recommendation_bridge import (
    build_provenance, enrich_with_context, authorize_and_deliver,
    full_delivery_pipeline, delivery_summary, EnrichedRecommendation)
from core.canonical_schemas import UserSchema, UserRole
from core.learning.recommendation_log import RecommendationRecord


def _user(role=UserRole.AGRONOMIST, tenant_id="tnt_001"):
    return UserSchema(user_id="u1", tenant_id=tenant_id, role=role,
                     name_ar="مهندس")


def _history(count=1, tenant_id="tnt_001"):
    recent = (datetime.now() - timedelta(days=20)).date().isoformat()
    return [
        RecommendationRecord(
            rec_id=f"r_{i}", tenant_id=tenant_id, district_id="d1",
            zone_id="fld_03", crop="wheat", issued_date=recent,
            recommendation_ar=f"توصية {i}", quality_grade="READY",
            predicted_yield_t_ha=3.5, confidence="medium",
            provenance={"input_snapshot": {"ndvi": 0.55},
                       "engines_used": ["fao56"], "weather_source": "open-meteo",
                       "weather_data_date": recent,
                       "model_versions": {"fao56": "v2.1"},
                       "calibration_set_id": None, "knowledge_snippets_ids": []},
            actual_yield_t_ha=3.4)
        for i in range(count)
    ]


class TestProvenanceBuilding:
    def test_includes_model_versions_from_registry(self):
        # CRITICAL: provenance يجب أن يحوي snapshot كاملاً من registry
        prov = build_provenance(
            engines_used=["fao56"], weather_source="open-meteo",
            weather_data_date="2026-05-28", input_snapshot={"ndvi": 0.6})
        assert "model_versions" in prov
        assert len(prov["model_versions"]) >= 16   # 16 skill مسجَّل افتراضياً
        assert prov["weather_source"] == "open-meteo"
        assert "snapshot_taken_at" in prov

    def test_input_snapshot_preserved(self):
        prov = build_provenance(
            engines_used=[], weather_source="x", weather_data_date="x",
            input_snapshot={"ndvi": 0.55, "soil_moisture": 22.0})
        assert prov["input_snapshot"]["ndvi"] == 0.55


class TestEnrichment:
    def test_adds_cross_reference_without_modifying_base(self):
        base = {"rec_id": "r_new", "recommendation_ar": "اروِ"}
        enriched = enrich_with_context(
            base, tenant_id="tnt_001", field_id="fld_03", crop="wheat",
            recommendation_history=_history(2),
            current_indicators={"ndvi": 0.57}, engines_used=["fao56"])
        # الأساس محفوظ (non-invasive)
        assert enriched["rec_id"] == "r_new"
        assert enriched["recommendation_ar"] == "اروِ"
        # السياق مُضاف
        assert "cross_reference" in enriched
        assert "provenance" in enriched

    def test_finds_similar_when_history_matches(self):
        enriched = enrich_with_context(
            {"rec_id": "x"}, tenant_id="tnt_001", field_id="fld_03",
            crop="wheat", recommendation_history=_history(3),
            current_indicators={"ndvi": 0.55})
        assert enriched["has_historical_context"]
        assert enriched["cross_reference"]["count"] >= 1

    def test_no_history_no_invention(self):
        # CRITICAL: لا تاريخ → لا اختراع لحالات مشابهة
        enriched = enrich_with_context(
            {"rec_id": "x"}, tenant_id="tnt_001", field_id="fld_03",
            crop="wheat", recommendation_history=[],
            current_indicators={"ndvi": 0.55})
        assert not enriched["has_historical_context"]
        assert enriched["cross_reference"]["count"] == 0


class TestAuthorizeAndDeliver:
    def test_authorized_user_delivered(self):
        u = _user(UserRole.AGRONOMIST)
        enriched = {"rec_id": "r1", "base": {}, "cross_reference": {},
                   "provenance": {}}
        delivery = authorize_and_deliver(u, enriched, tenant_id="tnt_001",
                                        farm_id="frm_01")
        assert delivery.delivered

    def test_worker_blocked_from_request(self):
        # CRITICAL: WORKER لا يملك RECOMMENDATION_REQUEST
        u = _user(UserRole.WORKER)
        delivery = authorize_and_deliver(u, {"rec_id": "r1"},
                                        tenant_id="tnt_001")
        assert not delivery.delivered
        assert "worker" in delivery.reason_ar

    def test_cross_tenant_blocked(self):
        # CRITICAL: tenant آخر → رفض حتى لـOWNER
        u = _user(UserRole.OWNER, tenant_id="tnt_001")
        delivery = authorize_and_deliver(u, {"rec_id": "r1"},
                                        tenant_id="tnt_999")   # tenant مختلف
        assert not delivery.delivered
        assert "عزل" in delivery.reason_ar

    def test_safety_critical_logged(self):
        # AGRONOMIST يوافق على مبيد → مُسلَّمة لكن مع علامة "حرجة"
        u = _user(UserRole.AGRONOMIST)
        delivery = authorize_and_deliver(u, {"rec_id": "r1"},
                                        tenant_id="tnt_001",
                                        is_pesticide=True)
        assert delivery.delivered
        assert "حرجة" in delivery.reason_ar or "audit" in delivery.reason_ar


class TestFullPipeline:
    def test_full_pipeline_success(self):
        u = _user(UserRole.AGRONOMIST)
        delivery = full_delivery_pipeline(
            user=u, tenant_id="tnt_001", field_id="fld_03", farm_id="frm_01",
            crop="wheat",
            base_recommendation={"rec_id": "r1", "recommendation_ar": "اروِ"},
            recommendation_history=_history(2),
            current_indicators={"ndvi": 0.57},
            engines_used=["fao56", "fuzzy"])
        assert delivery.delivered
        assert delivery.cross_reference["count"] >= 1
        assert len(delivery.provenance["model_versions"]) >= 16

    def test_full_pipeline_respects_inactive(self):
        # CRITICAL: مستخدم معطّل → رفض حتى لو OWNER
        u = UserSchema(user_id="u1", tenant_id="tnt_001",
                      role=UserRole.OWNER, name_ar="x", is_active=False)
        delivery = full_delivery_pipeline(
            user=u, tenant_id="tnt_001", field_id="f", farm_id="fa",
            crop="wheat", base_recommendation={"rec_id": "r"},
            recommendation_history=[])
        assert not delivery.delivered


class TestDeliverySummary:
    def test_delivered_shows_counts(self):
        u = _user(UserRole.AGRONOMIST)
        delivery = full_delivery_pipeline(
            user=u, tenant_id="tnt_001", field_id="f", farm_id="fa",
            crop="wheat", base_recommendation={"rec_id": "r1"},
            recommendation_history=_history(2),
            current_indicators={"ndvi": 0.55})
        summary = delivery_summary(delivery)
        assert "✅" in summary or "مُسلَّمة" in summary

    def test_blocked_explains_reason(self):
        u = _user(UserRole.WORKER)
        delivery = full_delivery_pipeline(
            user=u, tenant_id="tnt_001", field_id="f", farm_id="fa",
            crop="wheat", base_recommendation={"rec_id": "r"},
            recommendation_history=[])
        summary = delivery_summary(delivery)
        assert "⛔" in summary or "رفض" in summary
