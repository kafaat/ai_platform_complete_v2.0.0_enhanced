"""weather-signal-engine — يولّد إشارات الطقس آليّاً من تراكبات الحقول على جدول (P1).

بدل البذر اليدويّ لـweather_signals: حلقة مجدولة تمرّ كلّ WEATHER_SIGNAL_INTERVAL_SEC،
تجلب **أحدث تراكب** لكلّ (tenant_id, field_id) من field_weather_overlay خلال الساعة
الأخيرة، تبني سجلّات الإشارات عبر **النواة النقيّة المُختبَرة** (build_signal_records)،
ثمّ تكتبها في weather_signals. حتميّة إعادة التشغيل (idempotency): داخل معاملة واحدة
لكلّ حقل تُحذَف إشاراته السارية الحاليّة ثمّ تُدرَج الجديدة — فلا تتراكم تكرارات.

أمن: يتّصل بدور **sahool_jobs** (BYPASSRLS) عبر JOBS_DATABASE_URL — مهمّة خلفيّة عابرة
للمستأجرين بالتصميم (تقرأ تراكب كلّ مستأجِر، تكتب إشاراته). لا دور خارق (كي لا يلتفّ على
RLS). asyncpg (لا محرّك SQL مُجرّد) مطابقةً للمنصّة. تُستعمَل ANY مع cast نصّيّ لقوائم IN
وتحويل JSONB صريح للحمولة مطابقةً لأنماط المنصّة المُلزَمة بالحُرّاس.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import asyncpg
from core.weather_overlay_pipeline import build_signal_records

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("weather-signal-engine")

JOBS_DSN = os.getenv("JOBS_DATABASE_URL") or os.getenv("DATABASE_URL", "")
INTERVAL_SEC = int(os.getenv("WEATHER_SIGNAL_INTERVAL_SEC", "300"))
# صلاحيّة الإشارة المُولَّدة (ساعات): افتراضيّاً أفق التنبّؤ القصير.
SIGNAL_TTL_HOURS = int(os.getenv("WEATHER_SIGNAL_TTL_HOURS", "24"))

READY_FILE = Path(os.getenv("WORKER_READY_FILE", "/tmp/sahool-worker-ready"))
HEARTBEAT_FILE = Path(os.getenv("WORKER_HEARTBEAT_FILE", "/tmp/sahool-worker-heartbeat"))


def _touch_worker_file(path: Path) -> None:
    path.write_text(str(int(time.time())))


# أحدث تراكب لكلّ (tenant_id, field_id) خلال الساعة الأخيرة فقط (DISTINCT ON).
_RECENT_OVERLAYS_SQL = (
    "SELECT DISTINCT ON (tenant_id, field_id) "
    "tenant_id, field_id, spray_suitability_score, disease_risk_score, "
    "trafficability_score, heat_stress_hours, frost_risk_hours "
    "FROM field_weather_overlay "
    "WHERE time > NOW() - INTERVAL '1 hour' "
    "ORDER BY tenant_id, field_id, time DESC"
)
# حتميّة: نحذف الإشارات السارية الحاليّة لهذا الحقل (نفس الأنواع المُولَّدة) قبل الإدراج.
# ANY($2::text[]) لقائمة الأنواع (نمط المنصّة المُلزَم) — لا نمسّ إشارات نوع آخر.
_DELETE_CURRENT_SQL = (
    "DELETE FROM weather_signals "
    "WHERE tenant_id = $1 AND field_id = $2 AND signal_type = ANY($3::text[]) "
    "AND time > NOW() - INTERVAL '1 hour'"
)
_INSERT_SIGNAL_SQL = (
    "INSERT INTO weather_signals (tenant_id, field_id, signal_type, confidence_score, "
    "time, valid_until, payload) VALUES ($1,$2,$3,$4,NOW(), "
    "NOW() + ($5 || ' hours')::interval, CAST($6 AS jsonb))"
)


async def process_overlay(conn, overlay: dict) -> int:
    """يبني إشارات حقل واحد من أحدث تراكبه ويكتبها حتميّاً (حذف-ثمّ-إدراج).

    overlay يحمل أعمدة FieldWeatherScores (spray_suitability_score, disease_risk_score,
    trafficability_score, heat_stress_hours, frost_risk_hours). يُرجِع عدد الإشارات
    المُدرَجة. النواة النقيّة build_signal_records تتولّى منطق الإشارات (لا نُعيد بناءه)."""
    field_id = overlay["field_id"]
    tenant_id = str(overlay["tenant_id"])
    signals = build_signal_records(field_id, tenant_id, dict(overlay))
    if not signals:
        return 0
    types = [s["signal_type"] for s in signals]
    async with conn.transaction():
        await conn.execute(_DELETE_CURRENT_SQL, tenant_id, field_id, types)
        for s in signals:
            await conn.execute(
                _INSERT_SIGNAL_SQL,
                s["tenant_id"],
                s["field_id"],
                s["signal_type"],
                s["confidence_score"],
                str(SIGNAL_TTL_HOURS),
                json.dumps(s["payload"]),
            )
    return len(signals)


async def run_cycle(pool) -> int:
    """دورة واحدة: يجلب أحدث التراكبات الطازجة ويولّد إشاراتها. يُرجِع عدد الإشارات."""
    total = 0
    async with pool.acquire() as conn:
        overlays = await conn.fetch(_RECENT_OVERLAYS_SQL)
        for ov in overlays:
            total += await process_overlay(conn, ov)
    return total


async def run() -> None:
    if not JOBS_DSN:
        log.error("JOBS_DATABASE_URL/DATABASE_URL غير مضبوط — المحرّك معطّل")
        return
    pool = await asyncpg.create_pool(JOBS_DSN, statement_cache_size=0, min_size=1, max_size=4)
    _touch_worker_file(READY_FILE)
    _touch_worker_file(HEARTBEAT_FILE)
    log.info("✓ weather-signal-engine بدأ — دورة كلّ %ss", INTERVAL_SEC)
    try:
        while True:
            try:
                count = await run_cycle(pool)
                _touch_worker_file(HEARTBEAT_FILE)
                log.info("دورة الإشارات: أُدرِجَت %s إشارة", count)
            except Exception as e:  # noqa: BLE001 — فشل دورة واحدة لا يُسقِط الحلقة
                log.warning("تعذّرت دورة توليد الإشارات: %s", e)
            await asyncio.sleep(INTERVAL_SEC)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
