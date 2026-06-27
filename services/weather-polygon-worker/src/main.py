"""weather-polygon-worker — يربط تنبّؤ الطقس بالحقول مكانيّاً (P0، غلاف رفيع).

عند حدث sahool.weather.forecast.updated: لكلّ حقل، يجد خلايا شبكة الطقس داخل مضلّعه
(ST_Within على fields.geom)، يجمع تنبّؤها، ويحسب سجلّ التراكب + الإشارات عبر **النواة
النقيّة المُختبَرة** (core.weather_overlay_pipeline)، ثمّ يكتبها وينشر اكتمال التراكب.

أمن: يتّصل بدور **sahool_jobs** (BYPASSRLS) عبر JOBS_DATABASE_URL — مهمّة خلفيّة عابرة
للمستأجرين بالتصميم (تقرأ كلّ الحقول، تكتب تراكب كلّ مستأجِر). لا postgres superuser.
النشر بعد إتمام المعاملة (نمط outbox: نجاح القاعدة أوّلاً، ثمّ NATS — فشل النشر لا يُفقِد
التراكب). asyncpg (لا SQLAlchemy) مطابقةً للمنصّة، ومواضيع NATS ببادئة sahool.

────────────────────────────────────────────────────────────────────────────────
حالة التشغيل (H2 — سقالة ساكنة عمداً):
هذا الخطّ (مسار الطقس الشبكيّ grid) **معطّل افتراضيّاً**. الاشتراك على
`sahool.weather.forecast.updated` **يتيم**: لا ناشر له في المستودع بعدُ (M2 في تقرير
الفجوات). تشغيله بلا منتِج يجعل العامل يتّصل بـPostgres/NATS ثمّ ينتظر إلى الأبد دون أيّ
عمل — لا‑عمليّة صامتة تُربك التشغيل والمراقبة. لذا نحرس الاشتراك خلف راية بيئيّة
`WEATHER_GRID_PIPELINE_ENABLED` (افتراضها OFF)، ونطبع عند الإقلاع سطراً يوضّح أنّها سقالة
غير نشطة بانتظار منتِج. **مسار الطقس الحيّ المستعمَل فعليّاً منفصل تماماً** ويعيش في
المنصّة (`api/connectors/openmeteo.py` + `api/weather_automation.py`) — لا علاقة له بهذا
العامل ولا يتأثّر بهذه الراية. لتفعيل هذا الخطّ مستقبلاً: ابنِ منتِجاً ينشر الموضوع أعلاه
ثمّ اضبط `WEATHER_GRID_PIPELINE_ENABLED=1`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import asyncpg
from core.weather_overlay_pipeline import build_overlay_record, build_signal_records

import nats

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("weather-polygon-worker")

JOBS_DSN = os.getenv("JOBS_DATABASE_URL") or os.getenv("DATABASE_URL", "")
NATS_URL = os.getenv("NATS_URL", "nats://sahool-nats:4222")
HORIZON_HOURS = int(os.getenv("WEATHER_HORIZON_HOURS", "168"))

READY_FILE = Path(os.getenv("WORKER_READY_FILE", "/tmp/sahool-worker-ready"))
HEARTBEAT_FILE = Path(os.getenv("WORKER_HEARTBEAT_FILE", "/tmp/sahool-worker-heartbeat"))


def _touch_worker_file(path: Path) -> None:
    path.write_text(str(int(time.time())))


def _grid_pipeline_enabled() -> bool:
    """راية تفعيل مسار الطقس الشبكيّ (H2). افتراضها OFF لأنّ الاشتراك يتيم بلا منتِج.
    تُعتبر مفعّلة فقط بقيم صريحة موجبة كي لا يُفعَّل الخطّ بالخطأ."""
    return os.getenv("WEATHER_GRID_PIPELINE_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


_FIELDS_SQL = "SELECT field_id, tenant_id FROM fields WHERE geom IS NOT NULL"
_GRID_IN_FIELD_SQL = (
    "SELECT g.grid_id AS cell_key FROM weather_grid g "
    "JOIN fields f ON ST_Within(g.geom, f.geom) WHERE f.field_id = $1"
)
_FORECAST_SQL = (
    "SELECT date_trunc('hour', wf.time) AS hour, wf.grid_id AS cell_key, "
    "wf.temperature_2m_c AS temp_avg, wf.temperature_2m_c AS temp_min, "
    "wf.temperature_2m_c AS temp_max, wf.humidity_percent AS humidity, "
    "wf.wind_speed_10m_ms AS wind_speed, wf.wind_speed_10m_ms AS wind_gust, "
    "wf.precipitation_mm AS precip_sum, wf.precipitation_probability AS precip_prob, "
    "wf.et0_mm AS et0, wf.delta_t_c AS delta_t "
    "FROM weather_forecasts wf "
    "WHERE wf.grid_id = ANY($1::text[]) "
    "AND wf.time BETWEEN NOW() AND NOW() + ($2 || ' hours')::interval"
)
_UPSERT_OVERLAY = (
    "INSERT INTO field_weather_overlay (field_id, tenant_id, time, temperature_min_c, "
    "temperature_max_c, temperature_avg_c, humidity_avg_percent, wind_speed_avg_ms, "
    "wind_gust_max_ms, precipitation_sum_mm, precipitation_probability, et0_sum_mm, "
    "delta_t_avg_c, spray_suitability_score, disease_risk_score, heat_stress_hours, "
    "frost_risk_hours, trafficability_score, grid_cells_count, spatial_coverage) "
    "VALUES ($1,$2,NOW(),$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19) "
    "ON CONFLICT (tenant_id, field_id, time) DO NOTHING"
)
_INSERT_SIGNAL = (
    "INSERT INTO weather_signals (tenant_id, field_id, signal_type, confidence_score, "
    "time, valid_until, payload) VALUES ($1,$2,$3,$4,NOW(), "
    "NOW() + ($5 || ' hours')::interval, CAST($6 AS jsonb))"
)


async def process_field(conn, field_id: str, tenant_id: str) -> dict | None:
    cells = [r["cell_key"] for r in await conn.fetch(_GRID_IN_FIELD_SQL, field_id)]
    if not cells:
        return None
    rows = [dict(r) for r in await conn.fetch(_FORECAST_SQL, cells, str(HORIZON_HOURS))]
    overlay = build_overlay_record(field_id, tenant_id, rows)
    if overlay is None:
        return None
    async with conn.transaction():
        o = overlay
        await conn.execute(
            _UPSERT_OVERLAY,
            o["field_id"],
            o["tenant_id"],
            o["temperature_min_c"],
            o["temperature_max_c"],
            o["temperature_avg_c"],
            o["humidity_avg_percent"],
            o["wind_speed_avg_ms"],
            o["wind_gust_max_ms"],
            o["precipitation_sum_mm"],
            o["precipitation_probability"],
            o["et0_sum_mm"],
            o["delta_t_avg_c"],
            o["spray_suitability_score"],
            o["disease_risk_score"],
            o["heat_stress_hours"],
            o["frost_risk_hours"],
            o["trafficability_score"],
            o["grid_cells_count"],
            o["spatial_coverage"],
        )
        for s in build_signal_records(field_id, tenant_id, overlay):
            await conn.execute(
                _INSERT_SIGNAL,
                s["tenant_id"],
                s["field_id"],
                s["signal_type"],
                s["confidence_score"],
                str(HORIZON_HOURS),
                json.dumps(s["payload"]),
            )
    return overlay


async def run() -> None:
    # H2: السقالة الساكنة. الاشتراك يتيم (لا منتِج لـsahool.weather.forecast.updated بعدُ).
    # نخرج صراحةً بسطر واضح بدل التعطّل الصامت على اشتراك لن يصله حدث أبداً.
    if not _grid_pipeline_enabled():
        _touch_worker_file(READY_FILE)
        _touch_worker_file(HEARTBEAT_FILE)
        # inactive readiness: container remains healthy but explicitly idle behind feature flag.
        log.info(
            "weather-polygon-worker معطّل (سقالة غير نشطة): مسار الطقس الشبكيّ بانتظار "
            "منتِج لـsahool.weather.forecast.updated. فعّله بـWEATHER_GRID_PIPELINE_ENABLED=1 "
            "بعد بناء المنتِج. مسار الطقس الحيّ في المنصّة لا يتأثّر."
        )
        while True:
            _touch_worker_file(HEARTBEAT_FILE)
            await asyncio.sleep(60)
    if not JOBS_DSN:
        log.error("JOBS_DATABASE_URL/DATABASE_URL غير مضبوط — العامل معطّل")
        return
    pool = await asyncpg.create_pool(JOBS_DSN, statement_cache_size=0, min_size=1, max_size=4)
    nc = await nats.connect(NATS_URL, max_reconnect_attempts=-1)
    _touch_worker_file(READY_FILE)
    _touch_worker_file(HEARTBEAT_FILE)
    js = nc.jetstream()
    sub = await js.subscribe("sahool.weather.forecast.updated", durable="polygon-worker")
    log.info("✓ weather-polygon-worker بدأ — يستمع sahool.weather.forecast.updated")
    async for msg in sub:
        _touch_worker_file(HEARTBEAT_FILE)
        try:
            async with pool.acquire() as conn:
                fields = await conn.fetch(_FIELDS_SQL)
                done = 0
                for f in fields:
                    if await process_field(conn, f["field_id"], str(f["tenant_id"])):
                        done += 1
            # نشر بعد إتمام القاعدة (outbox): فشل النشر لا يُفقِد التراكب المحفوظ.
            #
            # «طريق مسدود» مُعلَن بصدق — لا عطل:
            # الموضوع sahool.weather.field.overlay.completed موجَّه لمشترِك *مستقبليّ*
            # (تحديث واجهات/إشعارات عند جاهزيّة تراكب الطقس). لا مستهلك مُسلَّم اليوم بقصد:
            # هذا المسار بأكمله سقالة غير نشطة محروسة بالعلم WEATHER_GRID_PIPELINE_ENABLED
            # (OFF افتراضيّاً — انظر _grid_pipeline_enabled حوالي سطر 45)، ويبقى كذلك حتّى
            # يُسلَّم المنتِج/المستهلك. لذا يَسِم tools/sahool_inspector.py هذا الناشر
            # بـ«ناشر بلا مشترِك» (WARN إرشاديّ لا حاجب) — وهو سلوك مُتوقَّع ومُعلَن.
            # قرار H2 المعماريّ: لا نُلفّق مستهلكاً/مشترِكاً وهميّاً لإسكات المفتّش.
            await js.publish(
                "sahool.weather.field.overlay.completed",
                json.dumps({"fields_processed": done}).encode(),
            )
        except Exception as e:  # noqa: BLE001 — لا يُسقِط العامل على حدث واحد
            log.warning("تعذّر معالجة حدث التنبّؤ: %s", e)
        finally:
            await msg.ack()


if __name__ == "__main__":
    asyncio.run(run())
