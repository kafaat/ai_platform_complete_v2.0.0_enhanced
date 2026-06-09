"""Tests for internal_orchestrator + api_adapter:
- Closes the 'maestro gap' (cross_ref + provenance forced internally)
- HTTP-like adapter framework-neutral
- Rate limiting (AI Workaholic guard)
- Tenant isolation at HTTP boundary"""
from core.canonical_schemas import UserSchema, UserRole
from core.internal_orchestrator import (
    orchestrate_recommendation, orchestrator_summary)
from core.api_adapter import (
    ApiRequest, ApiResponse, RateLimiter,
    handle_recommendation_request, handle_healthz, handle_readyz,
    _reset_rate_limiter)


def _user(role=UserRole.AGRONOMIST, tenant="tnt_001", active=True):
    return UserSchema(user_id=f"u_{role.value}", tenant_id=tenant,
                     role=role, name_ar="x", is_active=active)


def _validation():
    return {"quality_grade": "READY", "blocked": False,
            "missing_blockers": [], "missing_observables": [],
            "field_state": "ready"}


def _payload(**overrides):
    base = {
        "tenant_id": "tnt_001", "field_id": "fld_03", "farm_id": "frm_01",
        "crop": "wheat", "validation": _validation(),
        "current_indicators": {"ndvi": 0.55},
        "district_id": "al_bayda",
    }
    base.update(overrides)
    return base


class TestInternalOrchestrator:
    def test_authorized_user_gets_delivery(self):
        result = orchestrate_recommendation(
            user=_user(), tenant_id="tnt_001", farm_id="frm_01",
            field_id="fld_03", crop="wheat",
            validation=_validation(), field_state="ready",
            current_indicators={"ndvi": 0.55},
            district_id="al_bayda",
        )
        assert result.delivered

    def test_provenance_filled_with_versions(self):
        # CRITICAL: model_versions يُحفظ في كل توصية (forensic)
        result = orchestrate_recommendation(
            user=_user(), tenant_id="tnt_001", farm_id="frm_01",
            field_id="fld_03", crop="wheat",
            validation=_validation(), field_state="ready",
        )
        assert len(result.provenance.get("model_versions", {})) >= 16

    def test_worker_fail_fast_no_engine_run(self):
        # CRITICAL: WORKER يُرفض قبل تشغيل المحرّك
        result = orchestrate_recommendation(
            user=_user(UserRole.WORKER), tenant_id="tnt_001",
            farm_id="frm_01", field_id="fld_03", crop="wheat",
            validation=_validation(), field_state="ready",
        )
        assert not result.delivered
        # base_recommendation فارغ (لم يُشغَّل المحرّك)
        assert result.base_recommendation == {}

    def test_cross_tenant_blocked_even_owner(self):
        # حتى OWNER لا يعبر tenant
        result = orchestrate_recommendation(
            user=_user(UserRole.OWNER, tenant="tnt_001"),
            tenant_id="tnt_OTHER", farm_id="f", field_id="f",
            crop="wheat", validation=_validation(),
        )
        assert not result.delivered
        assert "عزل tenant" in result.reason_ar

    def test_inactive_user_rejected(self):
        result = orchestrate_recommendation(
            user=_user(active=False), tenant_id="tnt_001",
            farm_id="frm_01", field_id="fld_03", crop="wheat",
            validation=_validation(),
        )
        assert not result.delivered

    def test_summary_includes_essential_fields(self):
        result = orchestrate_recommendation(
            user=_user(), tenant_id="tnt_001", farm_id="frm_01",
            field_id="fld_03", crop="wheat",
            validation=_validation(), field_state="ready",
        )
        summary = orchestrator_summary(result)
        assert "delivered" in summary
        assert "auth_role" in summary
        assert "model_versions_count" in summary


class TestApiAdapter:
    """API محايد عن الإطار — TestClient غير مطلوب."""

    def setup_method(self):
        _reset_rate_limiter()

    def test_healthz_returns_200(self):
        r = handle_healthz()
        assert r.status_code == 200
        assert r.body["status"] == "alive"

    def test_readyz_includes_checks(self):
        r = handle_readyz()
        assert r.status_code in (200, 503)
        assert "checks" in r.body
        assert "skills_registry" in r.body["checks"]

    def test_successful_request_returns_200(self):
        req = ApiRequest(user=_user(), payload=_payload())
        r = handle_recommendation_request(req)
        assert r.status_code == 200
        assert r.body["delivered"]
        assert r.body["rec_id"]

    def test_missing_fields_returns_400(self):
        # CRITICAL: payload ناقص → 400 مع تفصيل
        req = ApiRequest(user=_user(), payload={"tenant_id": "x"})
        r = handle_recommendation_request(req)
        assert r.status_code == 400
        assert "missing_fields" in r.body

    def test_worker_returns_403(self):
        req = ApiRequest(user=_user(UserRole.WORKER), payload=_payload())
        r = handle_recommendation_request(req)
        assert r.status_code == 403

    def test_cross_tenant_returns_403(self):
        # CRITICAL: tenant آخر → 403
        req = ApiRequest(user=_user(tenant="tnt_001"),
                        payload=_payload(tenant_id="tnt_OTHER"))
        r = handle_recommendation_request(req)
        assert r.status_code == 403
        assert "عزل" in r.body.get("reason_ar", "")

    def test_inactive_user_returns_401(self):
        req = ApiRequest(user=_user(active=False), payload=_payload())
        r = handle_recommendation_request(req)
        assert r.status_code == 401

    def test_internal_error_returns_4xx(self):
        # validation=None → الـorchestrator يلتقط الخطأ ويُرجع 422
        # (semantically أنضف من 500: pipeline فشل بنعومة، لم ينهَر السيرفر)
        req = ApiRequest(user=_user(), payload=_payload(validation=None))
        r = handle_recommendation_request(req)
        # 422 (pipeline failed) أو 500 (لو لم يُلتقَط)
        assert r.status_code in (400, 422, 500)
        assert not r.body.get("delivered", True)


class TestRateLimiter:
    def test_within_limit_allowed(self):
        # CRITICAL: AI Workaholic guard
        rl = RateLimiter(max_requests=3, window_seconds=3600)
        for _ in range(3):
            allowed, _ = rl.check_and_record("user_1")
            assert allowed

    def test_exceeded_limit_rejected(self):
        rl = RateLimiter(max_requests=3, window_seconds=3600)
        for _ in range(3):
            rl.check_and_record("user_1")
        # الرابع يُرفض
        allowed, remaining = rl.check_and_record("user_1")
        assert not allowed
        assert remaining == 0

    def test_separate_users_separate_quotas(self):
        # عزل المستخدمين — quota كل واحد منفصل
        rl = RateLimiter(max_requests=2, window_seconds=3600)
        rl.check_and_record("user_a")
        rl.check_and_record("user_a")
        # user_b بدأ من الصفر
        allowed, _ = rl.check_and_record("user_b")
        assert allowed

    def test_reset_clears_quota(self):
        rl = RateLimiter(max_requests=2, window_seconds=3600)
        rl.check_and_record("u")
        rl.check_and_record("u")
        rl.reset("u")
        allowed, _ = rl.check_and_record("u")
        assert allowed


class TestRateLimitEndToEnd:
    def setup_method(self):
        _reset_rate_limiter()

    def test_default_limit_is_20_per_hour(self):
        # default rate limiter في api_adapter
        from core.api_adapter import _rate_limiter
        assert _rate_limiter.max_requests == 20
        assert _rate_limiter.window_seconds == 3600

    def test_repeated_requests_eventually_blocked(self):
        # 21 طلب → الـ21 يجب أن يُرفض
        user = _user()
        for i in range(20):
            req = ApiRequest(user=user, payload=_payload())
            r = handle_recommendation_request(req)
            assert r.status_code == 200, f"Request #{i+1} should pass"
        # الطلب 21
        req = ApiRequest(user=user, payload=_payload())
        r = handle_recommendation_request(req)
        assert r.status_code == 429
        assert "rate_limit" in r.body["error"]
