"""Disposable PG16 proof, never a staging probe.

Run only against the dedicated loopback CI database below. Each case creates its
own database and LOGIN role, applies the real 001..032 runner, then tests 033.
Application compatibility assertions are deliberately NOT xfailed: a restrictive
policy passing in isolation does not mean existing writers/readers can use it.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import migration_runner as runner
import persistence
import pytest
import pytest_asyncio

ADMIN_DSN = "postgresql://decision033_admin:disposable_test_only@127.0.0.1:5436/decision033_test"
TENANT = "00000000-0000-0000-0000-000000000033"
OTHER = "00000000-0000-0000-0000-000000000034"
VERSION = "033_tenant_boundary_hardening.sql"
TABLES = ("decision_outbox_events", "decision_reviews")


def _configured_dsn() -> str:
    value = os.getenv("DECISION_033_TEST_DATABASE_URL", "")
    if not value:
        if os.getenv("DECISION_033_REQUIRE_PG16") == "1":
            pytest.fail("PG16 proof is required; dedicated test database is missing")
        pytest.skip("requires the dedicated disposable PostgreSQL 16 job")
    # An exact allowlist prevents reuse with Railway DSNs, secrets, or arbitrary DBs.
    if value != ADMIN_DSN:
        pytest.fail("refusing a non-disposable/non-loopback database target")
    return value


async def _connect(dsn):
    return await asyncpg.connect(
        dsn,
        statement_cache_size=0,
        timeout=10,
        command_timeout=20,
        server_settings={"lock_timeout": "5s", "statement_timeout": "15s"},
    )


@pytest_asyncio.fixture
async def database(monkeypatch):
    """Admin is used for setup/inspection only; application calls authenticate afresh."""
    root = await _connect(_configured_dsn())
    suffix = uuid4().hex
    dbname, role = f"decision033_{suffix}", f"decision033_app_{suffix}"
    admin = None
    db_created = role_created = False
    try:
        version = int(await root.fetchval("SHOW server_version_num"))
        assert 160000 <= version < 170000, "this witness requires PostgreSQL 16"
        await root.execute(f'CREATE DATABASE "{dbname}"')
        db_created = True
        await root.execute(
            f"CREATE ROLE \"{role}\" LOGIN PASSWORD 'disposable_test_only' "
            "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT"
        )
        role_created = True
        parts = urlsplit(ADMIN_DSN)
        admin_dsn = urlunsplit(parts._replace(path=f"/{dbname}"))
        app_dsn = urlunsplit(
            parts._replace(netloc=f"{role}:disposable_test_only@127.0.0.1:5436", path=f"/{dbname}")
        )
        admin = await _connect(admin_dsn)

        async def admin_connection():
            return await _connect(admin_dsn)

        async def app_connection():
            return await _connect(app_dsn)

        monkeypatch.setattr(runner, "_connect", admin_connection)
        monkeypatch.setattr(persistence, "_connect", app_connection)
        monkeypatch.setenv("DECISION_SERVICE_ALLOW_SCHEMA_CHANGE", "true")
        migrations = runner.load_migrations()
        baseline = [m for m in migrations if m.version < VERSION]
        assert len(baseline) == 32
        with monkeypatch.context() as scoped:
            scoped.setattr(runner, "load_migrations", lambda: baseline)
            assert (await runner.apply_migrations())["ok"]
        await admin.execute(f'GRANT USAGE, CREATE ON SCHEMA public TO "{role}"')
        await admin.execute(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"'
        )
        await admin.execute(f'GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO "{role}"')
        app = await app_connection()
        try:
            identity = await app.fetchrow(
                "SELECT current_user AS role, session_user AS session, "
                "rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname=current_user"
            )
            assert dict(identity) == {
                "role": role,
                "session": role,
                "rolsuper": False,
                "rolbypassrls": False,
                "rolcanlogin": True,
            }
            assert not await app.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_auth_members "
                "WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user))"
            )
            assert not await app.fetchval("SELECT current_setting('app.current_tenant', true)")
        finally:
            await app.close()
        yield SimpleNamespace(
            admin=admin, admin_connection=admin_connection, app_connection=app_connection, role=role
        )
    finally:
        if admin is not None:
            await admin.close()
        # Names are generated here, not supplied by environment or user input.
        if db_created:
            await root.execute(f'DROP DATABASE "{dbname}"')
        if role_created:
            await root.execute(f'DROP ROLE "{role}"')
        await root.close()


async def _insert(conn, table, row_id, tenant):
    if table == "decision_outbox_events":
        await conn.execute(
            "INSERT INTO decision_outbox_events "
            "(event_id,tenant_id,event_type,aggregate_type,aggregate_id) "
            "VALUES ($1,$2::uuid,'CI_ONLY','ci_probe',$1)",
            row_id,
            tenant,
        )
    else:
        assert table == "decision_reviews"
        await conn.execute(
            "INSERT INTO decision_reviews "
            "(review_id,decision_id,tenant_id,action,previous_state,new_state,"
            "reviewed_by,candidate_lineage_id,idempotency_key,request_hash,policy_version) "
            "VALUES ($1,$1,$2::uuid,'approve','pending_approval','approved',"
            "'ci-reviewer','ci-lineage',$1,'ci-hash','ci-policy')",
            row_id,
            tenant,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("owns_table", [False, True], ids=["nonowner", "forced-owner"])
async def test_033_isolates_reads_writes_and_rolls_back(database, table, owns_table):
    assert (await runner.apply_migrations())["applied_now"] == [VERSION]
    if owns_table:
        await database.admin.execute(f'ALTER TABLE {table} OWNER TO "{database.role}"')
    app = await database.app_connection()
    try:
        flags = await app.fetchrow(
            "SELECT relrowsecurity, relforcerowsecurity, "
            "pg_get_userbyid(relowner)=current_user AS owns FROM pg_class WHERE oid=$1::regclass",
            table,
        )
        assert tuple(flags) == (True, True, owns_table)
        tx = app.transaction()
        await tx.start()
        try:
            await app.execute("SELECT set_config('app.current_tenant',$1,true)", TENANT)
            await _insert(app, table, "ci-own", TENANT)
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 1
            # Savepoints preserve the outer transaction after expected RLS errors.
            with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
                async with app.transaction():
                    await _insert(app, table, "ci-cross", OTHER)
            await app.execute("SELECT set_config('app.current_tenant',$1,true)", OTHER)
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 0
            await app.execute("SELECT set_config('app.current_tenant','',true)")
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 0
            with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
                async with app.transaction():
                    await _insert(app, table, "ci-missing", TENANT)
        finally:
            await tx.rollback()
        assert not await app.fetchval("SELECT current_setting('app.current_tenant',true)")
        assert await database.admin.fetchval(f"SELECT count(*) FROM {table}") == 0
    finally:
        await app.close()


@pytest.mark.asyncio
async def test_033_runner_check_apply_and_reapply(database):
    before = await runner.check_migrations()
    assert before["pending"] == [VERSION] and not before["ok"]
    assert before["checksum_mismatches"] == []
    first = await runner.apply_migrations()
    assert first["ok"] and first["applied_now"] == [VERSION]
    second = await runner.apply_migrations()
    assert second["ok"] and second["applied_now"] == []
    assert (await runner.check_migrations())["pending"] == []
    assert (
        await database.admin.fetchval(
            "SELECT count(*) FROM decision_service_schema_migrations WHERE version=$1", VERSION
        )
        == 1
    )


@pytest.fixture
def observed_writers(monkeypatch):
    """Observe real INSERTs without replacing SQL, role, or transaction behavior."""
    observed = set()
    original = persistence.emit_outbox_event

    async def emit(conn, **kwargs):
        caller = sys._getframe(1).f_code.co_name
        assert conn.is_in_transaction()
        assert await conn.fetchval("SELECT current_setting('app.current_tenant', true)") == str(
            kwargs["tenant_id"]
        )
        assert not await conn.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
        await original(conn, **kwargs)
        observed.add(caller)

    monkeypatch.setattr(persistence, "emit_outbox_event", emit)
    return observed


WRITER_SCENARIOS = (
    (
        "test_wx10_9_execution_plan",
        "test_approved_decision_creates_one_planned_record_and_outbox",
        {"create_execution_plan"},
    ),
    (
        "test_wx10_10_dispatch_authorization",
        "test_planned_approved_source_creates_one_authorization_and_outbox",
        {"authorize_dispatch"},
    ),
    (
        "test_wx10_11_execution_request",
        "test_create_execution_request_and_outbox",
        {"create_execution_request"},
    ),
    (
        "test_wx10_11b_execution_delivery_receipt",
        "test_claim_then_accepted_receipt_and_outbox",
        {"claim_execution_request", "record_execution_receipt"},
    ),
    (
        "test_wx10_12_execution_outcome",
        "test_terminal_request_creates_one_immutable_outcome_and_outbox",
        {"verify_execution_outcome"},
    ),
    (
        "test_wx12_1_runtime_receipts",
        "test_rollout_receipt_persists_append_only_and_guards_missing_plan",
        {"record_rollout_receipt"},
    ),
    (
        "test_wx12_1_runtime_receipts",
        "test_dispatch_receipt_replay_vs_conflict_and_guards_missing_request",
        {"record_retraining_dispatch_receipt"},
    ),
    (
        "test_wx12_3_runtime_schedules",
        "test_monitoring_schedule_emits_due_window_and_snapshot_closes_it",
        {"record_monitoring_snapshot"},
    ),
    (
        "test_wx12_3_runtime_schedules",
        "test_reconcile_schedule_emits_and_evidence_silences_it_for_a_period",
        {"record_reconcile_evidence"},
    ),
    (
        "test_wx12_3_runtime_schedules",
        "test_schedule_create_replay_and_conflict",
        {"create_runtime_schedule"},
    ),
    (
        "test_runtime_worker_tenants",
        "test_registration_replay_conflict_and_authorization_partitioning",
        {"register_runtime_worker_tenant"},
    ),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("module_name,scenario,expected", WRITER_SCENARIOS)
async def test_existing_writer_scenarios_after_033(
    database, monkeypatch, observed_writers, module_name, scenario, expected
):
    """Reuse established domain assertions; only setup/inspection use the admin."""
    assert (await runner.apply_migrations())["ok"]
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, "_connect", database.admin_connection)
    # These existing scenarios use asyncio.run; keep them off the fixture event loop.
    # persistence._connect remains the fresh restricted LOGIN from the database fixture.
    try:
        await asyncio.to_thread(getattr(module, scenario))
    except pytest.skip.Exception as exc:
        pytest.fail(f"required writer scenario must execute: {exc}")
    assert expected <= observed_writers, (
        f"writers never reached real INSERT: {expected - observed_writers}"
    )


@pytest.mark.asyncio
async def test_033_runner_rolls_back_policy_and_journal_on_error(database, monkeypatch):
    migrations = runner.load_migrations()
    target = next(m for m in migrations if m.version == VERSION)
    broken = replace(target, sql=target.sql + "\nSELECT 1 / 0;")
    with monkeypatch.context() as scoped:
        scoped.setattr(
            runner, "load_migrations", lambda: [broken if m == target else m for m in migrations]
        )
        with pytest.raises(asyncpg.DivisionByZeroError):
            await runner.apply_migrations()
    assert (await runner.check_migrations())["pending"] == [VERSION]
    for table in TABLES:
        assert not await database.admin.fetchval(
            "SELECT relrowsecurity OR relforcerowsecurity FROM pg_class WHERE oid=$1::regclass",
            table,
        )
        assert (
            await database.admin.fetchval(
                "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=$1", table
            )
            == 0
        )
    assert (await runner.apply_migrations())["ok"]


@pytest.mark.asyncio
async def test_learning_writer_survives_033_under_restricted_login(database, observed_writers):
    payload = SimpleNamespace(
        model_id="ci-model",
        feature_set_id=None,
        learning_rate=0.01,
        sample_count=1,
        label_summary={},
        drift_score=0.0,
        action="ci-only",
        source_type="ci-probe",
        source_id="ci-source",
        field_id=None,
        season_id=None,
        recommendation_id=None,
        decision_id=None,
        evidence_snapshot_id=None,
    )
    # Positive control: the actual writer succeeds before 033 with the SAME role.
    before = await persistence.persist_learning_update(
        tenant_id=TENANT, payload=payload, update_id="ci-before", traceability_status="traceable"
    )
    assert before == {"update_id": "ci-before"}
    assert (await runner.apply_migrations())["ok"]
    try:
        after = await persistence.persist_learning_update(
            tenant_id=TENANT, payload=payload, update_id="ci-after", traceability_status="traceable"
        )
    except asyncpg.InsufficientPrivilegeError:
        # Failed outbox write must roll back the learning row, not leave a partial commit.
        assert (
            await database.admin.fetchval(
                "SELECT count(*) FROM online_learning_updates WHERE update_id='ci-after'"
            )
            == 0
        )
        raise
    assert after == {"update_id": "ci-after"}
    assert "persist_learning_update" in observed_writers
    assert (
        await database.admin.fetchval(
            "SELECT count(*) FROM decision_outbox_events WHERE aggregate_id='ci-after'"
        )
        == 1
    )


@pytest.mark.asyncio
async def test_review_idempotency_replay_survives_033_under_restricted_login(database):
    request = dict(
        tenant_id=TENANT,
        decision_id="ci-review",
        action="approve",
        new_state="approved",
        reason="ci-only",
        reviewed_by="ci-reviewer",
        candidate_lineage_id="ci-lineage",
        idempotency_key="ci-review",
        policy_version="ci-policy",
    )
    request_hash = persistence._request_hash(
        **{
            key: request[key]
            for key in ("decision_id", "action", "new_state", "reason", "candidate_lineage_id")
        }
    )
    await database.admin.execute(
        "INSERT INTO decision_record (decision_id,tenant_id,stage,decision_type,"
        "review_state,candidate_lineage_id) "
        "VALUES ('ci-review',$1::uuid,'candidate','crop_decision_candidate','approved','ci-lineage')",
        TENANT,
    )
    await database.admin.execute(
        "INSERT INTO decision_reviews (review_id,decision_id,tenant_id,action,previous_state,"
        "new_state,reason,reviewed_by,candidate_lineage_id,idempotency_key,request_hash,policy_version) "
        "VALUES ('ci-saved-review','ci-review',$1::uuid,'approve','pending_approval','approved',"
        "'ci-only','ci-reviewer','ci-lineage','ci-review',$2,'ci-policy')",
        TENANT,
        request_hash,
    )
    before = await persistence.review_decision(**request)
    assert before["status"] == "ok" and before["replay"] is True
    assert (await runner.apply_migrations())["ok"]
    after = await persistence.review_decision(**request)
    assert after == before, "033 must not hide a tenant's authoritative idempotency replay"
    assert await persistence.review_decision(**{**request, "tenant_id": OTHER}) == {
        "status": "not_found"
    }


@pytest.mark.asyncio
async def test_fresh_review_is_atomic_and_tenant_scoped_after_033(database, observed_writers):
    assert (await runner.apply_migrations())["ok"]
    await database.admin.execute(
        "INSERT INTO decision_record (decision_id,tenant_id,stage,decision_type,"
        "review_state,candidate_lineage_id) "
        "VALUES ('ci-new-review',$1::uuid,'candidate','crop_decision_candidate',"
        "'pending_approval','ci-lineage')",
        TENANT,
    )
    request = dict(
        tenant_id=TENANT,
        decision_id="ci-new-review",
        action="approve",
        new_state="approved",
        reason="ci-only",
        reviewed_by="ci-reviewer",
        candidate_lineage_id="ci-lineage",
        idempotency_key="ci-new-review",
        policy_version="ci-policy",
    )
    # Another tenant must neither transition the decision nor learn its state.
    assert await persistence.review_decision(**{**request, "tenant_id": OTHER}) == {
        "status": "not_found"
    }
    result = await persistence.review_decision(**request)
    assert result["status"] == "ok" and result["replay"] is False
    assert result["authoritative"] is True and result["persisted"] is True
    assert "review_decision" in observed_writers
    replay = await persistence.review_decision(**request)
    assert replay == {**result, "replay": True}
    assert await persistence.review_decision(**{**request, "reason": "changed"}) == {
        "status": "conflict",
        "reason": "idempotency_key_payload_mismatch",
    }
    assert (
        await database.admin.fetchval(
            "SELECT review_state FROM decision_record WHERE decision_id='ci-new-review'"
        )
        == "approved"
    )
    for table, column in (
        ("decision_reviews", "decision_id"),
        ("decision_outbox_events", "aggregate_id"),
    ):
        assert (
            await database.admin.fetchval(
                f"SELECT count(*) FROM {table} WHERE {column}='ci-new-review' AND tenant_id=$1::uuid",
                TENANT,
            )
            == 1
        )


MODEL_WRITERS = {
    "persist_decision_record",
    "compose_agronomic_context",
    "create_learning_attribution",
    "create_model_evaluation_run",
    "create_model_promotion_decision",
    "create_model_activation_request",
    "review_model_activation_request",
    "claim_model_registry_activation_command",
    "record_model_registry_activation_receipt",
    "create_post_activation_verification",
    "create_rollout_plan",
    "record_monitoring_snapshot",
    "create_retraining_request",
    "create_model_registry_rollback_command",
    "claim_model_registry_rollback_command",
    "record_model_registry_rollback_receipt",
}


@pytest.mark.asyncio
async def test_model_lifecycle_writers_after_033(database, observed_writers):
    """Execute the persisted model lifecycle; no model training or registry network I/O."""
    import main as api
    import test_agronomic_lineage_integrity as lineage

    assert (await runner.apply_migrations())["ok"]

    async def call(name, **kwargs):
        result = await getattr(persistence, name)(tenant_id=TENANT, **kwargs)
        assert result.get("status", "ok") == "ok", (name, result)
        return result

    veg = await call(
        "persist_vegetation_snapshot",
        payload=lineage._veg_payload("ci-field", "a" * 64),
        snapshot_id="ci-veg",
    )
    ctx = await call(
        "compose_agronomic_context", created_by="ci", payload=lineage._compose_payload("ci-field")
    )
    manifest_hash = await database.admin.fetchval(
        "SELECT content_hash FROM decision_feature_manifests WHERE feature_manifest_id=$1",
        ctx["feature_manifest_id"],
    )
    await call(
        "persist_decision_record",
        decision_id="ci-model-decision",
        payload=lineage._decision("ci-field", ctx, veg["snapshot_id"], manifest_hash),
    )
    await database.admin.execute(
        "INSERT INTO outcome_record(outcome_id,tenant_id,decision_id,success,verification_state,"
        "evidence_snapshot_id,execution_request_id) "
        "VALUES('ci-model-outcome',$1::uuid,'ci-model-decision',true,'verified_success',"
        "'ci-evidence','ci-model-execution')",
        TENANT,
    )
    await call(
        "create_learning_attribution",
        outcome_id="ci-model-outcome",
        attributed_by="ci",
        payload=api.LearningAttributionIn(
            model_id="ci-model",
            feature_set_id="f1",
            label="success",
            evidence_snapshot_id="ci-evidence",
            idempotency_key="ci-attribution",
        ),
    )
    # Compute the supplied dataset fingerprint from independently inspected persisted rows.
    rows = await database.admin.fetch(
        "SELECT la.*,o.verification_state,o.success FROM decision_learning_attributions la "
        "JOIN outcome_record o ON o.tenant_id=la.tenant_id AND o.outcome_id=la.outcome_id "
        "WHERE la.tenant_id=$1::uuid",
        TENANT,
    )
    assert len(rows) == 1
    fingerprint = persistence._calibration_fingerprint([dict(row) for row in rows])
    evaluation = await call(
        "create_model_evaluation_run",
        evaluated_by="ci",
        payload=api.ModelEvaluationRunIn(
            model_id="ci-model",
            feature_set_id="f1",
            dataset_fingerprint=fingerprint,
            dataset_count=1,
            evaluator_version="ci-v1",
            baseline_metrics={"accuracy": 0.5},
            candidate_metrics={"accuracy": 0.8},
            candidate_artifact_uri="s3://ci/candidate",
            candidate_artifact_digest="b" * 64,
            artifact_format="onnx",
            idempotency_key="ci-eval",
        ),
    )
    promotion = await call(
        "create_model_promotion_decision",
        decided_by="ci",
        payload=api.ModelPromotionDecisionIn(
            evaluation_run_id=evaluation["evaluation_run_id"],
            policy_version="ci-v1",
            primary_metric="accuracy",
            min_improvement=0.1,
            idempotency_key="ci-promotion",
        ),
    )
    assert promotion["decision_state"] == "promotion_eligible"
    request = await call(
        "create_model_activation_request",
        requested_by="ci",
        payload=api.ModelActivationRequestIn(
            promotion_decision_id=promotion["promotion_decision_id"],
            target_environment="staging",
            idempotency_key="ci-activation",
        ),
    )
    review = await call(
        "review_model_activation_request",
        activation_request_id=request["activation_request_id"],
        reviewed_by="ci",
        payload=api.ModelActivationReviewIn(
            review_decision="approved",
            review_reason="ci-only",
            registry_alias="ci-alias",
            previous_artifact_uri="s3://ci/previous",
            previous_artifact_digest="c" * 64,
            idempotency_key="ci-activation-review",
        ),
    )
    command_id = review["activation_command"]["activation_command_id"]
    await call(
        "claim_model_registry_activation_command",
        command_id=command_id,
        adapter_id="ci-adapter",
        delivery_token="ci-activation-token",
    )
    receipt = await call(
        "record_model_registry_activation_receipt",
        command_id=command_id,
        recorded_by="ci",
        payload=api.ModelRegistryActivationReceiptIn(
            adapter_id="ci-adapter",
            delivery_token="ci-activation-token",
            receipt_state="activated",
            active_artifact_uri="s3://ci/candidate",
            active_artifact_digest="b" * 64,
            registry_version="ci-v1",
            idempotency_key="ci-activation-receipt",
        ),
    )
    receipt_id = receipt["activation_receipt_id"]
    await call(
        "create_post_activation_verification",
        receipt_id=receipt_id,
        verified_by="ci",
        payload=api.PostActivationVerificationIn(
            verification_state="verified_healthy",
            artifact_digest="b" * 64,
            idempotency_key="ci-verification",
        ),
    )
    await call(
        "create_rollout_plan",
        receipt_id=receipt_id,
        requested_by="ci",
        payload=api.RolloutPlanIn(mode="canary", traffic_percent=10, idempotency_key="ci-rollout"),
    )
    now = datetime.now(UTC)
    monitor = await call(
        "record_monitoring_snapshot",
        captured_by="ci",
        payload=api.MonitoringSnapshotIn(
            model_id="ci-model",
            feature_set_id="f1",
            target_environment="staging",
            window_start=now - timedelta(hours=1),
            window_end=now,
            sample_count=1,
            drift_state="warning",
            idempotency_key="ci-monitor",
        ),
    )
    await call(
        "create_retraining_request",
        requested_by="ci",
        payload=api.RetrainingRequestIn(
            model_id="ci-model",
            feature_set_id="f1",
            target_environment="staging",
            source_monitoring_snapshot_id=monitor["monitoring_snapshot_id"],
            dataset_fingerprint=fingerprint,
            training_manifest={"dataset": "ci-only"},
            code_version="ci-v1",
            idempotency_key="ci-retrain",
        ),
    )
    rollback = await call(
        "create_model_registry_rollback_command",
        receipt_id=receipt_id,
        requested_by="ci",
        payload=api.ModelRegistryRollbackIn(reason="ci-only", idempotency_key="ci-rollback"),
    )
    rollback_id = rollback["rollback_command_id"]
    await call(
        "claim_model_registry_rollback_command",
        command_id=rollback_id,
        adapter_id="ci-adapter",
        delivery_token="ci-rollback-token",
    )
    await call(
        "record_model_registry_rollback_receipt",
        command_id=rollback_id,
        recorded_by="ci",
        payload=api.ModelRegistryRollbackReceiptIn(
            adapter_id="ci-adapter",
            delivery_token="ci-rollback-token",
            receipt_state="rolled_back",
            active_artifact_uri="s3://ci/previous",
            active_artifact_digest="c" * 64,
            registry_version="ci-v2",
            idempotency_key="ci-rollback-receipt",
        ),
    )
    assert MODEL_WRITERS <= observed_writers, MODEL_WRITERS - observed_writers
    assert await database.admin.fetchval(
        "SELECT count(*) FROM decision_outbox_events WHERE tenant_id=$1::uuid", TENANT
    ) >= len(MODEL_WRITERS)


BASELINE_WRITERS = {
    "persist_dispatch_decision",
    "persist_outcome_record",
    "persist_recommendation_outcome",
}


@pytest.mark.asyncio
async def test_baseline_outbox_writers_after_033(database, observed_writers):
    import main as api

    assert (await runner.apply_migrations())["ok"]
    dispatch = await persistence.persist_dispatch_decision(
        tenant_id=TENANT,
        decision_id="ci-dispatch",
        payload=api.DispatchDecisionIn(recommendation_id="ci-rec", action_type="irrigation"),
    )
    assert dispatch["decision_id"] == "ci-dispatch"
    outcome = await persistence.persist_outcome_record(
        tenant_id=TENANT,
        outcome_id="ci-basic-outcome",
        payload=api.OutcomeRecordIn(decision_id="ci-dispatch", idempotency_key="ci-basic-outcome"),
    )
    assert outcome["outcome_id"] == "ci-basic-outcome"
    recommendation = await persistence.persist_recommendation_outcome(
        tenant_id=TENANT,
        payload=api.RecommendationOutcomeIn(
            recommendation_id="ci-rec", decision_id="ci-dispatch", idempotency_key="ci-rec"
        ),
    )
    assert recommendation["outcome_id"]
    assert BASELINE_WRITERS <= observed_writers


def test_every_outbox_writer_has_a_pg16_witness_and_binds_before_sql():
    source = Path(persistence.__file__).read_text()
    witnessed = BASELINE_WRITERS | MODEL_WRITERS | {"persist_learning_update", "review_decision"}
    for _, _, names in WRITER_SCENARIOS:
        witnessed |= names
    discovered = set()
    for fn in ast.parse(source).body:
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        emitters = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "emit_outbox_event"
        ]
        if not emitters:
            continue
        discovered.add(fn.name)
        transactions = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.AsyncWith)
            and any(ast.unparse(item.context_expr) == "conn.transaction()" for item in n.items)
        ]
        assert len(transactions) == 1, fn.name
        tenant = next(k.value for k in emitters[0].keywords if k.arg == "tenant_id")
        expected = ast.parse(
            "await conn.execute(\"SELECT set_config('app.current_tenant', $1, true)\", "
            + ast.unparse(tenant)
            + ")"
        ).body[0]
        assert ast.dump(transactions[0].body[0]) == ast.dump(expected), fn.name
    assert discovered == witnessed, {
        "uncovered": discovered - witnessed,
        "stale": witnessed - discovered,
    }
