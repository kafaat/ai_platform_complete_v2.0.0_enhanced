from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "services/decision-service/recommendation_outcomes_cutover_preflight.py"
spec = importlib.util.spec_from_file_location("ro_preflight", PATH)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_fresh_schema_is_safe():
    result = mod.classify_observation(table_exists=False)
    assert result["classification"] == "PASSED"
    assert result["table_exists"] is False


def test_missing_lineage_columns_fails_closed():
    result = mod.classify_observation(table_exists=True, columns={"outcome_id"})
    assert result["classification"] == "FAILED"
    assert any("missing_required_columns" in x for x in result["blockers"])


def test_existing_duplicate_idempotency_is_blocked():
    result = mod.classify_observation(
        table_exists=True,
        columns={"tenant_id", "recommendation_id", "idempotency_key"},
        duplicate_tenant_idempotency_groups=2,
    )
    assert result["classification"] == "FAILED"
    assert result["duplicate_tenant_idempotency_groups"] == 2


def test_invalid_existing_outcome_identity_is_blocked():
    result = mod.classify_observation(
        table_exists=True,
        columns={"tenant_id", "recommendation_id", "outcome_id"},
        null_outcome_ids=1,
        duplicate_outcome_id_groups=1,
    )
    assert result["classification"] == "FAILED"
    assert "null_outcome_ids:1" in result["blockers"]
    assert "duplicate_outcome_id_groups:1" in result["blockers"]


def test_legacy_shape_with_unique_outcome_ids_is_safe():
    result = mod.classify_observation(
        table_exists=True,
        columns={"tenant_id", "recommendation_id", "outcome_id"},
    )
    assert result["classification"] == "PASSED"
