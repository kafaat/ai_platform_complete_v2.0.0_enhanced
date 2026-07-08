from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _body(path: str, marker: str, next_marker: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    start = text.index(marker)
    end = text.index(next_marker, start)
    return text[start:end]


def test_decision_record_write_endpoint_uses_decision_service_facade() -> None:
    body = _body(
        "api/routers/decision_record.py",
        '@router.post("/api/v1/decision/record")',
        "\n\nclass OutcomePlannedIn",
    )
    assert "_record_decision_via_service" in body
    assert "tenant_connection" not in body
    assert "INSERT INTO decision_record" not in body
    assert "_emit_domain_event" not in body


def test_outcome_record_write_endpoint_uses_decision_service_facade() -> None:
    body = _body(
        "api/routers/decision_record.py",
        '@router.post("/api/v1/outcome/record")',
        '\n\n@router.get("/api/v1/decision/{decision_id}/lineage")',
    )
    assert "_record_outcome_via_service" in body
    assert "tenant_connection" not in body
    assert "INSERT INTO outcome_record" not in body
    assert "_emit_domain_event" not in body


def test_dispatch_execute_write_endpoint_uses_decision_service_facade() -> None:
    body = _body(
        "api/routers/decision_dispatch.py",
        '@router.post("/api/v1/decision/dispatch/execute")',
        '\n\n@router.post("/api/v1/decision/dispatch/consume")',
    )
    assert "_record_dispatch_decision_via_service" in body
    assert "tenant_connection" not in body
    assert "INSERT INTO dispatch_decisions" not in body
    assert "UPDATE dispatch_decisions" not in body
    assert "_emit_domain_event" not in body


def test_recommendation_outcomes_write_endpoint_uses_decision_service_facade() -> None:
    body = _body(
        "api/routers/recommendations.py",
        '@router.post("/api/v1/recommendations/outcomes", status_code=201)',
        "\n\n# مُسجَّل أخيراً عمداً:",
    )
    assert "_record_recommendation_outcome_via_service" in body
    assert "tenant_connection" not in body
    assert "INSERT INTO recommendation_outcomes" not in body
    assert "CommandStore" not in body


def test_decision_service_client_exposes_p4_5_write_facade_functions() -> None:
    text = (ROOT / "api/decision_service_client.py").read_text(encoding="utf-8")
    for name in [
        "record_decision",
        "record_dispatch_decision",
        "record_outcome",
        "record_recommendation_outcome",
        "record_learning_update",
    ]:
        assert f"async def {name}" in text
    assert "DEFAULT_DECISION_SERVICE_URL" in text
    assert "X-Agent-Token" in text
    assert "X-Tenant-Id" in text
