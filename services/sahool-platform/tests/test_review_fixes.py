"""Tests for critical fixes from strategic review:
1. district_id added to SearchContext (silent bug fix)
2. Pre-filter for O(matching) instead of O(all)
3. Explicit same_district scoring (was implicit before)
4. Contract pipeline enforcement (closes 'memory layer outside decision core')
"""

from datetime import datetime, timedelta

from core.canonical_schemas import UserRole, UserSchema
from core.cross_reference_finder import SearchContext, SimilarityMatch, find_similar_recommendations
from core.learning.recommendation_log import RecommendationRecord
from core.recommendation_bridge import (
    ContextPipelineError,
    EnrichedRecommendation,
    enforce_pipeline,
    full_delivery_pipeline,
    safe_delivery,
    validate_pipeline,
)


def _rec(rec_id, tenant_id="t1", district="al_bayda", days_ago=20, crop="wheat"):
    date = (datetime.now() - timedelta(days=days_ago)).date().isoformat()
    return RecommendationRecord(
        rec_id=rec_id,
        tenant_id=tenant_id,
        district_id=district,
        zone_id="z1",
        crop=crop,
        issued_date=date,
        recommendation_ar="x",
        quality_grade="READY",
        predicted_yield_t_ha=3.5,
        confidence="medium",
    )


class TestSilentDistrictBugFix:
    """إصلاح ١: district_id كان يُستخدم في المنطق بدون مرجع في السياق."""

    def test_search_context_accepts_district_id(self):
        ctx = SearchContext(tenant_id="t1", field_id="f1", crop="wheat", district_id="al_bayda")
        assert ctx.district_id == "al_bayda"

    def test_district_id_optional_backward_compat(self):
        # التوافق الخلفي محفوظ
        ctx = SearchContext(tenant_id="t1", field_id="f1", crop="wheat")
        assert ctx.district_id is None

    def test_same_district_increases_score_explicitly(self):
        # CRITICAL: المديرية المطابقة تزيد score (لا ضمنياً)
        ctx_with = SearchContext(
            tenant_id="t1", field_id="f1", crop="wheat", district_id="al_bayda"
        )
        ctx_without = SearchContext(tenant_id="t1", field_id="f1", crop="wheat")
        log = [_rec("r1", district="al_bayda")]

        r_with = find_similar_recommendations(ctx_with, log, min_similarity=0.0)
        r_without = find_similar_recommendations(ctx_without, log, min_similarity=0.0)

        assert r_with[0].similarity_score > r_without[0].similarity_score
        # السبب صريح في الأسباب
        assert any("المديرية" in s for s in r_with[0].why_similar_ar)

    def test_different_district_no_bonus(self):
        # مديرية مختلفة → لا zwd للـsame_district
        ctx = SearchContext(
            tenant_id="t1", field_id="f1", crop="wheat", district_id="dhamar"
        )  # مديرية مختلفة
        log = [_rec("r1", district="al_bayda")]
        results = find_similar_recommendations(ctx, log, min_similarity=0.0)
        # السبب لا يجب أن يحوي "نفس المديرية"
        if results:
            assert not any("نفس المديرية" in s for s in results[0].why_similar_ar)


class TestPreFilterPerformance:
    """إصلاح ٢: pre-filter يستبعد tenant آخر + القديم قبل حساب التشابه."""

    def test_other_tenant_filtered_before_scoring(self):
        # tenant آخر → يُفلتر فوراً (لا حساب تشابه)
        ctx = SearchContext(tenant_id="t1", field_id="f1", crop="wheat")
        log = [
            _rec("r_mine", tenant_id="t1"),
            _rec("r_other", tenant_id="t_other"),
        ]
        results = find_similar_recommendations(ctx, log, min_similarity=0.0)
        assert len(results) == 1
        assert results[0].source_id == "r_mine"

    def test_old_records_filtered_by_age(self):
        # > 365 يوم → يُفلتر
        ctx = SearchContext(tenant_id="t1", field_id="f1", crop="wheat")
        log = [
            _rec("r_recent", days_ago=20),
            _rec("r_ancient", days_ago=500),
        ]
        results = find_similar_recommendations(ctx, log, min_similarity=0.0)
        assert len(results) == 1
        assert results[0].source_id == "r_recent"

    def test_empty_candidates_short_circuits(self):
        # CRITICAL: قائمة فارغة بعد pre-filter → return فوري، لا حساب
        ctx = SearchContext(tenant_id="t1", field_id="f1", crop="wheat")
        log = [_rec("r1", tenant_id="t_other")]  # كلها tenant آخر
        results = find_similar_recommendations(ctx, log)
        assert results == []


class TestOutcomeQualityBridge:
    """جسر مستقبلي للـlearning loop (التنفيذ مُؤجَّل، البنية جاهزة)."""

    def test_match_carries_outcome_quality_field(self):
        # CRITICAL: SimilarityMatch يحوي outcome_quality للتنفيذ المستقبلي
        m = SimilarityMatch(
            source_type="recommendation",
            source_id="r1",
            source_date="2026-01-01",
            tenant_id="t1",
            field_id="f1",
            crop="wheat",
            similarity_score=0.8,
            why_similar_ar=["x"],
        )
        assert hasattr(m, "outcome_quality")
        assert m.outcome_quality is None  # default: غير محسوب

    def test_outcome_quality_computed_from_error(self):
        # error_pct=0.1 (10% خطأ) → quality=0.9
        rec = _rec("r1")
        rec.actual_yield_t_ha = 3.4
        rec.error_pct = 0.1
        ctx = SearchContext(tenant_id="t1", field_id="f1", crop="wheat")
        results = find_similar_recommendations(ctx, [rec], min_similarity=0.0)
        assert results
        assert results[0].outcome_quality == 0.9  # 1.0 - 0.1


class TestContractPipelineEnforcement:
    """إصلاح ٥ (الجوهري): لا توصية تخرج بدون كل المراحل."""

    def _user(self, role=UserRole.AGRONOMIST):
        return UserSchema(user_id="u1", tenant_id="tnt_001", role=role, name_ar="x")

    def _history(self):
        return [_rec("r_old", tenant_id="tnt_001")]

    def test_complete_pipeline_passes(self):
        delivery = safe_delivery(
            user=self._user(),
            tenant_id="tnt_001",
            field_id="fld_03",
            farm_id="frm_01",
            crop="wheat",
            base_recommendation={"rec_id": "r1", "recommendation_ar": "اروِ"},
            recommendation_history=self._history(),
            current_indicators={"ndvi": 0.55},
            engines_used=["fao56"],
        )
        req = validate_pipeline(delivery)
        assert req.is_complete

    def test_missing_cross_reference_caught(self):
        # CRITICAL: delivery بلا cross_reference → contract يكتشفه
        incomplete = EnrichedRecommendation(
            rec_id="bad",
            base_recommendation={},
            cross_reference={},  # count مفقود
            provenance={"model_versions": {"fao56": "v1"}, "input_snapshot": {}},
            auth_decision={
                "tenant_id": "t1",
                "resource_tenant_id": "t1",
                "permission": "x",
                "reason_ar": "x",
            },
            delivered=True,
            reason_ar="x",
        )
        req = validate_pipeline(incomplete)
        assert not req.is_complete
        assert not req.has_cross_reference

    def test_missing_provenance_caught(self):
        incomplete = EnrichedRecommendation(
            rec_id="bad",
            base_recommendation={},
            cross_reference={"count": 0},
            provenance={},  # model_versions مفقود
            auth_decision={
                "tenant_id": "t1",
                "resource_tenant_id": "t1",
                "permission": "x",
                "reason_ar": "x",
            },
            delivered=True,
            reason_ar="x",
        )
        req = validate_pipeline(incomplete)
        assert not req.has_provenance

    def test_enforce_raises_on_incomplete(self):
        # CRITICAL: enforce يرفع exception (لا يسلّم بصمت)
        incomplete = EnrichedRecommendation(
            rec_id="bad",
            base_recommendation={},
            cross_reference={},  # ناقص
            provenance={},
            auth_decision={"tenant_id": "t1"},
            delivered=True,
            reason_ar="x",
        )
        try:
            enforce_pipeline(incomplete)
            raise AssertionError("كان يجب رفع ContextPipelineError")
        except ContextPipelineError as e:
            assert "Pipeline incomplete" in str(e)

    def test_enforce_flips_delivered_to_false(self):
        # CRITICAL: فحص فاشل → delivered=False مع سبب صريح
        incomplete = EnrichedRecommendation(
            rec_id="bad",
            base_recommendation={},
            cross_reference={},
            provenance={},
            auth_decision={"tenant_id": "t1"},
            delivered=True,
            reason_ar="x",
        )
        try:
            enforce_pipeline(incomplete)
        except ContextPipelineError:
            pass
        # delivery نفسها عُدِّلت
        assert not incomplete.delivered
        assert "ناقص" in incomplete.reason_ar


class TestSafeDelivery:
    """safe_delivery — نقطة الدخول الموصى بها للطبقات الخارجية."""

    def _user(self):
        return UserSchema(user_id="u1", tenant_id="tnt_001", role=UserRole.AGRONOMIST, name_ar="x")

    def test_safe_delivery_propagates_district(self):
        # CRITICAL: district_id يصل من safe_delivery لـSearchContext
        log = [_rec("r1", tenant_id="tnt_001", district="al_bayda")]
        delivery = safe_delivery(
            user=self._user(),
            tenant_id="tnt_001",
            field_id="fld_03",
            farm_id="frm_01",
            crop="wheat",
            district_id="al_bayda",
            base_recommendation={"rec_id": "r1", "recommendation_ar": "x"},
            recommendation_history=log,
            current_indicators={"ndvi": 0.55},
        )
        # تحقّق: تأثير district_id موجود في cross_reference
        cross = delivery.cross_reference
        if cross.get("matches"):
            top = cross["matches"][0]
            # المديرية المطابقة يجب أن تكون في الأسباب
            assert any("المديرية" in s for s in top.why_similar_ar)

    def test_safe_delivery_blocks_unauthorized(self):
        # WORKER لا يستطيع طلب توصية
        worker = UserSchema(user_id="w1", tenant_id="tnt_001", role=UserRole.WORKER, name_ar="x")
        delivery = safe_delivery(
            user=worker,
            tenant_id="tnt_001",
            field_id="f",
            farm_id="fa",
            crop="wheat",
            base_recommendation={"rec_id": "r", "recommendation_ar": "x"},
            recommendation_history=[],
        )
        assert not delivery.delivered
