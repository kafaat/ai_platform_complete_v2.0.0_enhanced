"""Phase 9-12 runtime workers.

These workers turn the Phase 9-12 persistence tables from auditable facades into
runtime queues.  They are conservative by design: if an external dependency
(NATS, plugin executor, model serving backend, physical adapter) is not
configured, the worker records a blocked/retry state instead of pretending the
side effect happened.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Iterable
from typing import Any

import asyncpg

from shared.runtime_worker_contracts import (
    build_actuator_worker_action,
    build_model_promotion_action,
    build_model_rollback_action,
    build_outbox_action,
    build_plugin_worker_action,
    env_bool,
    parse_json_env,
)

Json = dict[str, Any]


def _json(value: Any) -> str:
    return json.dumps(value or {}, default=str, ensure_ascii=False)


async def _connect() -> asyncpg.Pool:
    database_url = os.getenv("JOBS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("JOBS_DATABASE_URL is required for Phase runtime workers")
    return await asyncpg.create_pool(
        dsn=database_url, min_size=1, max_size=int(os.getenv("WORKER_DB_POOL_MAX", "4"))
    )


async def _set_tenant(conn: Any, tenant_id: Any) -> None:
    if tenant_id:
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))
        await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))


async def _publish_nats(subject: str, payload: Json) -> None:
    nats_url = os.getenv("NATS_URL") or os.getenv("SAHOOL_NATS_URL")
    action = build_outbox_action(
        nats_url=nats_url, event_type=subject.replace("sahool.", ""), attempts=0, max_attempts=1
    )
    if action["action"] != "publish_nats":
        raise RuntimeError(action["reason"] or "nats_not_ready")
    try:
        import nats  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on runtime image
        raise RuntimeError("nats client is not installed") from exc
    nc = await nats.connect(nats_url, connect_timeout=5)
    try:
        await nc.publish(subject, json.dumps(payload, default=str).encode("utf-8"))
        await nc.flush(timeout=5)
    finally:
        await nc.close()


async def run_outbox_once(pool: asyncpg.Pool, *, batch_size: int = 25) -> int:
    max_attempts = int(os.getenv("OUTBOX_MAX_ATTEMPTS", "5"))
    nats_url = os.getenv("NATS_URL") or os.getenv("SAHOOL_NATS_URL")
    async with pool.acquire() as conn, conn.transaction():
        rows = await conn.fetch(
            """
            SELECT id, tenant_id, event_id, event_type, payload, attempts
            FROM runtime_event_outbox
            WHERE status IN ('pending','failed') AND attempts < $1
            ORDER BY created_at
            LIMIT $2
            FOR UPDATE SKIP LOCKED
            """,
            max_attempts,
            batch_size,
        )
        processed = 0
        for row in rows:
            await _set_tenant(conn, row["tenant_id"])
            action = build_outbox_action(
                nats_url=nats_url,
                event_type=row["event_type"],
                attempts=int(row["attempts"] or 0),
                max_attempts=max_attempts,
            )
            try:
                if action["action"] != "publish_nats":
                    raise RuntimeError(action.get("reason") or "outbox_not_publishable")
                subject = action["receipt"]["subject"]
                await _publish_nats(
                    subject,
                    {
                        "event_id": row["event_id"],
                        "event_type": row["event_type"],
                        "payload": row["payload"],
                    },
                )
                await conn.execute(
                    "UPDATE runtime_event_outbox SET status='published', attempts=attempts+1, published_at=now() WHERE id=$1",
                    row["id"],
                )
            except Exception:
                next_status = (
                    "dead_letter" if int(row["attempts"] or 0) + 1 >= max_attempts else "failed"
                )
                await conn.execute(
                    "UPDATE runtime_event_outbox SET status=$2, attempts=attempts+1 WHERE id=$1",
                    row["id"],
                    next_status,
                )
            processed += 1
        return processed


async def run_plugin_once(pool: asyncpg.Pool, *, batch_size: int = 25) -> int:
    plugin_enabled = env_bool("PLUGIN_EXECUTION_ENABLED", False)
    executor_url = os.getenv("PLUGIN_EXECUTOR_URL")
    async with pool.acquire() as conn, conn.transaction():
        rows = await conn.fetch(
            """
            SELECT id, tenant_id, execution_id, decision, status, sandbox_policy
            FROM marketplace_plugin_execution_runs
            WHERE status IN ('planned','pending')
            ORDER BY created_at
            LIMIT $1
            FOR UPDATE SKIP LOCKED
            """,
            batch_size,
        )
        for row in rows:
            await _set_tenant(conn, row["tenant_id"])
            action = build_plugin_worker_action(
                decision=str(row["decision"]),
                plugin_enabled=plugin_enabled,
                executor_url=executor_url,
                has_sandbox_policy=bool(row["sandbox_policy"]),
            )
            await conn.execute(
                "UPDATE marketplace_plugin_execution_runs SET status=$2 WHERE id=$1",
                row["id"],
                action["status"],
            )
            if action["action"] == "enqueue_external_executor":
                await _publish_nats(
                    "sahool.plugin.execution.requested",
                    {
                        "execution_id": row["execution_id"],
                        "tenant_id": str(row["tenant_id"]),
                        "executor": action["receipt"],
                    },
                )

        event_rows = await conn.fetch(
            """
            SELECT id, tenant_id, event_id, event_type, payload
            FROM marketplace_plugin_runtime_events
            WHERE status IN ('pending','failed')
            ORDER BY created_at
            LIMIT $1
            FOR UPDATE SKIP LOCKED
            """,
            batch_size,
        )
        for row in event_rows:
            await _set_tenant(conn, row["tenant_id"])
            try:
                await _publish_nats(
                    f"sahool.{str(row['event_type']).replace('_', '.')}",
                    {"event_id": row["event_id"], "payload": row["payload"]},
                )
                await conn.execute(
                    "UPDATE marketplace_plugin_runtime_events SET status='published' WHERE id=$1",
                    row["id"],
                )
            except Exception:
                await conn.execute(
                    "UPDATE marketplace_plugin_runtime_events SET status='failed' WHERE id=$1",
                    row["id"],
                )
        return len(rows) + len(event_rows)


async def _model_metadata(conn: Any, tenant_id: Any, model_id: str | None) -> dict[str, Any]:
    if not model_id:
        return {}
    row = await conn.fetchrow(
        "SELECT artifact_uri, artifact_hash FROM model_versions_runtime WHERE tenant_id=$1 AND model_id=$2",
        tenant_id,
        model_id,
    )
    return dict(row) if row else {}


async def run_model_registry_once(pool: asyncpg.Pool, *, batch_size: int = 25) -> int:
    serving_enabled = env_bool("MODEL_SERVING_ENABLED", False)
    rollback_enabled = env_bool("MODEL_SERVING_ROLLBACK_ENABLED", False)
    serving_backend_url = os.getenv("MODEL_SERVING_BACKEND_URL")
    async with pool.acquire() as conn, conn.transaction():
        processed = 0
        promotions = await conn.fetch(
            """
            SELECT id, tenant_id, promotion_id, alias, decision, target_model_id, previous_model_id
            FROM model_promotion_history_runtime
            WHERE decision='promote'
            ORDER BY created_at
            LIMIT $1
            FOR UPDATE SKIP LOCKED
            """,
            batch_size,
        )
        for row in promotions:
            await _set_tenant(conn, row["tenant_id"])
            metadata = await _model_metadata(conn, row["tenant_id"], row["target_model_id"])
            action = build_model_promotion_action(
                decision=str(row["decision"]),
                target_model_id=row["target_model_id"],
                artifact_uri=metadata.get("artifact_uri"),
                artifact_hash=metadata.get("artifact_hash"),
                serving_enabled=serving_enabled,
                serving_backend_url=serving_backend_url,
            )
            if action["action"] == "request_serving_promotion":
                await conn.execute(
                    """
                    INSERT INTO model_serving_aliases_runtime (tenant_id, alias, model_id, previous_model_id, promotion_id, status)
                    VALUES ($1,$2,$3,$4,$5,'pending_external_ack')
                    ON CONFLICT (tenant_id, alias) DO UPDATE SET
                        model_id=EXCLUDED.model_id, previous_model_id=EXCLUDED.previous_model_id,
                        promotion_id=EXCLUDED.promotion_id, status='pending_external_ack', updated_at=now()
                    """,
                    row["tenant_id"],
                    row["alias"],
                    row["target_model_id"],
                    row["previous_model_id"],
                    row["promotion_id"],
                )
                await _publish_nats(
                    "sahool.model.promotion.requested",
                    {
                        "promotion_id": row["promotion_id"],
                        "alias": row["alias"],
                        "target_model_id": row["target_model_id"],
                    },
                )
            processed += 1

        rollbacks = await conn.fetch(
            """
            SELECT id, tenant_id, rollback_id, alias, to_model_id
            FROM model_rollback_history_runtime
            WHERE status IN ('planned','pending')
            ORDER BY created_at
            LIMIT $1
            FOR UPDATE SKIP LOCKED
            """,
            batch_size,
        )
        for row in rollbacks:
            await _set_tenant(conn, row["tenant_id"])
            action = build_model_rollback_action(
                rollback_enabled=rollback_enabled,
                serving_backend_url=serving_backend_url,
                to_model_id=row["to_model_id"],
            )
            if action["action"] == "request_serving_rollback":
                await conn.execute(
                    "UPDATE model_rollback_history_runtime SET status='queued' WHERE id=$1",
                    row["id"],
                )
                await _publish_nats(
                    "sahool.model.rollback.requested",
                    {
                        "rollback_id": row["rollback_id"],
                        "alias": row["alias"],
                        "to_model_id": row["to_model_id"],
                    },
                )
            else:
                await conn.execute(
                    "UPDATE model_rollback_history_runtime SET status='blocked' WHERE id=$1",
                    row["id"],
                )
            processed += 1
        return processed


async def run_actuator_once(pool: asyncpg.Pool, *, batch_size: int = 25) -> int:
    physical_enabled = env_bool("PHYSICAL_ACTUATION_ENABLED", False)
    adapter_config = parse_json_env("ACTUATOR_ADAPTER_CONFIG_JSON")
    async with pool.acquire() as conn, conn.transaction():
        rows = await conn.fetch(
            """
            SELECT id, tenant_id, field_id, command_id, protocol, target_id, status
            FROM iot_command_dispatch
            WHERE status IN ('pending','planned','queued','simulated','adapter_required')
            ORDER BY created_at
            LIMIT $1
            FOR UPDATE SKIP LOCKED
            """,
            batch_size,
        )
        for row in rows:
            await _set_tenant(conn, row["tenant_id"])
            action = build_actuator_worker_action(
                physical_enabled=physical_enabled,
                protocol=str(row["protocol"]),
                target_id=str(row["target_id"]),
                adapter_config=adapter_config,
            )
            await conn.execute(
                """
                UPDATE iot_command_dispatch
                SET status=$2, physical_effect=$3, reason=$4, adapter_receipt=$5::jsonb, updated_at=now()
                WHERE id=$1
                """,
                row["id"],
                action["status"],
                bool(action["physical_effect"]),
                action.get("reason"),
                _json(action.get("receipt", {})),
            )
            if action["action"] == "request_adapter_dispatch":
                await _publish_nats(
                    "sahool.actuator.dispatch.requested",
                    {
                        "command_id": row["command_id"],
                        "protocol": row["protocol"],
                        "target_id": row["target_id"],
                    },
                )
        return len(rows)


async def loop_worker(kind: str) -> None:
    pool = await _connect()
    interval = float(os.getenv("WORKER_POLL_SECONDS", "5"))
    runners = {
        "outbox": run_outbox_once,
        "plugin": run_plugin_once,
        "model": run_model_registry_once,
        "actuator": run_actuator_once,
    }
    if kind not in runners:
        raise SystemExit(f"unknown worker kind {kind}; choose one of {', '.join(runners)}")
    try:
        while True:
            processed = await runners[kind](pool)
            print(json.dumps({"worker": kind, "processed": processed}), flush=True)
            await asyncio.sleep(interval)
    finally:
        await pool.close()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["outbox", "plugin", "model", "actuator"])
    args = parser.parse_args(list(argv) if argv is not None else None)
    asyncio.run(loop_worker(args.kind))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
