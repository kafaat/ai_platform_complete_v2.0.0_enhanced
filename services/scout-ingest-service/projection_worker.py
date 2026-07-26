#!/usr/bin/env python3
"""عامل إسقاط scout-ingest (SCOUT-INGEST-01 / B1.3) — Pattern A: claim→project→complete.

يقرأ الإدخالات **المقبولة فقط** (دالّة claim تُصفّي على trust_status='accepted') ويُسقطها إلى
``external_field_observations`` (نموذج القراءة المملوك لـscout-ingest — لا scouting_pins المملوك للمنصّة).

**least-grant محفوظ:** claim/complete = SECURITY DEFINER (يملكهما sahool_ingest_resolver، BYPASSRLS)
فيمسحان عابراً للمستأجرين ويحدّثان projection_status دون منح UPDATE لـsahool_ingest. الإدراج فقط يتمّ
كـsahool_ingest (INSERT، بعد ضبط app.current_tenant ⇒ RLS WITH CHECK يمرّ). idempotent: observation_id
مشتقّ ⇒ ON CONFLICT DO NOTHING. خلف ``SCOUT_INGEST_PROJECTION_ENABLED`` (off افتراضاً).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from shared.contracts.ingest.projection import ProjectionSkip, project_submission

logger = logging.getLogger("scout-ingest.projection")

DATABASE_URL = os.getenv("DATABASE_URL", "")
BATCH = int(os.getenv("SCOUT_INGEST_PROJECTION_BATCH", "50"))
LEASE_SECONDS = int(os.getenv("SCOUT_INGEST_PROJECTION_LEASE_SECONDS", "120"))
POLL_SECONDS = float(os.getenv("SCOUT_INGEST_PROJECTION_POLL_SECONDS", "5"))
MAX_ATTEMPTS = int(os.getenv("SCOUT_INGEST_PROJECTION_MAX_ATTEMPTS", "6"))
_ENABLED_TRUE = {"1", "true", "yes", "on"}
# فترة الخمول حين تعطيل العامل: نبقى أحياءً (لا نخرج) كي لا يُنتِج خروج العمليّة
# مع restart:unless-stopped + فحص liveness (pgrep) حلقة إعادة تشغيل. استهلاك مُهمَل.
DISABLED_IDLE_SECONDS = float(os.getenv("SCOUT_INGEST_PROJECTION_DISABLED_IDLE_SECONDS", "3600"))


def enabled() -> bool:
    return os.getenv("SCOUT_INGEST_PROJECTION_ENABLED", "0").strip().lower() in _ENABLED_TRUE


async def _connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required for the scout-ingest projection worker")
    import asyncpg

    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


async def run_once(conn) -> dict[str, int]:
    """دورة claim واحدة: تُسقِط الدفعة المُطالَبة وتُغلق كلّ صفّ (projected/dead_letter/retry)."""
    counts = {"projected": 0, "dead_letter": 0, "retry": 0}
    rows = await conn.fetch(
        "SELECT * FROM claim_submissions_for_projection($1, $2)", BATCH, LEASE_SECONDS
    )
    for row in rows:
        ref = row["submission_ref"]
        tenant_id = row["tenant_id"]
        try:
            payload = row["normalized_payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            result = project_submission(
                tenant_id=str(tenant_id),
                idempotency_key=row["idempotency_key"],
                normalized_payload=payload or {},
                submitted_at=row["submitted_at"],
            )
            if isinstance(result, ProjectionSkip):
                await conn.execute(
                    "SELECT complete_submission_projection($1, 'dead_letter', $2)",
                    ref,
                    result.reason,
                )
                counts["dead_letter"] += 1
                continue
            # الإدراج كـsahool_ingest تحت سياق المستأجِر (RLS WITH CHECK يمرّ)؛ idempotent عبر PK.
            await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(tenant_id))
            await conn.execute(
                "INSERT INTO external_field_observations "
                "(observation_id, tenant_id, field_id, source_submission_key, observed_property, "
                " value, severity, lat, lng, observed_at) "
                "VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9,$10) "
                "ON CONFLICT (observation_id) DO NOTHING",
                result.observation_id,
                tenant_id,
                result.field_id,
                result.source_submission_key,
                result.observed_property,
                json.dumps(result.value, ensure_ascii=False) if result.value is not None else None,
                result.severity,
                result.lat,
                result.lng,
                result.observed_at,
            )
            await conn.execute("SELECT complete_submission_projection($1, 'projected', NULL)", ref)
            counts["projected"] += 1
        except Exception as exc:  # noqa: BLE001 — عزل الصفّ: فشل واحد لا يُسقط الدفعة
            terminal = int(row["attempts"]) >= MAX_ATTEMPTS
            status = "dead_letter" if terminal else "retry"
            await conn.execute(
                "SELECT complete_submission_projection($1, $2, $3)", ref, status, str(exc)[:4000]
            )
            counts[status] = counts.get(status, 0) + 1
            logger.warning("projection %s for submission %s: %s", status, ref, exc)
    return counts


async def loop() -> None:
    if not enabled():
        # لا نخرج: الخروج مع restart:unless-stopped + فحص liveness يُنتِج حلقة إعادة
        # تشغيل (Finding 4). نبقى خاملين أحياءً (فحص pgrep أخضر) حتّى التفعيل.
        logger.info(
            "scout-ingest projection worker disabled (SCOUT_INGEST_PROJECTION_ENABLED); idling"
        )
        while True:
            await asyncio.sleep(DISABLED_IDLE_SECONDS)
    logger.info("scout-ingest projection worker started (batch=%s poll=%ss)", BATCH, POLL_SECONDS)
    while True:
        conn = await _connect()
        try:
            counts = await run_once(conn)
        finally:
            await conn.close()
        if not any(counts.values()):
            await asyncio.sleep(POLL_SECONDS)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(loop())


if __name__ == "__main__":
    main()
