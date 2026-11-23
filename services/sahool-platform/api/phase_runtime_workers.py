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
    RUNTIME_EVENT_ENVELOPE_COLUMNS,
    build_actuator_worker_action,
    build_model_promotion_action,
    build_model_rollback_action,
    build_outbox_action,
    build_plugin_worker_action,
    env_bool,
    parse_json_env,
    runtime_event_envelope,
    runtime_event_subject,
)
from shared.startup_retry import retry_startup_connect

Json = dict[str, Any]


def _json(value: Any) -> str:
    return json.dumps(value or {}, default=str, ensure_ascii=False)


async def _connect() -> asyncpg.Pool:
    database_url = os.getenv("JOBS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("JOBS_DATABASE_URL is required for Phase runtime workers")
    # RESTART-POLICY-BYPASSES-DEPENDS-ON-HEALTH-01: a restart-policy restart does not
    # wait for Postgres; transient refusals are retried, configuration errors are not.
    return await retry_startup_connect(
        asyncpg.create_pool,
        dsn=database_url,
        min_size=1,
        max_size=int(os.getenv("WORKER_DB_POOL_MAX", "4")),
        startup_what="phase runtime worker database",
    )


async def _set_tenant(conn: Any, tenant_id: Any) -> None:
    if tenant_id:
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))
        await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))


# ── WORKER-CLAIM-NOT-PINNED-BY-A-TRANSACTION-01 ─────────────────────────────
#
# `FOR UPDATE SKIP LOCKED` في اتّصالٍ بوضع autocommit **لا يُثبِّت مطالبة**: القفلُ
# يُحرَّر فور انتهاء عبارة `SELECT`، فيلتقط عاملٌ ثانٍ الصفوفَ نفسَها. والمقيس أنّ
# هذا الملفّ يحمل ستّةَ مواضع `SKIP LOCKED` و**صفرَ** `conn.transaction()`.
#
# وأخطرُها `run_actuator_once`: يطالِب ثمّ ينشر `sahool.actuator.dispatch.requested`
# — فالعطلُ ليس مجرّداً، بل **طلبُ إرسالٍ فيزيائيٍّ مرّتين للأمر نفسه**.
#
# والعلاجُ ليس إطالةَ المعاملة حتّى تشمل النشر: ذلك يُعيد نمطَ `event_bus.py` الذي
# يحبس الأقفالَ أثناء I/O شبكيّ. بل فصلٌ ثلاثيّ — TX-1 مطالبةٌ تُثبَّت بـcommit ·
# الشبكةُ خارج أيّ معاملة · TX-2 إنهاءٌ بـCAS على `claim_token`.
#
# **ولمَ رمزٌ ولا تكفي الحالة:** عند انتهاء الإجارة يُعيد عاملٌ ثانٍ المطالبة. فلو
# كان شرطُ الإنهاء `status='claimed'` وحدَه لأنهى الأوّلُ **مطالبةَ الثاني** ظانّاً
# أنّها مطالبتُه. الرمزُ يجعل الشرطَ هويّةً لا حالة.

_LEASE_SECONDS = int(os.getenv("WORKER_CLAIM_LEASE_SECONDS", "300"))


def _worker_identity() -> str:
    """هويّةٌ تُميّز العاملَ في السجلّ — للتشخيص لا للصحّة."""
    return f"{os.getenv('HOSTNAME', 'worker')}:{os.getpid()}"


async def claim_batch(
    conn: Any,
    *,
    table: str,
    columns: str,
    where: str,
    order_by: str = "created_at",
    batch_size: int,
    params: Iterable[Any] = (),
) -> list[Any]:
    """TX-1: يُطالِب دفعةً ويُثبِّتها بـcommit، ثمّ يُعيدها بـ``claim_token``.

    المطالبةُ والالتقاطُ في عبارةٍ واحدة داخل معاملةٍ صريحة: الصفوفُ المُختارة
    تُقفَل، تُوسَم، ثمّ يُغلَق كلُّ ذلك بـcommit **قبل أيّ عملٍ شبكيّ**. فما إن
    ينتهي هذا حتّى تكون الصفوفُ خارج نطاق `where` — لأنّ `claim_token` صار غيرَ
    فارغ — فلا يلتقطها عاملٌ ثانٍ.
    """
    extra = list(params)
    lease_arg = len(extra) + 1
    by_arg = len(extra) + 2
    limit_arg = len(extra) + 3
    rows = await conn.fetch(
        f"""
        WITH claimed AS (
            SELECT id FROM {table}
            WHERE ({where}) AND claim_token IS NULL
            ORDER BY {order_by}
            LIMIT ${limit_arg}
            FOR UPDATE SKIP LOCKED
        )
        UPDATE {table} AS t
        SET claim_token = gen_random_uuid(),
            claimed_by  = ${by_arg},
            lease_until = now() + make_interval(secs => ${lease_arg})
        FROM claimed
        WHERE t.id = claimed.id
        RETURNING {columns}, t.claim_token
        """,  # noqa: S608 - أسماءُ الجداول والأعمدة ثوابتُ نداءٍ داخليّة لا مُدخَلُ مستخدِم
        *extra,
        float(_LEASE_SECONDS),
        _worker_identity(),
        batch_size,
    )
    return list(rows)


async def finalize_claim(
    conn: Any, *, table: str, row_id: Any, claim_token: Any, assignments: str, params: Iterable[Any]
) -> bool:
    """TX-2: إنهاءٌ بـCAS على ``claim_token`` — يُرجِع هل كان الإنهاءُ لنا.

    ``False`` تعني أنّ إجارتَنا انتهت وأعاد عاملٌ آخرُ المطالبة، فلا نكتب فوق
    عمله. وهي حالةٌ متوقَّعة لا خطأ: العملُ سيُنجَز مرّةً واحدة — بيد الآخر.
    """
    extra = list(params)
    id_arg = len(extra) + 1
    token_arg = len(extra) + 2
    result = await conn.execute(
        f"""
        UPDATE {table}
        SET {assignments}, claim_token = NULL, claimed_by = NULL, lease_until = NULL
        WHERE id = ${id_arg} AND claim_token = ${token_arg}
        """,  # noqa: S608 - كما أعلاه
        *extra,
        row_id,
        claim_token,
    )
    return not str(result).endswith(" 0")


async def reclaim_expired(conn: Any, *, table: str) -> int:
    """يُعيد الصفوفَ التي انتهت إجارتُها إلى بِركة الالتقاط.

    بلا هذا يبقى صفٌّ مُطالَبٌ من عاملٍ انهار **مُطالَباً إلى الأبد** — فالمطالبةُ
    تصير قبراً لا إجارة. ولا يُلمَس ``status``: قد يكون العاملُ أتمّ عملَه ولم
    يُنهِ، فإعادةُ الحالة تُلغي ما وقع.
    """
    result = await conn.execute(
        f"""
        UPDATE {table}
        SET claim_token = NULL, claimed_by = NULL, lease_until = NULL
        WHERE claim_token IS NOT NULL AND lease_until < now()
        """  # noqa: S608 - كما أعلاه
    )
    return int(str(result).rsplit(" ", 1)[-1] or 0)


async def _publish_nats(subject: str, payload: Json, *, msg_id: str | None = None) -> None:
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
        # Nats-Msg-Id = event_id, as the platform OutboxWorker does (event_bus.py). The sahool
        # stream drops a republish only inside its duplicate window (server default 120 s);
        # a republish after the 300 s lease expiry falls outside it. Per-user delivery is
        # still deduplicated by the notification receipt keyed on event_id.
        headers = {"Nats-Msg-Id": msg_id} if msg_id else None
        await nc.publish(subject, json.dumps(payload, default=str).encode("utf-8"), headers=headers)
        await nc.flush(timeout=5)
    finally:
        await nc.close()


async def run_outbox_once(pool: asyncpg.Pool, *, batch_size: int = 25) -> int:
    max_attempts = int(os.getenv("OUTBOX_MAX_ATTEMPTS", "5"))
    nats_url = os.getenv("NATS_URL") or os.getenv("SAHOOL_NATS_URL")
    async with pool.acquire() as conn:
        # TX-1: مطالبةٌ تُثبَّت بـcommit قبل أيّ نشرٍ شبكيّ.
        async with conn.transaction():
            await reclaim_expired(conn, table="runtime_event_outbox")
            rows = await claim_batch(
                conn,
                table="runtime_event_outbox",
                columns=RUNTIME_EVENT_ENVELOPE_COLUMNS["outbox"],
                where="status IN ('pending','failed') AND attempts < $1",
                batch_size=batch_size,
                params=(max_attempts,),
            )

        processed = 0
        for row in rows:
            action = build_outbox_action(
                nats_url=nats_url,
                event_type=row["event_type"],
                attempts=int(row["attempts"] or 0),
                max_attempts=max_attempts,
            )
            try:
                # الشبكةُ خارج أيّ معاملة — لا أقفالَ محبوسةٌ أثناء I/O.
                if action["action"] != "publish_nats":
                    raise RuntimeError(action.get("reason") or "outbox_not_publishable")
                subject = action["receipt"]["subject"]
                await _publish_nats(
                    subject, runtime_event_envelope(row), msg_id=str(row["event_id"])
                )
                assignments = "status='published', attempts=attempts+1, published_at=now()"
                params: tuple[Any, ...] = ()
            except Exception:
                next_status = (
                    "dead_letter" if int(row["attempts"] or 0) + 1 >= max_attempts else "failed"
                )
                assignments = "status=$1, attempts=attempts+1"
                params = (next_status,)
            # TX-2: إنهاءٌ بـCAS — إن انتهت إجارتُنا فالصفُّ لغيرنا ولا نكتب فوقه.
            async with conn.transaction():
                await _set_tenant(conn, row["tenant_id"])
                await finalize_claim(
                    conn,
                    table="runtime_event_outbox",
                    row_id=row["id"],
                    claim_token=row["claim_token"],
                    assignments=assignments,
                    params=params,
                )
            processed += 1
        return processed


async def run_plugin_once(pool: asyncpg.Pool, *, batch_size: int = 25) -> int:
    plugin_enabled = env_bool("PLUGIN_EXECUTION_ENABLED", False)
    executor_url = os.getenv("PLUGIN_EXECUTOR_URL")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await reclaim_expired(conn, table="marketplace_plugin_execution_runs")
            rows = await claim_batch(
                conn,
                table="marketplace_plugin_execution_runs",
                columns=(
                    "t.id, t.tenant_id, t.execution_id, t.decision, t.status, t.sandbox_policy"
                ),
                where="status IN ('planned','pending')",
                batch_size=batch_size,
            )

        for row in rows:
            action = build_plugin_worker_action(
                decision=str(row["decision"]),
                plugin_enabled=plugin_enabled,
                executor_url=executor_url,
                has_sandbox_policy=bool(row["sandbox_policy"]),
            )
            # كما في المُشغِّل: الإنهاءُ يسبق النشر، وCAS بوّابةٌ تمنع إرسالاً ثانياً.
            async with conn.transaction():
                await _set_tenant(conn, row["tenant_id"])
                owned = await finalize_claim(
                    conn,
                    table="marketplace_plugin_execution_runs",
                    row_id=row["id"],
                    claim_token=row["claim_token"],
                    assignments="status=$1",
                    params=(action["status"],),
                )
            if owned and action["action"] == "enqueue_external_executor":
                await _publish_nats(
                    "sahool.plugin.execution.requested",
                    {
                        "execution_id": row["execution_id"],
                        "tenant_id": str(row["tenant_id"]),
                        "executor": action["receipt"],
                    },
                )

        async with conn.transaction():
            await reclaim_expired(conn, table="marketplace_plugin_runtime_events")
            event_rows = await claim_batch(
                conn,
                table="marketplace_plugin_runtime_events",
                columns=RUNTIME_EVENT_ENVELOPE_COLUMNS["plugin"],
                where="status IN ('pending','failed')",
                batch_size=batch_size,
            )

        for row in event_rows:
            try:
                await _publish_nats(
                    runtime_event_subject(str(row["event_type"])),
                    runtime_event_envelope(row),
                    msg_id=str(row["event_id"]),
                )
                assignments = "status='published'"
            except Exception:
                assignments = "status='failed'"
            async with conn.transaction():
                await _set_tenant(conn, row["tenant_id"])
                await finalize_claim(
                    conn,
                    table="marketplace_plugin_runtime_events",
                    row_id=row["id"],
                    claim_token=row["claim_token"],
                    assignments=assignments,
                    params=(),
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
        # F-D04 (A-QUEUE-WITH-NO-TERMINAL-STATE-REPUBLISHES-FOREVER-01): the claim takes
        # only status='pending' rows (v288) and the release writes one terminal status —
        # requested | blocked | skipped — so a processed promotion is never claimed again,
        # neither re-blocked every cycle while serving is disabled nor requested again while
        # it is enabled. 'requested' ends the queue, not the promotion: the alias stays
        # pending_external_ack until an acknowledgement from the serving backend is recorded.
        async with conn.transaction():
            await reclaim_expired(conn, table="model_promotion_history_runtime")
            promotions = await claim_batch(
                conn,
                table="model_promotion_history_runtime",
                columns=(
                    "t.id, t.tenant_id, t.promotion_id, t.alias, t.decision, "
                    "t.target_model_id, t.previous_model_id"
                ),
                where="status='pending'",
                batch_size=batch_size,
            )

        for row in promotions:
            async with conn.transaction():
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
                # The request is published while the row is still claimed and pending, and only
                # then marked requested. A broker that is down must not leave a row that is
                # terminal but never sent (Devin on #1587): on a failed publish the claim is
                # released with the row still pending, so a later cycle publishes it. Delivery
                # is at least once; Nats-Msg-Id is stable per promotion, so the stream drops a
                # republish inside its duplicate window and a consumer keys on promotion_id.
                async with conn.transaction():
                    await _set_tenant(conn, row["tenant_id"])
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
                try:
                    await _publish_nats(
                        "sahool.model.promotion.requested",
                        {
                            "promotion_id": row["promotion_id"],
                            "alias": row["alias"],
                            "target_model_id": row["target_model_id"],
                        },
                        msg_id=f"model-promotion-requested:{row['promotion_id']}",
                    )
                except Exception as exc:  # noqa: BLE001 - any failure means "not sent"
                    released = ("pending", f"publish_failed:{type(exc).__name__}")
                else:
                    released = ("requested", None)
                async with conn.transaction():
                    await _set_tenant(conn, row["tenant_id"])
                    await finalize_claim(
                        conn,
                        table="model_promotion_history_runtime",
                        row_id=row["id"],
                        claim_token=row["claim_token"],
                        assignments="status=$1, status_reason=$2",
                        params=released,
                    )
            else:
                async with conn.transaction():
                    await finalize_claim(
                        conn,
                        table="model_promotion_history_runtime",
                        row_id=row["id"],
                        claim_token=row["claim_token"],
                        assignments="status=$1, status_reason=$2",
                        params=(
                            "skipped" if action["action"] == "skip" else "blocked",
                            action.get("reason"),
                        ),
                    )
            processed += 1

        async with conn.transaction():
            await reclaim_expired(conn, table="model_rollback_history_runtime")
            rollbacks = await claim_batch(
                conn,
                table="model_rollback_history_runtime",
                columns="t.id, t.tenant_id, t.rollback_id, t.alias, t.to_model_id",
                where="status IN ('planned','pending')",
                batch_size=batch_size,
            )

        for row in rollbacks:
            action = build_model_rollback_action(
                rollback_enabled=rollback_enabled,
                serving_backend_url=serving_backend_url,
                to_model_id=row["to_model_id"],
            )
            requested = action["action"] == "request_serving_rollback"
            async with conn.transaction():
                await _set_tenant(conn, row["tenant_id"])
                owned = await finalize_claim(
                    conn,
                    table="model_rollback_history_runtime",
                    row_id=row["id"],
                    claim_token=row["claim_token"],
                    assignments="status=$1",
                    params=("queued" if requested else "blocked",),
                )
            if owned and requested:
                await _publish_nats(
                    "sahool.model.rollback.requested",
                    {
                        "rollback_id": row["rollback_id"],
                        "alias": row["alias"],
                        "to_model_id": row["to_model_id"],
                    },
                )
            processed += 1
        return processed


async def run_actuator_once(pool: asyncpg.Pool, *, batch_size: int = 25) -> int:
    physical_enabled = env_bool("PHYSICAL_ACTUATION_ENABLED", False)
    adapter_config = parse_json_env("ACTUATOR_ADAPTER_CONFIG_JSON")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await reclaim_expired(conn, table="iot_command_dispatch")
            rows = await claim_batch(
                conn,
                table="iot_command_dispatch",
                columns=(
                    "t.id, t.tenant_id, t.field_id, t.command_id, t.protocol, t.target_id, t.status"
                ),
                where="status IN ('pending','planned','queued','simulated','adapter_required')",
                batch_size=batch_size,
            )

        for row in rows:
            action = build_actuator_worker_action(
                physical_enabled=physical_enabled,
                protocol=str(row["protocol"]),
                target_id=str(row["target_id"]),
                adapter_config=adapter_config,
            )
            # **الإنهاءُ قبل النشر عمداً** — والترتيبُ هنا قرارُ سلامةٍ لا أسلوب:
            # لو نُشِر أوّلاً ثمّ سقط الإنهاء، لعادت الإجارةُ المنتهيةُ بالصفّ إلى
            # البِركة فيُنشَر **طلبُ إرسالٍ فيزيائيٍّ ثانٍ للأمر نفسه**. وبهذا
            # الترتيب يكون أسوأُ ما يقع فقدَ طلبٍ — وفقدُ طلبٍ أهونُ من تكراره
            # حين يكون الطلبُ حركةَ صمّامٍ أو مضخّة (fail-closed).
            async with conn.transaction():
                await _set_tenant(conn, row["tenant_id"])
                owned = await finalize_claim(
                    conn,
                    table="iot_command_dispatch",
                    row_id=row["id"],
                    claim_token=row["claim_token"],
                    assignments=(
                        "status=$1, physical_effect=$2, reason=$3, "
                        "adapter_receipt=$4::jsonb, updated_at=now()"
                    ),
                    params=(
                        action["status"],
                        bool(action["physical_effect"]),
                        action.get("reason"),
                        _json(action.get("receipt", {})),
                    ),
                )
            # CAS بوّابةٌ تسبق النشر: إن لم يكن الصفُّ لنا فالعملُ لغيرنا، ولا
            # نُطلِق أثراً فيزيائيّاً باسمِ مطالبةٍ انتهت.
            if owned and action["action"] == "request_adapter_dispatch":
                await _publish_nats(
                    "sahool.actuator.dispatch.requested",
                    {
                        "command_id": row["command_id"],
                        "protocol": row["protocol"],
                        "target_id": row["target_id"],
                    },
                )
        return len(rows)


class _RainChainChanged(Exception):
    """قيدٌ في سلسلة إعادة تسجيل المطر تغيّر بين القراءة والكتابة ⇒ تُرجَع السلسلة كلُّها."""


def _water_deficit_dedup_key(tenant_id: object, field_id: str, day: object, result: dict) -> str:
    """W2-02: one decision.water_deficit event per field and day — but a blocked outcome
    (``blocked:lineage_missing`` …) keeps its own key, so a later hourly run whose candidate
    is recorded is not dropped by ON CONFLICT behind the morning's block."""
    key = f"water-deficit:{tenant_id}:{field_id}:{day}"
    status = str(result.get("status") or "")
    return f"{key}:{status}" if status.startswith("blocked") else key


async def run_water_ledger_once(pool: asyncpg.Pool, *, batch_size: int = 50) -> int:
    """WATER-LEDGER-AUTO: يحسب قيد دفتر المياه اليوميّ آليّاً لكلّ حقل بموسم نشط.

    الصدق التشغيليّ:
      • خلف راية ``WATER_LEDGER_AUTO_ENABLED`` (افتراضيّاً off — لا كتابة صامتة).
      • ET0 من محرّك الطقس حصراً والمطر من توقّع اليوم — تعذّرهما ⇒ تخطّي الحقل
        (لا صفر مُختلَق)، ويُعاد في الدورة التالية.
      • weather-7: ET0 بارتفاع الحقل (``fields.elevation_m``) — غيابه ⇒ تخطّي اليوم لا مستوى
        البحر؛ والمرجعُ ``validated`` وحده؛ ويُكتب نَسَبُ ET0 (الطريقة · الجودة · اللقطة)
        ومصدرُ المطر. مطرُ الأمس المتوقَّع يُعاد تسجيلُه من الأرشيف قبل أن يُبنى عليه اليوم.
      • الريّ من ``irrigation_runs`` المكتملة لليوم؛ تشغيلات بلا حجم ⇒ علم مُعلَن.
      • القيد اليدويّ سيّد: لا يُلمَس قيد يومٍ لم يكتبه العامل نفسه.
      • upsert idempotent على (field_id, ledger_date) — إعادة التشغيل تعيد الحساب
        بأحدث مدخلات اليوم لا تكرّر.
    """
    if not env_bool("WATER_LEDGER_AUTO_ENABLED", False):
        return 0
    import datetime as _dt

    # DAILY-WATER-LEDGER-UTC-DATE-VS-ADEN-FORECAST-DAY-01: «اليوم» يوم الحقل المحلّيّ لا يوم UTC.
    # كان ``date.today()`` (UTC على الخادم) يُقرَن بيوم توقّعاتٍ محلّيّ، فبين منتصف الليل UTC
    # ومنتصف الليل في عدن يُحسَب ETc والمطر في يومٍ خاطئ أو مرّتين. والريُّ يُجمَع بالتقويم نفسه.
    from zoneinfo import ZoneInfo

    from api.soil_enrichment import extract_texture, latest_lab_texture_row
    from api.water_ledger_auto import (
        AUTO_CREATED_BY,
        compute_daily_ledger_entry,
        forecast_day_for_ledger_date,
        gap_irrigation_by_day,
        manual_entry_takes_precedence,
        reported_irrigation,
    )
    from api.water_ledger_inputs import (
        RAIN_RECONCILE_WINDOW_DAYS,
        RAIN_SOURCE_FORECAST,
        daily_kc,
        et0_product_is_reference,
        et0_weather_inputs,
        field_elevation_m,
        ledger_root_zone,
        observed_rain_by_date,
        rain_reconcile_start,
        rebuild_rain_chain,
    )
    from api.weather_service_client import (
        get_et0_product,
        get_weather_forecast,
        get_weather_historical,
    )

    ledger_tz = os.getenv("WATER_LEDGER_TIMEZONE", "Asia/Aden")
    today = _dt.datetime.now(ZoneInfo(ledger_tz)).date()
    processed = 0
    async with pool.acquire() as conn:
        # DAILY-WATER-LEDGER-FIRST-50-FIELDS-ONLY-01: كان ``LIMIT 50`` بلا ترتيب يُعالج أوّل خمسين
        # حقلاً كيفما اتّفق، وتبقى البقيّةُ بلا دفترٍ بلا مؤشّر. صار تقسيماً بالمفتاح على ``field_id``
        # حتّى تُستنفَد الحقول، وموسمٌ نشطٌ واحدٌ لكلّ حقل (الأحدث زراعةً) — موسمان نشطان كانا
        # يكتبان القيدَ نفسه (field_id, ledger_date) مرّتين.
        last_field_id = ""
        while True:
            fields = await conn.fetch(
                """
                SELECT DISTINCT ON (f.field_id)
                       f.field_id, f.tenant_id, f.lat, f.lon, f.elevation_m,
                       f.crop AS field_crop, s.season_id, s.sowing_date, s.cultivar
                FROM fields f
                JOIN seasons s ON s.field_id = f.field_id AND s.status = 'active'
                WHERE f.lat IS NOT NULL AND f.lon IS NOT NULL AND f.field_id > $2
                ORDER BY f.field_id, s.sowing_date DESC NULLS LAST, s.season_id
                LIMIT $1
                """,
                batch_size,
                last_field_id,
            )
            if not fields:
                break
            last_field_id = fields[-1]["field_id"]
            for row in fields:
                field_id = row["field_id"]
                # weather-7: بلا ارتفاعٍ يحسب المحرّك PM عند مستوى البحر — تخطٍّ معلن لا قيدٌ خاطئ.
                elevation_m = field_elevation_m(row["elevation_m"])
                if elevation_m is None:
                    print(
                        json.dumps(
                            {
                                "worker": "water_ledger",
                                "field_id": field_id,
                                "skipped": "field_elevation_missing",
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    continue
                try:
                    # WORKER-TENANT-GUC-SET-OUTSIDE-ANY-TRANSACTION-01: set_config(…, true) يعيش داخل
                    # معاملةٍ فقط؛ بلاها يزول قبل القراءة التالية (صفر صفوف تحت FORCE RLS). ثلاث معاملات
                    # قصيرة لكلّ حقل، كلٌّ يضبط المستأجر: القراءات · القيد · الحدث. الشبكة (الطقس وET0
                    # وجسر القرار) **خارج** أيّ معاملة: لا قفلَ صفٍّ ولا معاملةَ مفتوحة أثناء I/O، والقيد
                    # يُلتزَم قبل الجسر كما كان قبل الإصلاح (فشلُ الجسر لا يُرجِع قيدَ الدفتر).
                    async with conn.transaction():
                        await _set_tenant(conn, row["tenant_id"])
                        existing = await conn.fetchrow(
                            "SELECT created_by, irrigation_mm, irrigation_reported_by"
                            " FROM water_ledger WHERE field_id=$1 AND ledger_date=$2",
                            field_id,
                            today,
                        )
                        if existing and manual_entry_takes_precedence(existing["created_by"]):
                            continue  # الإنسان سيّد الدفتر — لا كتابة فوق قيد يدويّ.
                        # W0-13: a person reported today's applied water (v280) ⇒ that figure is
                        # the day's irrigation; the balance is recomputed around it, not over it.
                        reported_irrigation_mm = reported_irrigation(existing)
                        # W1-13: a report or the farm-ledger projection can open a row the worker
                        # never computes (an earlier day, or a today the worker skipped). It holds
                        # the day's water and no balance; read as the prior day it would restart
                        # the chain from field capacity. The prior balance is the latest row that
                        # has one; an uncomputed worker row in between is a skipped day.
                        prev = await conn.fetchrow(
                            "SELECT depletion_mm, ledger_date FROM water_ledger"
                            " WHERE field_id=$1 AND ledger_date < $2"
                            " AND NOT (created_by IS NOT DISTINCT FROM $3 AND decision IS NULL)"
                            " ORDER BY ledger_date DESC LIMIT 1",
                            field_id,
                            today,
                            AUTO_CREATED_BY,
                        )
                        # weather-7: المطرُ المتوقَّع يُعاد تسجيله من الأرشيف حين يمتلئ. الأرشيف
                        # (ERA5) يتأخّر أيّاماً، فتُقرأ نافذةٌ من القيود (ويومٌ قبلها مرساةً) لا
                        # قيدُ الأمس وحده، ويُعاد فحصُها كلَّ دورة حتّى يُرصَد مطرُها.
                        window_rows = await conn.fetch(
                            "SELECT ledger_date, depletion_mm, created_by, rain_source, rain_mm,"
                            " etc_mm, irrigation_mm, decision, taw_mm, raw_mm FROM water_ledger"
                            " WHERE field_id=$1 AND ledger_date >= $2 AND ledger_date < $3"
                            " ORDER BY ledger_date",
                            field_id,
                            today - _dt.timedelta(days=RAIN_RECONCILE_WINDOW_DAYS + 1),
                            today,
                        )
                        reconcile_from = rain_reconcile_start(window_rows, today, AUTO_CREATED_BY)
                        # DAILY-WATER-LEDGER-SKIPPED-DAYS-DROP-CONSUMPTION-01: أيّامٌ بلا قيدٍ بين
                        # آخر قيدٍ واليوم يُقدَّر استهلاكُها ويُطرَح ريُّها المسجَّل (لا تُسقَط).
                        # يوماً بيوم (لا مجموعاً): القصُّ بعد كلّ يوم، وريٌّ مجهولٌ في يومٍ متخطّى
                        # يُعلَن ولا يُعَدّ صفراً (مراجعة Copilot على #1342).
                        missing_days = 0
                        gap_irrigation_mm: list[float] = []
                        gap_unobserved = gap_untracked = False
                        if prev and prev["ledger_date"] is not None:
                            missing_days = max((today - prev["ledger_date"]).days - 1, 0)
                        if missing_days:
                            gap_rows = await conn.fetch(
                                "SELECT (started_at AT TIME ZONE $4)::date AS d,"
                                " COALESCE(SUM(volume_mm), 0) AS mm,"
                                " COUNT(*) FILTER (WHERE volume_mm IS NULL) AS untracked,"
                                " COUNT(*) AS runs"
                                " FROM irrigation_runs"
                                " WHERE field_id=$1 AND status='completed'"
                                " AND (started_at AT TIME ZONE $4)::date > $2"
                                " AND (started_at AT TIME ZONE $4)::date < $3"
                                " GROUP BY 1",
                                field_id,
                                prev["ledger_date"],
                                today,
                                ledger_tz,
                            )
                            # The water reported on a skipped day's uncomputed row is that
                            # day's measured total, as it would have been on its own day.
                            gap_reported = await conn.fetch(
                                "SELECT ledger_date, irrigation_mm FROM water_ledger"
                                " WHERE field_id=$1 AND ledger_date > $2 AND ledger_date < $3"
                                " AND created_by = $4 AND decision IS NULL"
                                " AND irrigation_reported_by IS NOT NULL"
                                " AND irrigation_mm IS NOT NULL",
                                field_id,
                                prev["ledger_date"],
                                today,
                                AUTO_CREATED_BY,
                            )
                            gap_irrigation_mm, gap_unobserved, gap_untracked = (
                                gap_irrigation_by_day(
                                    gap_rows,
                                    prev["ledger_date"],
                                    today,
                                    {
                                        r["ledger_date"]: float(r["irrigation_mm"])
                                        for r in gap_reported
                                    },
                                )
                            )
                        # نسيج مخبريّ معتمَد إن وُجد ⇒ TAW أدقّ؛ وإلّا fallback مُعلَن المصدر.
                        # W1-03: المخزن القانونيّ (soil_lab_results) أوّلاً، والقديم موسوماً.
                        soil_row = await latest_lab_texture_row(conn, field_id)
                        texture = extract_texture(soil_row["result"]) if soil_row else None
                        # Kc الطوريّ من بطاقة المحصول وتاريخ الزراعة — لا Kc منتصف الموسم كلَّ يوم ولا
                        # احتياطَ القمح. مجهولٌ ⇒ تخطٍّ مُعلَّل (لا قيدَ بمعاملٍ لا يمثّل الحقل).
                        crop_kc = daily_kc(row["field_crop"], row["sowing_date"], today)
                        if crop_kc is None:
                            print(
                                json.dumps(
                                    {
                                        "worker": "water_ledger",
                                        "field_id": field_id,
                                        "skipped": "crop_kc_unavailable",
                                    },
                                    ensure_ascii=False,
                                ),
                                flush=True,
                            )
                            continue
                        irr = await conn.fetchrow(
                            "SELECT COALESCE(SUM(volume_mm), 0) AS mm,"
                            " COUNT(*) FILTER (WHERE volume_mm IS NULL) AS untracked,"
                            " COUNT(*) AS runs"
                            " FROM irrigation_runs"
                            " WHERE field_id=$1 AND status='completed'"
                            " AND (started_at AT TIME ZONE $3)::date = $2",
                            field_id,
                            today,
                            ledger_tz,
                        )

                    # مدخلات اليوم من خدمة الطقس؛ ET0 يُحسب في المحرّك حصراً (agro/et0) —
                    # لا نستهلك et0 المزوّد الخام. فشل أيّهما ⇒ تخطٍّ صادق لهذا اليوم.
                    # يومُ التوقّع الذي تاريخُه يومُ الدفتر لا ``days[0]`` أعمى: المزوّد يسمّي الأيّام
                    # بمنطقة الحقل، وقد تخالف WATER_LEDGER_TIMEZONE. لا تطابق ⇒ تخطٍّ لا قيدٌ بتاريخٍ خاطئ.
                    forecast = await get_weather_forecast(
                        float(row["lat"]), float(row["lon"]), days=2
                    )
                    day0 = forecast_day_for_ledger_date(forecast, today)
                    if day0 is None:
                        print(
                            json.dumps(
                                {
                                    "worker": "water_ledger",
                                    "field_id": field_id,
                                    "skipped": "forecast_day_not_ledger_date",
                                    "ledger_date": today.isoformat(),
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
                        continue
                    rain_updates: list[dict] = []
                    rebuilt_prev_depletion = None
                    if reconcile_from is not None:
                        try:
                            observed = observed_rain_by_date(
                                await get_weather_historical(
                                    float(row["lat"]),
                                    float(row["lon"]),
                                    start_date=reconcile_from.isoformat(),
                                    end_date=(today - _dt.timedelta(days=1)).isoformat(),
                                    tenant_id=str(row["tenant_id"]),
                                )
                            )
                            rain_updates, rebuilt_prev_depletion = rebuild_rain_chain(
                                window_rows, observed, today, AUTO_CREATED_BY
                            )
                        except Exception as exc:  # noqa: BLE001 — أرشيفٌ غائب أو قيدٌ لا يُبنى ⇒ يبقى التوقّع معلَناً
                            # Declared, not silent: an archive that always fails would otherwise
                            # leave forecast rain booked forever with nothing in the logs.
                            print(
                                json.dumps(
                                    {
                                        "worker": "water_ledger",
                                        "skip": "rain_reconcile_unavailable",
                                        "error": type(exc).__name__,
                                    }
                                ),
                                flush=True,
                            )
                            rain_updates, rebuilt_prev_depletion = [], None
                    t_max, t_min = day0.get("temp_max_c"), day0.get("temp_min_c")
                    # ميّز «هطول مقيس = 0» عن «هطول مفقود» — الأخير يُفترَض 0 بإعلان لا صامتاً.
                    _precip = day0.get("precipitation_mm")
                    rain_assumed_zero = _precip is None
                    rain_mm = float(_precip or 0.0)
                    if t_max is None or t_min is None:
                        continue
                    # الرطوبة ومتوسّط الريح (محوَّلاً إلى 2م، FAO-56 Eq. 47) — لا قصوى اليوم.
                    et0 = await get_et0_product(
                        t_max_c=float(t_max),
                        t_min_c=float(t_min),
                        **et0_weather_inputs(day0),
                        lat_deg=float(row["lat"]),
                        elevation_m=elevation_m,
                        day_of_year=today.timetuple().tm_yday,
                        valid_time=today.isoformat(),
                        tenant_id=str(row["tenant_id"]),
                    )
                    et0_mm = et0.get("et0_mm")
                    if et0_mm is None:
                        continue

                    # المعاملة الثانية: سياق المستأجر من جديد (كان يزول بانتهاء الأولى)، ثمّ القيدُ وحده.
                    async with conn.transaction():
                        await _set_tenant(conn, row["tenant_id"])
                        prev_depletion = (
                            float(prev["depletion_mm"])
                            if prev and prev["depletion_mm"] is not None
                            else None
                        )
                        if rain_updates:
                            try:
                                # نقطةُ حفظ: سلسلةٌ تتغيّر بين الدورتين (قيدٌ صار يدويّاً أو تبدّل)
                                # تُرجَع كلُّها ولا تُرجِع قيدَ اليوم؛ يُبنى اليومُ عندئذٍ على المخزَّن.
                                async with conn.transaction():
                                    # ضبطُ المستأجر داخل نقطة الحفظ أيضاً: كلُّ معاملةٍ تربطه بنفسها.
                                    await _set_tenant(conn, row["tenant_id"])
                                    for upd in rain_updates:
                                        status = await conn.execute(
                                            "UPDATE water_ledger SET rain_mm=$3, rain_source=$4,"
                                            " depletion_mm=$5, deficit_mm=$6, confidence=$7,"
                                            " decision=$8, updated_at=now()"
                                            " WHERE field_id=$1 AND ledger_date=$2"
                                            " AND created_by=$9"
                                            " AND rain_source IS NOT DISTINCT FROM $10"
                                            " AND depletion_mm IS NOT DISTINCT FROM $11",
                                            field_id,
                                            upd["ledger_date"],
                                            upd["rain_mm"],
                                            upd["rain_source"],
                                            upd["depletion_mm"],
                                            upd["deficit_mm"],
                                            upd["confidence"],
                                            upd["decision"],
                                            AUTO_CREATED_BY,
                                            upd["expected_rain_source"],
                                            upd["expected_depletion_mm"],
                                        )
                                        if not str(status).endswith(" 1"):
                                            raise _RainChainChanged(str(upd["ledger_date"]))
                                if (
                                    rebuilt_prev_depletion is not None
                                    and prev is not None
                                    and rain_updates[-1]["ledger_date"] == prev["ledger_date"]
                                ):
                                    prev_depletion = rebuilt_prev_depletion
                            except _RainChainChanged:
                                pass
                        kc = crop_kc.kc
                        zone = await ledger_root_zone(
                            conn,
                            tenant_id=str(row["tenant_id"]),
                            field_id=field_id,
                            season_id=str(row["season_id"]) if row["season_id"] else None,
                            crop_kc=crop_kc,
                            variety=row["cultivar"],
                            texture=texture,
                            etc_mm_day=kc * float(et0_mm),
                        )
                        applied_mm = (
                            reported_irrigation_mm
                            if reported_irrigation_mm is not None
                            else float(irr["mm"] or 0.0)
                        )
                        entry = compute_daily_ledger_entry(
                            prev_depletion_mm=prev_depletion,
                            taw_mm=zone["taw_mm"],
                            raw_mm=zone["raw_mm"],
                            et0_mm=float(et0_mm),
                            kc=kc,
                            rain_mm=rain_mm,
                            irrigation_mm=applied_mm,
                            # A reported figure is the day's measured total: neither flag applies.
                            irrigation_volume_untracked=bool(irr["untracked"])
                            and reported_irrigation_mm is None,
                            irrigation_unobserved=not int(irr["runs"] or 0)
                            and reported_irrigation_mm is None,
                            rain_assumed_zero=rain_assumed_zero,
                            et0_reference_unavailable=not et0_product_is_reference(et0),
                            root_zone_texture_fallback=zone["root_zone_texture_fallback"],
                            depletion_fraction_default=zone["depletion_fraction_default"],
                            missing_prior_days=missing_days,
                            missing_days_irrigation_mm=gap_irrigation_mm,
                            missing_days_irrigation_unobserved=gap_unobserved,
                            missing_days_irrigation_untracked=gap_untracked,
                        )
                        # The WHERE keeps a row another writer took between the read above and
                        # this write (a manual entry, an as-applied reconciliation): no row is
                        # returned, nothing is written, and the bridge does not run on it.
                        stored = await conn.fetchval(
                            """
                            INSERT INTO water_ledger
                              (tenant_id, field_id, ledger_date, et0_mm, kc, etc_mm, rain_mm,
                               irrigation_mm, depletion_mm, deficit_mm, stage, decision,
                               confidence, created_by, et0_method, et0_quality,
                               weather_snapshot_id, rain_source, taw_mm, raw_mm,
                               created_at, updated_at)
                            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                                    $13, $14, $15, $16, $17, $18, $19, $20, now(), now())
                            ON CONFLICT (field_id, ledger_date) DO UPDATE SET
                              et0_mm = EXCLUDED.et0_mm, kc = EXCLUDED.kc, etc_mm = EXCLUDED.etc_mm,
                              rain_mm = EXCLUDED.rain_mm,
                              irrigation_mm = CASE
                                WHEN water_ledger.irrigation_reported_by IS NOT NULL
                                THEN water_ledger.irrigation_mm
                                ELSE EXCLUDED.irrigation_mm END,
                              depletion_mm = EXCLUDED.depletion_mm, deficit_mm = EXCLUDED.deficit_mm,
                              stage = EXCLUDED.stage, decision = EXCLUDED.decision,
                              confidence = EXCLUDED.confidence, et0_method = EXCLUDED.et0_method,
                              taw_mm = EXCLUDED.taw_mm, raw_mm = EXCLUDED.raw_mm,
                              et0_quality = EXCLUDED.et0_quality,
                              weather_snapshot_id = EXCLUDED.weather_snapshot_id,
                              rain_source = EXCLUDED.rain_source, updated_at = now()
                            WHERE water_ledger.created_by = EXCLUDED.created_by
                            RETURNING 1
                            """,
                            str(row["tenant_id"]),
                            field_id,
                            today,
                            float(et0_mm),
                            kc,
                            entry["etc_mm"],
                            rain_mm,
                            applied_mm,
                            entry["depletion_mm"],
                            entry["deficit_mm"],
                            crop_kc.stage,
                            entry["decision"],
                            entry["confidence"],
                            AUTO_CREATED_BY,
                            et0.get("method"),
                            et0.get("quality_status"),
                            et0.get("weather_snapshot_id"),
                            RAIN_SOURCE_FORECAST,
                            zone["taw_mm"],
                            zone["raw_mm"],
                        )
                        if stored is None:
                            continue  # الإنسان سيّد الدفتر — كُتِب القيد بعد قراءتنا.
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
                            "taw_mm": zone["taw_mm"],
                            "raw_mm": zone["raw_mm"],
                        },
                        # W2-02: the season's crop and cultivar for the AC-1 lineage.
                        crop=row["field_crop"],
                        cultivar_id=row["cultivar"],
                    )
                    if bridge_result.get("status") not in {"disabled", "below_threshold"}:
                        async with conn.transaction():
                            await _set_tenant(conn, row["tenant_id"])
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
                                        "season_id": str(row["season_id"])
                                        if row["season_id"]
                                        else None,
                                        "ledger_date": today.isoformat(),
                                        "deficit_mm": entry["deficit_mm"],
                                    }
                                ),
                                _water_deficit_dedup_key(
                                    row["tenant_id"], field_id, today, bridge_result
                                ),
                            )

                except Exception as exc:  # noqa: BLE001 — تخطٍّ لكلّ حقل مُعلَّل، لا انهيار الدفعة
                    print(
                        json.dumps(
                            {
                                "worker": "water_ledger",
                                "field_id": field_id,
                                "skipped": str(exc)[:200],
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
            if len(fields) < batch_size:
                break
    return processed


async def loop_worker(kind: str) -> None:
    # CT-03 (تدقيق الحاويات V21): هويّة الخدمة إلزاميّة — نرفض الإقلاع قبل أيّ اتّصال متى
    # فُعّل جسر عجز الماء في الإنتاج وكان SAHOOL_AGENT_TOKEN فارغاً، كي لا يحاول عاملٌ
    # مجهول الهويّة دفع مرشّحات قرار محكومة إلى decision-service (الرسالة لا تطبع التوكن).
    if kind == "water_ledger":
        from api.water_decision_bridge import water_ledger_identity_startup_error

        identity_error = water_ledger_identity_startup_error()
        if identity_error:
            raise RuntimeError(identity_error)
        from api.water_decision_bridge import bridge_enabled as water_bridge_enabled

        if water_bridge_enabled():
            # W2-02 (decision-9): a bridge that can never carry AC-1 lineage does not start.
            from api.agronomic_context_composer import agronomic_context_startup_error

            if ac1_error := agronomic_context_startup_error():
                raise RuntimeError(ac1_error)
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
    # CT-06 (تدقيق الحاويات V21 §2.1): نبضة كلّ دورة تُثبِت أنّ حلقة المعالجة تتحرّك — يقرؤها
    # healthcheck الحاوية (حداثة + حالة) بدل مجرّد وجود متغيّر بيئة. خطأ المُشغّل يُسجَّل في
    # النبضة ثمّ يُعاد رفعه فتتقادم النبضة وتُعاد الحاوية (لا إخفاء لتوقّف وظيفيّ).
    from api.worker_heartbeat import HeartbeatState

    hb = HeartbeatState(worker_name=f"phase-runtime-{kind}")
    hb.write()
    try:
        while True:
            try:
                processed = await runners[kind](pool)
            except Exception as exc:  # noqa: BLE001 — نُسجّل الفشل في النبضة ثمّ نُعيد رفعه
                hb.mark_error(str(exc))
                hb.write()
                raise
            hb.mark_poll(processed)
            hb.write()
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
