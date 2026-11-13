from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUTER = ROOT / "services/sahool-platform/api/routers/recommendations.py"


def _body() -> str:
    text = ROUTER.read_text(encoding="utf-8")
    start = text.index('@router.post("/api/v1/recommendations/outcomes", status_code=201)')
    end = text.index("\n\n# مُسجَّل أخيراً عمداً:", start)
    return text[start:end]


def test_cutover_branch_never_writes_the_platform_and_reads_only_the_sealed_labels():
    # Amended by v26 workstream 06 (was: no platform connection at all in the cutover branch).
    # Before the only authoritative write, the branch reconciles the outcome labels against the
    # sealed recommendation through _cutover_outcome_labels: ONE tenant read, no platform write,
    # so a contradicting prediction is refused in both SOR modes. decision-service stays the
    # only writer.
    body = _body()
    cut = body.index("if mode.strict_decision_service_required:")
    pre = body.index("# Pre-cutover bridge:")
    authoritative_branch = body[cut:pre]
    assert "tenant_connection" not in authoritative_branch
    assert authoritative_branch.index("await _cutover_outcome_labels(user, req)") < (
        authoritative_branch.index("await _mirror_recommendation_outcome_to_service")
    )
    text = ROUTER.read_text(encoding="utf-8")
    helper = text[
        text.index("async def _cutover_outcome_labels(") : text.index(
            '@router.post("/api/v1/recommendations/outcomes"'
        )
    ]
    assert helper.count("tenant_connection(") == 1
    for write in ("INSERT INTO", "UPDATE ", "DELETE FROM", "conn.execute", "_idempotent("):
        assert write not in authoritative_branch + helper, write
    assert "INSERT INTO recommendation_outcomes" not in authoritative_branch


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
    payload = body[
        body.index("service_payload = {") : body.index("mode = get_platform_decision_sor_mode()")
    ]
    assert '"idempotency_key": idem' in payload
    assert '"recommendation_id": req.recommendation_id' in payload
    assert '"predicted_yield_t_ha": req.predicted_yield_t_ha' in payload
    assert '"actual_yield_t_ha": req.actual_yield_t_ha' in payload
