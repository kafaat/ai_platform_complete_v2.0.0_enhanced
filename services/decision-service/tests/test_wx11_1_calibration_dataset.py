from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN = (ROOT / "services/decision-service/main.py").read_text()
PERSISTENCE = (ROOT / "services/decision-service/persistence.py").read_text()
ROUTER = (ROOT / "services/sahool-platform/api/routers/decision_review.py").read_text()
CLIENT = (ROOT / "services/sahool-platform/api/decision_service_client.py").read_text()


def test_calibration_dataset_is_authoritative_read_only_boundary():
    assert '@app.get("/v1/learning/calibration-dataset")' in MAIN
    assert "if not sor_enabled()" in MAIN
    assert "build_calibration_dataset" in MAIN
    assert '"read_only": True' in PERSISTENCE
    assert "weighted_success_rate" in PERSISTENCE


def test_dataset_uses_verified_attribution_lineage_only():
    for token in (
        "decision_learning_attributions",
        "outcome_record",
        "decision_record",
        "la.learning_state='attributed'",
        "verified_success",
        "verified_failure",
    ):
        assert token in PERSISTENCE


def test_bff_proves_authoritative_dataset():
    assert "/api/v1/learning/calibration-dataset" in ROUTER
    assert "Permission.DECISION_LEARNING_ATTRIBUTE" in ROUTER
    assert "did not prove an authoritative calibration dataset" in ROUTER
    assert "async def get_calibration_dataset" in CLIENT


def test_equipment_attributions_excluded_from_calibration_and_evaluation(monkeypatch):
    """Exercise both runtime readers on migrated PG column types, including historical rows."""
    import asyncio
    import os
    from types import SimpleNamespace
    from uuid import uuid4

    import pytest

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("requires migrated decision-service Postgres")
    import asyncpg
    import persistence

    tenant = str(uuid4())
    other = str(uuid4())

    async def connect_with_fixture():
        conn = await asyncpg.connect(dsn)
        try:
            # Clone the migrated columns, without constraints, to represent unbound legacy
            # rows too. The read-model test never seeds a production table or sends a command.
            await conn.execute("""
                CREATE TEMP TABLE decision_record AS TABLE public.decision_record WITH NO DATA;
                CREATE TEMP TABLE outcome_record AS TABLE public.outcome_record WITH NO DATA;
                CREATE TEMP TABLE decision_learning_attributions AS
                    TABLE public.decision_learning_attributions WITH NO DATA;
                CREATE TEMP TABLE decision_execution_requests AS
                    TABLE public.decision_execution_requests WITH NO DATA;
                CREATE TEMP TABLE decision_model_evaluation_runs
                    (LIKE public.decision_model_evaluation_runs INCLUDING ALL);
                CREATE TEMP TABLE decision_outbox_events
                    (LIKE public.decision_outbox_events INCLUDING ALL);
            """)
            for name, mode, success, owner in [
                ("task-good", "task", True, tenant),
                ("task-failed", "task", False, tenant),
                ("equipment-failed", "equipment", False, tenant),
                ("equipment-historical-success", "equipment", True, tenant),
                ("wrong-owner", "task", True, other),
                ("missing-request", None, True, tenant),
            ]:
                await conn.execute(
                    """INSERT INTO decision_record
                       (decision_id,tenant_id,field_id,season_id,crop_id,cultivar_id,
                        agronomic_context_snapshot_id,vegetation_snapshot_id,
                        field_historical_context_snapshot_id,feature_manifest_id,feature_manifest_hash)
                       VALUES ($1,$2,'field','season','crop','cultivar','ac','veg','hist','fm',repeat('a',64))""",
                    name,
                    tenant,
                )
                await conn.execute(
                    """INSERT INTO outcome_record (outcome_id,tenant_id,execution_request_id,
                       decision_id,success,verification_state) VALUES ($1,$2,$1,$1,$3,$4)""",
                    name,
                    tenant,
                    success,
                    "verified_success" if success else "verified_failure",
                )
                await conn.execute(
                    """INSERT INTO decision_learning_attributions
                       (tenant_id,learning_attribution_id,outcome_id,decision_id,execution_request_id,
                        model_id,label,weight,evidence_snapshot_id,learning_state)
                       VALUES ($1,$2,$2,$2,$2,'model',$3,1,'ev','attributed')""",
                    tenant,
                    name,
                    "success" if success else "failure",
                )
                if mode is not None:
                    await conn.execute(
                        """INSERT INTO decision_execution_requests
                           (tenant_id,execution_request_id,decision_id,target_type)
                           VALUES ($1,$2,$2,$3)""",
                        owner,
                        name,
                        mode,
                    )
            return conn
        except BaseException:
            await conn.close()
            raise

    async def verify():
        dataset = await persistence.build_calibration_dataset(
            tenant_id=tenant, model_id="model", feature_set_id=None, limit=10
        )
        assert {item["outcome_id"] for item in dataset["items"]} == {"task-good", "task-failed"}
        assert dataset["weighted_success_rate"] == 0.5
        result = await persistence.create_model_evaluation_run(
            tenant_id=tenant,
            evaluated_by="tester",
            payload=SimpleNamespace(
                model_id="model",
                feature_set_id=None,
                dataset_count=2,
                dataset_fingerprint=dataset["dataset_fingerprint"],
                evaluator_version="fixture",
                baseline_metrics={},
                candidate_metrics={},
                candidate_artifact_uri="urn:test:artifact",
                candidate_artifact_digest="d" * 64,
                artifact_format="onnx",
                metadata={},
                idempotency_key="fixture-evaluation",
            ),
        )
        assert result["status"] == "ok"
        assert result["dataset_fingerprint"] == dataset["dataset_fingerprint"]
        assert result["dataset_count"] == 2

    monkeypatch.setattr(persistence, "_connect", connect_with_fixture)
    asyncio.run(verify())
