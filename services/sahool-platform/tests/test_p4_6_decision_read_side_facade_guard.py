"""INTERIM decision-loop read-path guard (rescoped from the P4.6 read-facade contract).

During the temporary bridge the platform is the Source of Record, so the loop READ routes
must read the platform DB authoritatively again (they returned empty/502 while delegating to
the not-yet-SoR decision-service).  This guard therefore asserts the interim invariant:
the learning-summary and decision/lineage read routes read the platform loop tables via
``tenant_connection``.  decision-service still exposes its read contracts (kept for the
future SoR + as the mirror surface), and the client still exposes the read helpers.
"""

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


def test_learning_summary_read_side_reads_platform_db_authoritatively():
    source = _read("api/routers/learning_summary.py")
    body = _function_body(source, "get_learning_summary")
    assert "tenant_connection" in body
    assert "decision_record" in body
    assert "outcome_record" in body


def test_decision_lineage_reads_use_platform_db_authoritatively():
    source = _read("api/routers/decision_record.py")
    for name in ("get_decision_lineage", "list_decision_records", "get_field_lineage"):
        body = _function_body(source, name)
        assert "tenant_connection" in body
        assert ("decision_record" in body) or ("outcome_record" in body)


def test_decision_service_still_exposes_read_contracts():
    source = Path(ROOT.parent / "decision-service/main.py").read_text(encoding="utf-8")
    for marker in (
        '@app.get("/v1/learning/summary")',
        '@app.get("/v1/decisions")',
        '@app.get("/v1/decisions/{decision_id}/lineage")',
        '@app.get("/v1/fields/{field_id}/lineage")',
        '@app.get("/v1/outcomes/reconciled")',
    ):
        assert marker in source


def test_decision_client_still_exposes_read_side_helpers():
    text = _read("api/decision_service_client.py")
    for name in ("list_decisions", "get_field_lineage", "get_reconciled_outcomes"):
        assert f"async def {name}" in text
