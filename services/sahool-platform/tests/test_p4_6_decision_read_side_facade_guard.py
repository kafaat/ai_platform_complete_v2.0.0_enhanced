from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    marker = f"async def {name}"
    start = source.index(marker)
    next_def = source.find("\n@router.", start + 1)
    if next_def == -1:
        next_def = len(source)
    return source[start:next_def]


def test_learning_summary_read_side_uses_decision_service_facade():
    source = _read("api/routers/learning_summary.py")
    body = _function_body(source, "get_learning_summary")
    assert "decision_service_client" in body
    assert "tenant_connection" not in body
    assert "decision_record" not in body
    assert "outcome_record" not in body
    assert "recommendation_outcomes" not in body
    assert "dispatch_decisions" not in body


def test_decision_lineage_reads_use_decision_service_facade():
    source = _read("api/routers/decision_record.py")
    for name in ("get_decision_lineage", "list_decision_records", "get_field_lineage"):
        body = _function_body(source, name)
        assert "decision_service_client" in body
        assert "tenant_connection" not in body
        assert "SELECT * FROM decision_record" not in body
        assert "SELECT * FROM outcome_record" not in body


def test_decision_service_exposes_read_contracts():
    source = Path(ROOT.parent / "decision-service/main.py").read_text(encoding="utf-8")
    for marker in (
        '@app.get("/v1/learning/summary")',
        '@app.get("/v1/decisions")',
        '@app.get("/v1/decisions/{decision_id}/lineage")',
        '@app.get("/v1/fields/{field_id}/lineage")',
        '@app.get("/v1/outcomes/reconciled")',
    ):
        assert marker in source


def test_decision_client_exposes_read_side_helpers():
    text = _read("api/decision_service_client.py")
    for name in ("list_decisions", "get_field_lineage", "get_reconciled_outcomes"):
        assert f"async def {name}" in text
