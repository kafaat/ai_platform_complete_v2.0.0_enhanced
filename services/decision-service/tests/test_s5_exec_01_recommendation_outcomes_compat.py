from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_compat_migration_converges_identity_without_collapsing_recommendation_history():
    sql = (ROOT / "services/decision-service/migrations/032_recommendation_outcomes_cutover_compat.sql").read_text()
    for column in (
        "outcome_id", "idempotency_key", "request_hash", "decision_id", "outcome",
        "confidence", "metadata", "updated_at", "farm_id", "crop", "predicted_yield_t_ha",
        "actual_yield_t_ha", "accepted", "matured_within_lag", "issued_at",
        "outcome_recorded_at",
    ):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in sql
    assert "pk_cols = ARRAY['tenant_id','recommendation_id']" in sql
    assert "PRIMARY KEY (outcome_id)" in sql
    assert "ux_recommendation_outcomes_tenant_idempotency" in sql
    assert "UNIQUE INDEX" in sql
    assert "tenant_recommendation" in sql and "UNIQUE INDEX IF NOT EXISTS ux_recommendation_outcomes_tenant_recommendation" not in sql


def test_authoritative_persistence_uses_idempotency_not_recommendation_id_as_uniqueness():
    src = (ROOT / "services/decision-service/persistence.py").read_text()
    start = src.index("def _recommendation_outcome_request_hash")
    end = src.index("async def read_outcomes_for_reconcile", start)
    body = src[start:end]
    assert "ON CONFLICT (tenant_id, idempotency_key)" in body
    assert "ON CONFLICT (tenant_id, recommendation_id)" not in body
    assert "idempotency_key reused with different" in body
    assert "RETURNING outcome_id, request_hash" in body
    assert 'metadata.get("predicted_yield_t_ha")' in body
    assert 'metadata.get("actual_yield_t_ha")' in body
    assert "if not replayed:" in body  # no duplicate outbox event on replay


def test_service_contract_accepts_idempotency_and_exposes_compatibility_identity():
    src = (ROOT / "services/decision-service/main.py").read_text()
    model = src[src.index("class RecommendationOutcomeIn"):src.index("class LearningUpdateIn")]
    assert "idempotency_key: str | None = None" in model
    start = src.index('@app.post("/v1/recommendation-outcomes")')
    end = src.index('@app.post("/v1/learning/updates")', start)
    body = src[start:end]
    assert '"outcome_id": persisted.get("outcome_id")' in body
    assert '"replayed": bool(persisted.get("replayed", False))' in body
    assert '"authoritative": True' in body
