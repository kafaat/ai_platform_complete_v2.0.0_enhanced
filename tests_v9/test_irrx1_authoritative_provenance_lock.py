from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_manual_execution_creation_no_longer_accepts_free_recommendation_payload():
    text = (ROOT / "services/sahool-platform/api/routers/irrigation_engineering.py").read_text(
        encoding="utf-8"
    )
    request = text[
        text.index("class ManualExecutionCreateRequest") : text.index(
            "class ManualExecutionTransitionRequest"
        )
    ]
    assert "execution_plan_id: str" in request
    assert "recommendation: ManualRecommendationInput" not in request
    assert "AUTHORITATIVE_MANUAL_IRRIGATION_PLAN_NOT_FOUND" in text


def test_decision_sor_returns_plan_digest_and_bff_registers_only_proven_irrigation_plan():
    sor = (ROOT / "services/decision-service/persistence.py").read_text(encoding="utf-8")
    bff = (ROOT / "services/sahool-platform/api/routers/decision_review.py").read_text(
        encoding="utf-8"
    )
    assert '"plan_digest": row["request_hash"]' in sor
    assert 'result.get("authoritative") is True' in bff
    assert 'result.get("persisted") is True' in bff
    assert 'req.operation_type == "manual_irrigation"' in bff
    assert "irrigation_manual_execution_sources" in bff


def test_database_enforces_source_identity_and_tenant_isolation():
    sql = (
        ROOT / "migrations/v190_irrx1_authoritative_recommendation_provenance_lock.sql"
    ).read_text(encoding="utf-8")
    for token in (
        "FORCE ROW LEVEL SECURITY",
        "FOREIGN KEY (tenant_id, execution_plan_id)",
        "IRRX1_AUTHORITATIVE_PROVENANCE_REQUIRED",
        "IRRX1_EXECUTION_SOURCE_MISMATCH",
        "IRRX1_PROVENANCE_IS_IMMUTABLE",
        "manual execution sources are append-only",
    ):
        assert token in sql


def test_v190_is_registered_in_manifest_and_runner():
    assert "v190_irrx1_authoritative_recommendation_provenance_lock.sql" in (
        ROOT / "migrations/MANIFEST.txt"
    ).read_text(encoding="utf-8")
    assert "v190_irrx1_authoritative_recommendation_provenance_lock.sql" in (
        ROOT / "scripts_v9/run_migrations.sql"
    ).read_text(encoding="utf-8")
