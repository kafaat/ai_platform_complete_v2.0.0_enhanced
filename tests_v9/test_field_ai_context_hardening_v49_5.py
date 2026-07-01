from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "services" / "sahool-platform" / "api" / "routers" / "field_ai_context.py"
MIGRATION = ROOT / "migrations" / "v127_evidence_context_hardening.sql"


def _src() -> str:
    return ROUTER.read_text(encoding="utf-8")


def test_v49_5_events_query_is_explicitly_tenant_scoped():
    src = _src()
    assert "async def _optional_events(" in src
    assert "tenant_id: str" in src
    assert "WHERE tenant_id = $2::uuid" in src
    assert "operations, warn = await _optional_events(conn, field_id, str(user.tenant_id)" in src


def test_v49_5_ai_context_has_redaction_and_budget_controls():
    src = _src()
    assert "_REDACT_KEYS" in src
    assert "_redact_context" in src
    assert "_CONTEXT_MAX_BYTES" in src
    assert "_CONTEXT_MAX_ITEMS" in src
    assert "_apply_final_context_budget" in src
    assert "context_budget" in src
    assert "omitted_by_budget" in src


def test_v49_5_ai_context_has_freshness_and_provenance_cards():
    src = _src()
    assert "_freshness_score" in src
    assert "_source_provenance" in src
    assert "evidence_freshness_score" in src
    assert "evidence_provenance" in src
    assert "source" in src and "confidence" in src


def test_v49_5_recommendation_outcome_rls_migration_contract():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "recommendation_outcomes" in sql
    assert "WITH CHECK" in sql
    assert "tenant_id IS NOT NULL" in sql
    assert "predicted_yield_t_ha IS NULL OR predicted_yield_t_ha >= 0" in sql
    assert "actual_yield_t_ha IS NULL OR actual_yield_t_ha >= 0" in sql
