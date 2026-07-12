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
    async with pool.acquire() as conn:
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
    async with pool.acquire() as conn:
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
    async with pool.acquire() as conn:
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
    async with pool.acquire() as conn:
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


async def run_water_ledger_once(pool: asyncpg.Pool, *, batch_size: int = 50) -> int:
    """WATER-LEDGER-AUTO: يحسب قيد دفتر المياه اليوميّ آليّاً لكلّ حقل بموسم نشط.

    الصدق التشغيليّ:
      • خلف راية ``WATER_LEDGER_AUTO_ENABLED`` (افتراضيّاً off — لا كتابة صامتة).
      • ET0 من محرّك الطقس حصراً والمطر من توقّع اليوم — تعذّرهما ⇒ تخطّي الحقل
        (لا صفر مُختلَق)، ويُعاد في الدورة التالية.
      • الريّ من ``irrigation_runs`` المكتملة لليوم؛ تشغيلات بلا حجم ⇒ علم مُعلَن.
      • القيد اليدويّ سيّد: لا يُلمَس قيد يومٍ لم يكتبه العامل نفسه.
      • upsert idempotent على (field_id, ledger_date) — إعادة التشغيل تعيد الحساب
        بأحدث مدخلات اليوم لا تكرّر.
    """
    if not env_bool("WATER_LEDGER_AUTO_ENABLED", False):
        return 0
    import datetime as _dt

    from api.soil_enrichment import extract_texture
    from api.soil_water import soil_water_params
    from api.water_balance import KC_BY_CROP_STAGE, kc_from_ndvi
    from api.water_ledger_auto import (
        AUTO_CREATED_BY,
        compute_daily_ledger_entry,
        manual_entry_takes_precedence,
    )
    from api.weather_service_client import get_et0_product, get_weather_forecast

    today = _dt.date.today()
    processed = 0
    async with pool.acquire() as conn:
        fields = await conn.fetch(
            """
            SELECT DISTINCT f.field_id, f.tenant_id, f.lat, f.lon, f.crop AS field_crop, s.season_id
            FROM fields f
            JOIN seasons s ON s.field_id = f.field_id AND s.status = 'active'
            WHERE f.lat IS NOT NULL AND f.lon IS NOT NULL
            LIMIT $1
            """,
            batch_size,
        )
        for row in fields:
            field_id = row["field_id"]
            try:
                await _set_tenant(conn, row["tenant_id"])
                existing = await conn.fetchrow(
                    "SELECT created_by FROM water_ledger WHERE field_id=$1 AND ledger_date=$2",
                    field_id,
                    today,
                )
                if existing and manual_entry_takes_precedence(existing["created_by"]):
                    continue  # الإنسان سيّد الدفتر — لا كتابة فوق قيد يدويّ.
                prev = await conn.fetchrow(
                    "SELECT depletion_mm FROM water_ledger"
                    " WHERE field_id=$1 AND ledger_date < $2"
                    " ORDER BY ledger_date DESC LIMIT 1",
                    field_id,
                    today,
                )
                # نسيج مخبريّ معتمَد إن وُجد ⇒ TAW أدقّ؛ وإلّا fallback مُعلَن المصدر.
                soil_row = await conn.fetchrow(
                    "SELECT result FROM soil_lab_tests"
                    " WHERE field_id=$1 AND status IN ('approved','published')"
                    " ORDER BY sampled_on DESC NULLS LAST LIMIT 1",
                    field_id,
                )
                texture = extract_texture(soil_row["result"]) if soil_row else None
                sw = soil_water_params(texture=texture, root_depth_m=None)
                irr = await conn.fetchrow(
                    "SELECT COALESCE(SUM(volume_mm), 0) AS mm,"
                    " COUNT(*) FILTER (WHERE volume_mm IS NULL) AS untracked"
                    " FROM irrigation_runs"
                    " WHERE field_id=$1 AND status='completed'"
                    " AND started_at::date = $2",
                    field_id,
                    today,
                )

                # مدخلات اليوم من خدمة الطقس؛ ET0 يُحسب في المحرّك حصراً (agro/et0) —
                # لا نستهلك et0 المزوّد الخام. فشل أيّهما ⇒ تخطٍّ صادق لهذا اليوم.
                forecast = await get_weather_forecast(float(row["lat"]), float(row["lon"]), days=1)
                day0 = (forecast.get("days") or [{}])[0]
                t_max, t_min = day0.get("temp_max_c"), day0.get("temp_min_c")
                rain_mm = float(day0.get("precipitation_mm") or 0.0)
                if t_max is None or t_min is None:
                    continue
                et0 = await get_et0_product(
                    t_max_c=float(t_max),
                    t_min_c=float(t_min),
                    solar_rad_mj_m2=day0.get("solar_radiation_mj_m2"),
                    wind_2m_ms=day0.get("wind_max_ms"),
                    lat_deg=float(row["lat"]),
                    day_of_year=today.timetuple().tm_yday,
                    tenant_id=str(row["tenant_id"]),
                )
                et0_mm = et0.get("et0_mm")
                if et0_mm is None:
                    continue

                crop = (row["field_crop"] or "").strip().lower() or None
                kc_map = KC_BY_CROP_STAGE.get(crop or "", KC_BY_CROP_STAGE.get("wheat", {}))
                kc, _ = kc_from_ndvi(None, kc_map, "mid")
                entry = compute_daily_ledger_entry(
                    prev_depletion_mm=(
                        float(prev["depletion_mm"])
                        if prev and prev["depletion_mm"] is not None
                        else None
                    ),
                    taw_mm=float(sw["taw_mm"]),
                    raw_mm=float(sw["taw_mm"]) * float(sw["raw_fraction"]),
                    et0_mm=float(et0_mm),
                    kc=kc,
                    rain_mm=rain_mm,
                    irrigation_mm=float(irr["mm"] or 0.0),
                    irrigation_volume_untracked=bool(irr["untracked"]),
                )
                await conn.execute(
                    """
                    INSERT INTO water_ledger
                      (tenant_id, field_id, ledger_date, et0_mm, kc, etc_mm, rain_mm,
                       irrigation_mm, depletion_mm, deficit_mm, stage, decision,
                       confidence, created_by, created_at, updated_at)
                    VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                            $13, $14, now(), now())
                    ON CONFLICT (field_id, ledger_date) DO UPDATE SET
                      et0_mm = EXCLUDED.et0_mm, kc = EXCLUDED.kc, etc_mm = EXCLUDED.etc_mm,
                      rain_mm = EXCLUDED.rain_mm, irrigation_mm = EXCLUDED.irrigation_mm,
                      depletion_mm = EXCLUDED.depletion_mm, deficit_mm = EXCLUDED.deficit_mm,
                      stage = EXCLUDED.stage, decision = EXCLUDED.decision,
                      confidence = EXCLUDED.confidence, updated_at = now()
                    """,
                    str(row["tenant_id"]),
                    field_id,
                    today,
                    float(et0_mm),
                    kc,
                    entry["etc_mm"],
                    rain_mm,
                    float(irr["mm"] or 0.0),
                    entry["depletion_mm"],
                    entry["deficit_mm"],
                    "mid",
                    entry["decision"],
                    entry["confidence"],
                    AUTO_CREATED_BY,
                )
                processed += 1
                # Governed bridge: candidate creation is deterministic and default-off.
                from api.water_decision_bridge import process_water_deficit

                bridge_result = await process_water_deficit(
                    tenant_id=str(row["tenant_id"]),
                    field_id=field_id,
                    season_id=str(row["season_id"]) if row["season_id"] else None,
                    ledger_date=today,
                    entry={
                        **entry,
                        "taw_mm": float(sw["taw_mm"]),
                        "raw_mm": float(sw["taw_mm"]) * float(sw["raw_fraction"]),
                    },
                )
                if bridge_result.get("status") not in {"disabled", "below_threshold"}:
                    await conn.execute(
                        """INSERT INTO events
                             (event_type, entity_type, entity_id, tenant_id, actor_id, payload,
                              dedup_key, source, occurred_at)
                           VALUES ($1, 'field', $2::text, $3::uuid, $4, $5::jsonb, $6, 'scheduler', now())
                           ON CONFLICT (dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING""",
                        "decision.water_deficit",
                        field_id,
                        str(row["tenant_id"]),
                        "water-ledger-governed-bridge",
                        json.dumps(
                            {
                                **bridge_result,
                                "field_id": field_id,
                                "season_id": str(row["season_id"]) if row["season_id"] else None,
                                "ledger_date": today.isoformat(),
                                "deficit_mm": entry["deficit_mm"],
                            }
                        ),
                        f"water-deficit:{row['tenant_id']}:{field_id}:{today}",
                    )

            except Exception as exc:  # noqa: BLE001 — تخطٍّ لكلّ حقل مُعلَّل، لا انهيار الدفعة
                print(
                    json.dumps(
                        {"worker": "water_ledger", "field_id": field_id, "skipped": str(exc)[:200]},
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    return processed


async def loop_worker(kind: str) -> None:
    pool = await _connect()
    interval = float(os.getenv("WORKER_POLL_SECONDS", "5"))
    runners = {
        "outbox": run_outbox_once,
        "plugin": run_plugin_once,
        "model": run_model_registry_once,
        "actuator": run_actuator_once,
        "water_ledger": run_water_ledger_once,
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
    parser.add_argument("kind", choices=["outbox", "plugin", "model", "actuator", "water_ledger"])
    args = parser.parse_args(list(argv) if argv is not None else None)
    asyncio.run(loop_worker(args.kind))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
