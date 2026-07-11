from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
M = (ROOT / "services/decision-service/main.py").read_text()
P = (ROOT / "services/decision-service/persistence.py").read_text()
SQL = (
    ROOT / "services/decision-service/migrations/013_registry_adapter_receipt_rollback.sql"
).read_text()
R = (ROOT / "services/sahool-platform/api/routers/decision_review.py").read_text()


def test_routes_and_bff_present():
    for x in [
        "activation-commands/{activation_command_id}/claim",
        "activation-commands/{activation_command_id}/receipt",
        "activation-receipts/{activation_receipt_id}/rollback-command",
    ]:
        assert x in M and x in R


def test_append_only_evidence_tables():
    assert SQL.count("BEFORE UPDATE OR DELETE") == 3
    assert (
        "uq_registry_claim_command" in SQL
        and "uq_registry_receipt_command" in SQL
        and "uq_rollback_receipt" in SQL
    )


def test_receipt_proves_candidate_digest_and_rollback_uses_previous_pointer():
    assert "active_artifact_digest_mismatch" in P
    assert "previous_artifact_uri" in P and "previous_artifact_digest" in P


def test_no_direct_registry_mutation():
    low = P.lower()
    assert "model.fit(" not in low and "optimizer.step(" not in low and "mqtt.publish(" not in low
