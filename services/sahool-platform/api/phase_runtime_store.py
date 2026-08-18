"""Optional persistent runtime store for Phase 9-12 facades.

The Phase 9-12 shared modules stay deterministic and dependency-light. This
adapter is the thin runtime activation layer: if the FastAPI app exposes
``app.state.db_pool`` it persists outputs into the Phase migration tables; if no
pool is available it returns a truthful ``persisted=False`` marker without
breaking local contract tests.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def _persistence_required(request: Request | None = None) -> bool:
    values = {
        os.getenv("PHASE_RUNTIME_PERSISTENCE_REQUIRED", ""),
        os.getenv("SAHOOL_ENV", ""),
        os.getenv("APP_ENV", ""),
        os.getenv("ENVIRONMENT", ""),
    }
    if request is not None:
        try:
            values.add(str(getattr(request.app.state, "phase_runtime_persistence_required", "")))
        except Exception:  # noqa: BLE001 — قراءة علم اختياريّ من app.state؛ غيابه يُتجاهَل بأمان
            pass
    normalized = {str(v).strip().lower() for v in values if v is not None}
    return bool(normalized & {"1", "true", "yes", "required", "production", "prod", "staging"})


def _missing_runtime_dependency(
    request: Request, reason: str, *, status_code: int = 503
) -> dict[str, Any]:
    if _persistence_required(request):
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": "phase_runtime_persistence_required",
                "reason": reason,
                "hint": "Configure app.state.db_pool and X-Tenant-Id/app.current_tenant for Phase 9-12 runtime writes.",
            },
        )
    return {"persisted": False, "reason": reason}


def _tenant_required(
    request: Request, tenant: UUID | None, reason: str = "x_tenant_id_missing"
) -> dict[str, Any] | None:
    if tenant is None and _persistence_required(request):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "phase_runtime_tenant_required",
                "reason": reason,
                "hint": "Send X-Tenant-Id and ensure the DB session sets app.current_tenant before RLS-protected writes.",
            },
        )
    return None


def tenant_id_from_request(request: Request, fallback: str | None = None) -> str | None:
    return request.headers.get("x-tenant-id") or request.headers.get("X-Tenant-Id") or fallback


def _pool(request: Request):
    return getattr(request.app.state, "db_pool", None)


def _uuid(value: Any) -> UUID | None:
    if value in (None, "", "None"):
        return None
    try:
        return UUID(str(value))
    except Exception:  # noqa: BLE001 — تحويل UUID اختياريّ؛ قيمة غير صالحة ⇒ None بأمان
        return None


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


async def _set_rls_tenant(conn: Any, tenant: UUID | None) -> None:
    """Bind PostgreSQL RLS context when tenant is known.

    The Phase 9-12 migrations now accept app.current_tenant as canonical
    while preserving app.tenant_id compatibility. Setting both transaction-locally before writes closes the gap where RLS was defined but
    the request context was not guaranteed to reach the database session.
    """
    if tenant is not None:
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant))
        await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant))


def _event_id(event: dict[str, Any]) -> str:
    return str(event.get("event_id") or f"evt_{hash(_json(event)) & 0xFFFFFFFF:x}")


async def persist_runtime_event(
    request: Request,
    *,
    tenant: UUID | None,
    field: UUID | None,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict[str, Any],
    status: str = "pending",
) -> dict[str, Any]:
    pool = _pool(request)
    if pool is None:
        return _missing_runtime_dependency(request, "db_pool_missing")
    tenant_error = _tenant_required(request, tenant)
    if tenant_error is not None:
        return tenant_error
    event = {
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "event_type": event_type,
        "payload": payload,
    }
    async with pool.acquire() as conn:
        await _set_rls_tenant(conn, tenant)
        await conn.execute(
            """
            INSERT INTO runtime_event_outbox
                (tenant_id, field_id, event_id, aggregate_type, aggregate_id, event_type, payload, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8)
            ON CONFLICT (event_id) DO NOTHING
            """,
            tenant,
            field,
            _event_id(event),
            aggregate_type,
            aggregate_id,
            event_type,
            _json(payload),
            status,
        )
    return {"persisted": True, "event_type": event_type}


async def persist_phase9_plan(request: Request, plan: dict[str, Any]) -> dict[str, Any]:
    pool = _pool(request)
    tenant = _uuid(plan.get("tenant_id") or tenant_id_from_request(request))
    field = _uuid(plan.get("field_id"))
    tenant_error = _tenant_required(request, tenant)
    if tenant_error is not None:
        return tenant_error
    if pool is None or field is None:
        return _missing_runtime_dependency(request, "db_pool_or_valid_field_id_missing")
    async with pool.acquire() as conn:
        await _set_rls_tenant(conn, tenant)
        row = await conn.fetchrow(
            """
            INSERT INTO autonomous_execution_plan
                (tenant_id, field_id, recommendation_id, source_state_id, mode, status, safety_gate, verification_plan)
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb)
            RETURNING id
            """,
            tenant,
            field,
            str(plan.get("recommendation_id")),
            str(plan.get("source_state_id")),
            str(plan.get("mode")),
            str(plan.get("status")),
            _json(plan.get("safety_gate")),
            _json(plan.get("verification_plan")),
        )
        plan_id = row["id"]
        for cmd in plan.get("commands") or []:
            await conn.execute(
                """
                INSERT INTO actuator_command_outbox
                    (tenant_id, field_id, execution_plan_id, command_id, actuator_type, protocol, target_id,
                     command, idempotency_key, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,'pending')
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                tenant,
                field,
                plan_id,
                str(cmd.get("command_id")),
                str(cmd.get("actuator_type")),
                str(cmd.get("protocol")),
                str(cmd.get("target_id")),
                _json(cmd.get("command")),
                str(cmd.get("idempotency_key")),
            )
    return {
        "persisted": True,
        "execution_plan_id": str(plan_id),
        "commands": len(plan.get("commands") or []),
    }


async def persist_phase9_verification(
    request: Request,
    result: dict[str, Any],
    execution_plan: dict[str, Any],
    telemetry: dict[str, Any],
) -> dict[str, Any]:
    pool = _pool(request)
    field = _uuid(execution_plan.get("field_id"))
    tenant = _uuid(execution_plan.get("tenant_id") or tenant_id_from_request(request))
    tenant_error = _tenant_required(request, tenant)
    if tenant_error is not None:
        return tenant_error
    if pool is None or field is None:
        return _missing_runtime_dependency(request, "db_pool_or_valid_field_id_missing")
    async with pool.acquire() as conn:
        await _set_rls_tenant(conn, tenant)
        await conn.execute(
            """
            INSERT INTO execution_verification_event
                (tenant_id, field_id, execution_id, recommendation_id, status, telemetry, field_response)
            VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb)
            """,
            tenant,
            field,
            str(execution_plan.get("execution_id")),
            str(execution_plan.get("recommendation_id")),
            str(result.get("status") or result.get("verification_status") or "verified"),
            _json(telemetry),
            _json(result),
        )
    return {"persisted": True}


async def persist_model_version(request: Request, model: dict[str, Any]) -> dict[str, Any]:
    pool = _pool(request)
    if pool is None:
        return _missing_runtime_dependency(request, "db_pool_missing")
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO model_registry_version
                (model_id, name, task, version, status, metrics, training_feature_sets)
            VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb)
            ON CONFLICT (name, task, version) DO UPDATE SET
                status = EXCLUDED.status,
                metrics = EXCLUDED.metrics,
                training_feature_sets = EXCLUDED.training_feature_sets
            """,
            str(model.get("model_id")),
            str(model.get("name")),
            str(model.get("task")),
            str(model.get("version")),
            str(model.get("status", "candidate")),
            _json(model.get("metrics")),
            _json(model.get("training_feature_sets", [])),
        )
    return {"persisted": True}


async def persist_feature_dataset(
    request: Request, spec: dict[str, Any], dataset: dict[str, Any]
) -> dict[str, Any]:
    pool = _pool(request)
    tenant = _uuid(tenant_id_from_request(request))
    tenant_error = _tenant_required(request, tenant)
    if tenant_error is not None:
        return tenant_error
    if pool is None or tenant is None:
        return _missing_runtime_dependency(request, "db_pool_or_x_tenant_id_missing")
    async with pool.acquire() as conn:
        await _set_rls_tenant(conn, tenant)
        await conn.execute(
            """
            INSERT INTO feature_set_specs
                (tenant_id, feature_set_id, name, version, entity_type, feature_names, label_names, freshness_hours, quality_gates)
            VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9::jsonb)
            ON CONFLICT (tenant_id, feature_set_id) DO UPDATE SET quality_gates = EXCLUDED.quality_gates
            """,
            tenant,
            str(spec.get("feature_set_id")),
            str(spec.get("name")),
            str(spec.get("version")),
            str(spec.get("entity_type")),
            _json(spec.get("feature_names", [])),
            _json(spec.get("label_names", [])),
            int(spec.get("freshness_hours", 24)),
            _json(spec.get("quality_gates")),
        )
        await conn.execute(
            """
            INSERT INTO training_datasets
                (tenant_id, dataset_id, feature_set_id, entity_type, entity_count, row_count, status, quality, object_uri)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
            ON CONFLICT (tenant_id, dataset_id) DO UPDATE SET status = EXCLUDED.status, quality = EXCLUDED.quality
            """,
            tenant,
            str(dataset.get("dataset_id")),
            str(dataset.get("feature_set_id")),
            str(dataset.get("entity_type")),
            int(dataset.get("entity_count", 0)),
            int(dataset.get("row_count", 0)),
            str(dataset.get("status")),
            _json(dataset.get("quality")),
            dataset.get("object_uri"),
        )
        for rec in dataset.get("records", []) or []:
            entity_id = str(rec.get("entity_id"))
            await conn.execute(
                """
                INSERT INTO online_feature_values
                    (tenant_id, entity_type, entity_id, feature_set_id, event_time, values, labels, quality)
                VALUES ($1,$2,$3,$4,COALESCE($5::timestamptz, now()),$6::jsonb,$7::jsonb,$8::jsonb)
                ON CONFLICT (tenant_id, entity_type, entity_id, feature_set_id, event_time)
                DO UPDATE SET values = EXCLUDED.values, labels = EXCLUDED.labels, quality = EXCLUDED.quality
                """,
                tenant,
                str(rec.get("entity_type", dataset.get("entity_type", "field"))),
                entity_id,
                str(dataset.get("feature_set_id")),
                rec.get("event_time"),
                _json(rec.get("features")),
                _json(rec.get("labels")),
                _json(rec.get("quality")),
            )
    return {"persisted": True, "online_rows": len(dataset.get("records", []) or [])}


async def persist_phase9_feature_batch(
    request: Request, plan: dict[str, Any], records: list[dict[str, Any]]
) -> dict[str, Any]:
    pool = _pool(request)
    tenant = _uuid(plan.get("tenant_id") or tenant_id_from_request(request))
    tenant_error = _tenant_required(request, tenant)
    if tenant_error is not None:
        return tenant_error
    if pool is None or tenant is None:
        return _missing_runtime_dependency(request, "db_pool_or_tenant_missing")
    async with pool.acquire() as conn:
        await _set_rls_tenant(conn, tenant)
        for rec in records:
            await conn.execute(
                """
                INSERT INTO field_feature_store_candidate
                    (tenant_id, entity_type, entity_id, feature_id, feature_set, source_state_id, event_time, features, labels, quality)
                VALUES ($1,$2,$3,$4,$5,$6,COALESCE($7::timestamptz, now()),$8::jsonb,$9::jsonb,$10::jsonb)
                ON CONFLICT (feature_id) DO UPDATE SET
                    features = EXCLUDED.features, labels = EXCLUDED.labels, quality = EXCLUDED.quality
                """,
                tenant,
                str(rec.get("entity_type")),
                str(rec.get("entity_id")),
                str(rec.get("feature_id")),
                str(rec.get("feature_set")),
                rec.get("source_state_id"),
                rec.get("event_time"),
                _json(rec.get("features")),
                _json(rec.get("labels")),
                _json(rec.get("quality")),
            )
    return {"persisted": True, "features": len(records)}


async def persist_iot_dispatch_batch(
    request: Request, execution_plan: dict[str, Any], batch: dict[str, Any]
) -> dict[str, Any]:
    """Persist Phase 9 IoT dispatch attempts without requiring live hardware.

    The table is append-only by idempotency key/envelope to support replay,
    forensic review and worker pickup. Missing DB/pool returns a truthful
    non-persisted marker instead of pretending success.
    """
    pool = _pool(request)
    tenant = _uuid(execution_plan.get("tenant_id") or tenant_id_from_request(request))
    field = _uuid(execution_plan.get("field_id"))
    tenant_error = _tenant_required(request, tenant)
    if tenant_error is not None:
        return tenant_error
    if pool is None or tenant is None or field is None:
        return _missing_runtime_dependency(request, "db_pool_or_valid_tenant_field_missing")
    rows = 0
    async with pool.acquire() as conn:
        await _set_rls_tenant(conn, tenant)
        for result in batch.get("results") or []:
            await conn.execute(
                """
                INSERT INTO iot_command_dispatch
                    (tenant_id, field_id, execution_id, dispatch_batch_id, envelope_id, command_id,
                     protocol, target_id, status, physical_effect, reason, adapter_receipt, verification_contract)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13::jsonb)
                ON CONFLICT (tenant_id, envelope_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    physical_effect = EXCLUDED.physical_effect,
                    adapter_receipt = EXCLUDED.adapter_receipt,
                    verification_contract = EXCLUDED.verification_contract
                """,
                tenant,
                field,
                str(execution_plan.get("execution_id")),
                str(batch.get("dispatch_batch_id")),
                str(result.get("envelope_id")),
                str(result.get("command_id")),
                str(result.get("protocol")),
                str(result.get("target_id")),
                str(result.get("status")),
                bool(result.get("physical_effect")),
                result.get("reason"),
                _json(result.get("adapter_receipt")),
                _json(result.get("verification_contract")),
            )
            rows += 1
    return {
        "persisted": True,
        "rows": rows,
        "dispatch_batch_id": str(batch.get("dispatch_batch_id")),
    }


async def persist_phase10_learning_outputs(
    request: Request, outputs: dict[str, Any]
) -> dict[str, Any]:
    pool = _pool(request)
    tenant = _uuid(tenant_id_from_request(request))
    tenant_error = _tenant_required(request, tenant)
    if tenant_error is not None:
        return tenant_error
    if pool is None or tenant is None:
        return _missing_runtime_dependency(request, "db_pool_or_x_tenant_id_missing")
    async with pool.acquire() as conn:
        await _set_rls_tenant(conn, tenant)
        promotion = outputs.get("model_promotion") or {}
        if promotion:
            await conn.execute(
                """
                INSERT INTO model_lifecycle_decisions
                    (tenant_id, decision_id, task, champion_model_id, challenger_model_id, decision, reasons, metric_deltas, rollout)
                VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9::jsonb)
                ON CONFLICT (tenant_id, decision_id) DO UPDATE SET decision = EXCLUDED.decision, rollout = EXCLUDED.rollout
                """,
                tenant,
                str(promotion.get("decision_id")),
                str(promotion.get("task")),
                promotion.get("champion_model_id"),
                promotion.get("challenger_model_id"),
                str(promotion.get("decision")),
                _json(promotion.get("reasons", [])),
                _json(promotion.get("metric_deltas", {})),
                _json(promotion.get("rollout", {})),
            )
        update = outputs.get("online_learning_update") or {}
        if update:
            # جسر #2: نَسَب المصدر — كلّ تحديث تعلّم يُحَلّ مصدره وحالة قابليّة تتبّعه قبل
            # الكتابة. صدق: تحديث بلا مصدر ⇒ traceability_status='rejected_untraceable'.
            from core.learning_source_lineage import resolve_learning_source

            _lin = resolve_learning_source(update)
            from api.decision_service_client import (
                record_learning_update as _mirror_learning_update_to_service,
            )
            from api.decision_sor_mode import (
                assert_platform_may_write_decision_sor,
                get_platform_decision_sor_mode,
            )

            service_payload = {
                "update_id": str(update.get("update_id")),
                "model_id": str(update.get("model_id")),
                "feature_set_id": str(update.get("feature_set_id")),
                "learning_rate": float(update.get("learning_rate", 0.01)),
                "sample_count": int(update.get("sample_count", 0)),
                "label_summary": update.get("label_summary", {}),
                "drift_score": float(update.get("drift_score", 0)),
                "action": str(update.get("action")),
                "source_type": _lin["source_type"],
                "source_id": _lin["source_id"],
                "field_id": _lin["field_id"],
                "season_id": _lin["season_id"],
                "recommendation_id": _lin["recommendation_id"],
                "decision_id": _lin["decision_id"],
                "evidence_snapshot_id": _lin["evidence_snapshot_id"],
            }
            mode = get_platform_decision_sor_mode()
            if mode.strict_decision_service_required:
                service_result = await _mirror_learning_update_to_service(
                    service_payload,
                    tenant_id=str(tenant),
                )
                if not service_result.get("authoritative") or not service_result.get("persisted"):
                    raise RuntimeError(
                        "decision-service did not prove authoritative learning-update persistence"
                    )
            else:
                assert_platform_may_write_decision_sor("online_learning_updates")
                await conn.execute(
                    """
                    INSERT INTO online_learning_updates
                        (tenant_id, update_id, model_id, feature_set_id, learning_rate, sample_count,
                         label_summary, drift_score, action, source_type, source_id, field_id, season_id,
                         recommendation_id, decision_id, evidence_snapshot_id, traceability_status)
                    VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
                    ON CONFLICT (tenant_id, update_id) DO UPDATE SET
                        action = EXCLUDED.action, drift_score = EXCLUDED.drift_score,
                        source_type = EXCLUDED.source_type, source_id = EXCLUDED.source_id,
                        traceability_status = EXCLUDED.traceability_status
                    """,
                    tenant,
                    str(update.get("update_id")),
                    str(update.get("model_id")),
                    str(update.get("feature_set_id")),
                    float(update.get("learning_rate", 0.01)),
                    int(update.get("sample_count", 0)),
                    _json(update.get("label_summary", {})),
                    float(update.get("drift_score", 0)),
                    str(update.get("action")),
                    _lin["source_type"],
                    _lin["source_id"],
                    _lin["field_id"],
                    _lin["season_id"],
                    _lin["recommendation_id"],
                    _lin["decision_id"],
                    _lin["evidence_snapshot_id"],
                    _lin["traceability_status"],
                )
            # Pre-cutover only: mirror after the authoritative platform write. In strict
            # decision-service SoR mode the service call above is the sole authoritative write.
            if not mode.strict_decision_service_required:
                try:
                    await _mirror_learning_update_to_service(
                        service_payload,
                        tenant_id=str(tenant),
                    )
                except Exception as e:  # noqa: BLE001 — pre-cutover mirror is fail-soft
                    logger.warning(
                        "decision-service mirror (learning-update %s) فشلت — كتابة المنصّة موثوقة: %s",
                        update.get("update_id"),
                        e,
                    )
        scenario = outputs.get("scenario_result") or {}
        if scenario:
            await conn.execute(
                """
                INSERT INTO scenario_runs
                    (tenant_id, scenario_id, field_id, crop, assumptions, baseline, projected, deltas, risk_flags)
                VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7::jsonb,$8::jsonb,$9::jsonb)
                ON CONFLICT (tenant_id, scenario_id) DO UPDATE SET projected = EXCLUDED.projected, deltas = EXCLUDED.deltas
                """,
                tenant,
                str(scenario.get("scenario_id")),
                _uuid(scenario.get("field_id")),
                scenario.get("crop"),
                _json(scenario.get("assumptions", {})),
                _json(scenario.get("baseline", {})),
                _json(scenario.get("projected", {})),
                _json(scenario.get("deltas", {})),
                _json(scenario.get("risk_flags", [])),
            )
        feature_runtime = outputs.get("feature_store_runtime") or {}
        registry = feature_runtime.get("registry") or {}
        feature_set = registry.get("feature_set") or {}
        if feature_set:
            await conn.execute(
                """
                INSERT INTO feature_set_versions_runtime
                    (tenant_id, feature_set_id, name, version, entity_type, feature_ids, feature_names, registry_version)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8)
                ON CONFLICT (tenant_id, feature_set_id) DO UPDATE SET
                    feature_ids = EXCLUDED.feature_ids, feature_names = EXCLUDED.feature_names
                """,
                tenant,
                str(feature_set.get("feature_set_id")),
                str(feature_set.get("name")),
                str(feature_set.get("version")),
                str(feature_set.get("entity_type")),
                _json(feature_set.get("feature_ids", [])),
                _json(feature_set.get("feature_names", [])),
                str(feature_set.get("registry_version", "feature-store.v1")),
            )
        for definition in registry.get("definitions") or []:
            await conn.execute(
                """
                INSERT INTO feature_definitions_runtime
                    (tenant_id, feature_id, name, version, entity_type, value_type, owner, ttl_hours, sources, transformations, quality_gates)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11::jsonb)
                ON CONFLICT (tenant_id, feature_id) DO UPDATE SET
                    sources = EXCLUDED.sources, transformations = EXCLUDED.transformations, quality_gates = EXCLUDED.quality_gates
                """,
                tenant,
                str(definition.get("feature_id")),
                str(definition.get("name")),
                str(definition.get("version")),
                str(definition.get("entity_type")),
                str(definition.get("value_type", "unknown")),
                str(definition.get("owner", "phase10")),
                int(definition.get("ttl_hours", 24)),
                _json(definition.get("sources", [])),
                _json(definition.get("transformations", [])),
                _json(definition.get("quality_gates", {})),
            )
        offline = feature_runtime.get("offline_dataset_version") or {}
        if offline:
            await conn.execute(
                """
                INSERT INTO offline_dataset_versions_runtime
                    (tenant_id, dataset_version_id, dataset_name, version, feature_set_id, row_count, entity_count, content_hash, object_uri, point_in_time_safe, missing_event_time_count)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (tenant_id, dataset_version_id) DO UPDATE SET object_uri = EXCLUDED.object_uri
                """,
                tenant,
                str(offline.get("dataset_version_id")),
                str(offline.get("dataset_name")),
                str(offline.get("version")),
                str(offline.get("feature_set_id")),
                int(offline.get("row_count", 0)),
                int(offline.get("entity_count", 0)),
                str(offline.get("content_hash")),
                offline.get("object_uri"),
                bool(offline.get("point_in_time_safe", False)),
                int(offline.get("missing_event_time_count", 0)),
            )
        snapshot = feature_runtime.get("point_in_time_snapshot") or {}
        if snapshot.get("snapshot_id"):
            await conn.execute(
                """
                INSERT INTO point_in_time_snapshots_runtime
                    (tenant_id, snapshot_id, feature_set_id, as_of, row_count, excluded_count, rows)
                VALUES ($1,$2,$3,$4::timestamptz,$5,$6,$7::jsonb)
                ON CONFLICT (tenant_id, snapshot_id) DO NOTHING
                """,
                tenant,
                str(snapshot.get("snapshot_id")),
                str((feature_runtime.get("offline_dataset_version") or {}).get("feature_set_id")),
                str(snapshot.get("as_of")),
                int(snapshot.get("row_count", 0)),
                int(snapshot.get("excluded_count", 0)),
                _json(snapshot.get("rows", [])),
            )
        model_runtime = outputs.get("model_registry_runtime") or {}
        for model in [model_runtime.get("champion"), model_runtime.get("challenger")]:
            if model:
                await conn.execute(
                    """
                    INSERT INTO model_versions_runtime
                        (tenant_id, model_id, model_name, version, task, framework, artifact_uri, artifact_hash, dataset_version_id, feature_set_id, metrics, status)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12)
                    ON CONFLICT (tenant_id, model_id) DO UPDATE SET metrics = EXCLUDED.metrics, status = EXCLUDED.status
                    """,
                    tenant,
                    str(model.get("model_id")),
                    str(model.get("model_name")),
                    str(model.get("version")),
                    str(model.get("task")),
                    str(model.get("framework", "python")),
                    str(model.get("artifact_uri")),
                    str(model.get("artifact_hash")),
                    model.get("dataset_version_id"),
                    model.get("feature_set_id"),
                    _json(model.get("metrics", {})),
                    str(model.get("status", "registered")),
                )
        serving = model_runtime.get("serving_promotion") or {}
        if serving:
            await conn.execute(
                """
                INSERT INTO model_promotion_history_runtime
                    (tenant_id, promotion_id, alias, decision, target_model_id, previous_model_id, challenger_model_id, metric_delta, reasons, rollback_target_model_id)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10)
                ON CONFLICT (tenant_id, promotion_id) DO NOTHING
                """,
                tenant,
                str(serving.get("promotion_id")),
                str(serving.get("alias")),
                str(serving.get("decision")),
                serving.get("target_model_id"),
                serving.get("previous_model_id"),
                serving.get("challenger_model_id"),
                _json(serving.get("metric_delta", {})),
                _json(serving.get("reasons", [])),
                serving.get("rollback_target_model_id"),
            )
            if serving.get("decision") == "promote" and serving.get("target_model_id"):
                await conn.execute(
                    """
                    INSERT INTO model_serving_aliases_runtime
                        (tenant_id, alias, model_id, previous_model_id, promotion_id)
                    VALUES ($1,$2,$3,$4,$5)
                    ON CONFLICT (tenant_id, alias) DO UPDATE SET
                        model_id = EXCLUDED.model_id, previous_model_id = EXCLUDED.previous_model_id,
                        promotion_id = EXCLUDED.promotion_id, updated_at = now()
                    """,
                    tenant,
                    str(serving.get("alias")),
                    str(serving.get("target_model_id")),
                    serving.get("previous_model_id"),
                    str(serving.get("promotion_id")),
                )
        rollback = model_runtime.get("rollback_plan") or {}
        if rollback:
            await conn.execute(
                """
                INSERT INTO model_rollback_history_runtime
                    (tenant_id, rollback_id, alias, from_model_id, to_model_id, reason, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (tenant_id, rollback_id) DO NOTHING
                """,
                tenant,
                str(rollback.get("rollback_id")),
                str(rollback.get("alias")),
                str(rollback.get("from_model_id")),
                str(rollback.get("to_model_id")),
                str(rollback.get("reason")),
                str(rollback.get("status", "planned")),
            )
    return {"persisted": True}


async def persist_marketplace_app(request: Request, registration: dict[str, Any]) -> dict[str, Any]:
    pool = _pool(request)
    app = registration.get("app") or {}
    manifest = app.get("manifest") or {}
    if pool is None:
        return _missing_runtime_dependency(request, "db_pool_missing")
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO marketplace_apps
                (app_key, name, version, author, category, manifest, status, risk_level, review_findings, published_at)
            VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9::jsonb,NULL)
            ON CONFLICT (app_key) DO UPDATE SET
                manifest = EXCLUDED.manifest,
                status = EXCLUDED.status,
                risk_level = EXCLUDED.risk_level,
                review_findings = EXCLUDED.review_findings,
                updated_at = now()
            """,
            str(app.get("app_id")),
            str(manifest.get("name")),
            str(manifest.get("version")),
            str(manifest.get("author")),
            str(app.get("category", "agronomy")),
            _json(manifest),
            str(app.get("status")),
            str(app.get("risk_level")),
            _json(app.get("review_findings", [])),
        )
    return {"persisted": True, "app_key": str(app.get("app_id"))}


async def persist_marketplace_installation(
    request: Request, result: dict[str, Any], app_key: str | None = None
) -> dict[str, Any]:
    pool = _pool(request)
    installation = result.get("installation") or {}
    tenant = _uuid(installation.get("tenant_id") or tenant_id_from_request(request))
    tenant_error = _tenant_required(request, tenant)
    if tenant_error is not None:
        return tenant_error
    if pool is None or tenant is None or not result.get("installed"):
        return _missing_runtime_dependency(request, "db_pool_or_tenant_or_installed_missing")
    async with pool.acquire() as conn:
        await _set_rls_tenant(conn, tenant)
        app_row = await conn.fetchrow(
            "SELECT id FROM marketplace_apps WHERE app_key = $1",
            str(app_key or installation.get("app_id")),
        )
        if app_row is None:
            return _missing_runtime_dependency(
                request, "marketplace_app_not_found", status_code=404
            )
        installed_by = _uuid(installation.get("installed_by"))
        await conn.execute(
            """
            INSERT INTO marketplace_installations
                (tenant_id, app_id, granted_permissions, status, installed_by, quota)
            VALUES ($1,$2,$3::jsonb,$4,$5,$6::jsonb)
            ON CONFLICT (tenant_id, app_id) DO UPDATE SET
                granted_permissions = EXCLUDED.granted_permissions,
                status = EXCLUDED.status,
                quota = EXCLUDED.quota
            """,
            tenant,
            app_row["id"],
            _json(installation.get("granted_permissions", [])),
            str(installation.get("status", "active")),
            installed_by,
            _json(installation.get("quota", {})),
        )
    return {"persisted": True}


async def persist_webhook_subscription(request: Request, result: dict[str, Any]) -> dict[str, Any]:
    pool = _pool(request)
    wh = result.get("webhook") or {}
    tenant = _uuid(wh.get("tenant_id") or tenant_id_from_request(request))
    if pool is None or tenant is None or not result.get("created"):
        return _missing_runtime_dependency(request, "db_pool_or_tenant_or_created_missing")
    async with pool.acquire() as conn:
        await _set_rls_tenant(conn, tenant)
        await conn.execute(
            """
            INSERT INTO webhook_subscriptions (tenant_id, url, events, secret_ref, active)
            VALUES ($1,$2,$3::jsonb,$4,$5)
            ON CONFLICT (tenant_id, url) DO UPDATE SET events = EXCLUDED.events, active = EXCLUDED.active
            """,
            tenant,
            str(wh.get("url")),
            _json(wh.get("events", [])),
            str(wh.get("secret_ref")),
            bool(wh.get("active", True)),
        )
    return {"persisted": True}


async def persist_usage_record(request: Request, result: dict[str, Any]) -> dict[str, Any]:
    pool = _pool(request)
    usage = result.get("usage") or {}
    tenant = _uuid(usage.get("tenant_id") or tenant_id_from_request(request))
    if pool is None or tenant is None or not result.get("recorded"):
        return _missing_runtime_dependency(request, "db_pool_or_tenant_or_recorded_missing")
    async with pool.acquire() as conn:
        await _set_rls_tenant(conn, tenant)
        app_row = await conn.fetchrow(
            "SELECT id FROM marketplace_apps WHERE app_key = $1", str(usage.get("app_id"))
        )
        await conn.execute(
            """
            INSERT INTO usage_metering_records (tenant_id, app_id, meter, quantity, idempotency_key, metadata)
            VALUES ($1,$2,$3,$4,$5,$6::jsonb)
            ON CONFLICT (tenant_id, app_id, idempotency_key) DO NOTHING
            """,
            tenant,
            app_row["id"] if app_row else None,
            str(usage.get("meter")),
            float(usage.get("quantity", 0)),
            str(usage.get("idempotency_key")),
            _json(usage.get("metadata")),
        )
    return {"persisted": True}


async def persist_phase11_cycle(request: Request, cycle: dict[str, Any]) -> dict[str, Any]:
    pool = _pool(request)
    tenant = _uuid(tenant_id_from_request(request) or cycle.get("tenant_id"))
    field = _uuid((cycle.get("context") or {}).get("field_id") or cycle.get("field_id"))
    tenant_error = _tenant_required(request, tenant)
    if tenant_error is not None:
        return tenant_error
    if pool is None or tenant is None:
        return _missing_runtime_dependency(request, "db_pool_or_x_tenant_id_missing")
    consensus = cycle.get("consensus") or {}
    context = cycle.get("context") or {}
    cycle_id = str(
        cycle.get("cycle_id")
        or consensus.get("consensus_id")
        or f"cycle_{hash(_json(cycle)) & 0xFFFFFFFF:x}"
    )
    async with pool.acquire() as conn:
        await _set_rls_tenant(conn, tenant)
        await conn.execute(
            """
            INSERT INTO agent_federation_cycles
                (tenant_id, field_id, cycle_id, objective, context_id, consensus_status, selected_action, dispatch_ready, payload)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)
            ON CONFLICT (cycle_id) DO UPDATE SET payload = EXCLUDED.payload
            """,
            tenant,
            field,
            cycle_id,
            str(cycle.get("objective", "optimize_field_outcome")),
            str(context.get("context_id", "runtime_context")),
            str(consensus.get("status", "unknown")),
            str((consensus.get("selected") or {}).get("action"))
            if isinstance(consensus.get("selected"), dict)
            else None,
            bool((cycle.get("operation_plan") or {}).get("dispatch_ready", False)),
            _json(cycle),
        )
        for proposal in cycle.get("proposals") or []:
            await conn.execute(
                """
                INSERT INTO agent_proposals
                    (tenant_id, cycle_id, proposal_id, agent_role, action, confidence, priority, safety_flags, evidence)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb)
                ON CONFLICT (proposal_id) DO NOTHING
                """,
                tenant,
                cycle_id,
                str(proposal.get("proposal_id")),
                str(proposal.get("agent_role")),
                str(proposal.get("action")),
                float(proposal.get("confidence", 0)),
                int(proposal.get("priority", 0)),
                _json(proposal.get("safety_flags", [])),
                _json(proposal.get("evidence", {})),
            )
        runtime_resolution = cycle.get("runtime_resolution") or {}
        if runtime_resolution.get("resolution_id"):
            await conn.execute(
                """
                INSERT INTO agent_conflict_resolutions
                    (tenant_id, field_id, cycle_id, resolution_id, status, selected_action, approval_required, confidence, conflict_reasons, vetoes, ranked_actions, payload)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb,$11::jsonb,$12::jsonb)
                ON CONFLICT (resolution_id) DO UPDATE SET payload = EXCLUDED.payload
                """,
                tenant,
                field,
                cycle_id,
                str(runtime_resolution.get("resolution_id")),
                str(runtime_resolution.get("status", "unknown")),
                runtime_resolution.get("selected_action"),
                bool(runtime_resolution.get("approval_required", True)),
                float(runtime_resolution.get("confidence", 0)),
                _json(runtime_resolution.get("conflict_reasons", [])),
                _json(runtime_resolution.get("vetoes", [])),
                _json(runtime_resolution.get("ranked_actions", [])),
                _json(runtime_resolution),
            )
        authority = cycle.get("authority_envelope") or {}
        if authority.get("envelope_id"):
            await conn.execute(
                """
                INSERT INTO agent_authority_envelopes
                    (tenant_id, field_id, cycle_id, envelope_id, allowed_authority, may_execute, may_publish_event, required_next_gate, blocked_reasons, evidence)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb)
                ON CONFLICT (envelope_id) DO NOTHING
                """,
                tenant,
                field,
                cycle_id,
                str(authority.get("envelope_id")),
                str(authority.get("allowed_authority", "advisory_blocked")),
                bool(authority.get("may_execute", False)),
                bool(authority.get("may_publish_event", False)),
                str(authority.get("required_next_gate", "human_review")),
                _json(authority.get("blocked_reasons", [])),
                _json(authority.get("evidence", {})),
            )
    return {"persisted": True, "cycle_id": cycle_id, "proposals": len(cycle.get("proposals") or [])}
