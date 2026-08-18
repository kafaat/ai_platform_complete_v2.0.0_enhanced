from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUTER = ROOT / "services/sahool-platform/api/routers/recommendations.py"


def _body() -> str:
    text = ROUTER.read_text(encoding="utf-8")
    start = text.index('@router.post("/api/v1/recommendations/outcomes", status_code=201)')
    end = text.index("\n\n# مُسجَّل أخيراً عمداً:", start)
    return text[start:end]


def test_cutover_branch_calls_service_before_any_platform_connection():
    body = _body()
    cut = body.index("if mode.strict_decision_service_required:")
    pre = body.index("# Pre-cutover bridge:")
    authoritative_branch = body[cut:pre]
    assert "tenant_connection" not in authoritative_branch
    assert "INSERT INTO recommendation_outcomes" not in authoritative_branch
    assert "await _mirror_recommendation_outcome_to_service" in authoritative_branch
    assert 'service_result.get("authoritative")' in authoritative_branch
    assert 'service_result.get("persisted")' in authoritative_branch
    assert 'service_result.get("outcome_id")' in authoritative_branch


def test_pre_cutover_branch_remains_platform_authoritative_then_fail_soft_mirror():
    body = _body()
    pre = body.index("# Pre-cutover bridge:")
    legacy = body[pre:]
    assert "tenant_connection" in legacy
    assert "INSERT INTO recommendation_outcomes" in legacy
    assert 'assert_platform_may_write_decision_sor("recommendation_outcomes")' in legacy
    assert "except Exception" in legacy
    assert 'result["authoritative_store"] = "sahool-platform"' in legacy


def test_idempotency_identity_is_forwarded_to_authoritative_service():
    body = _body()
    payload = body[body.index("service_payload = {"):body.index("mode = get_platform_decision_sor_mode()")]
    assert '"idempotency_key": idem' in payload
    assert '"recommendation_id": req.recommendation_id' in payload
    assert '"predicted_yield_t_ha": req.predicted_yield_t_ha' in payload
    assert '"actual_yield_t_ha": req.actual_yield_t_ha' in payload
