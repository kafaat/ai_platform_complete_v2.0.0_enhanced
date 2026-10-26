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

**القارئ صادقٌ عن مصدره (FIELD-WEATHER-OVERLAY-HAS-A-READER-AND-NO-WRITER-01).**
لا شيء في الشجرة يكتب field_weather_overlay منذ حذف weather-polygon-worker (#1205)،
ولا شيء يكتب weather_forecasts التي كان سيُبنى منها التراكب. فكانت كلُّ دورةٍ تقرأ
صفراً من الصفوف وتُسجّل «أُدرِجَت 0 إشارة» بمستوى INFO — وهو سطرٌ يُقرَأ «لا خطر
طقسيّ» وحقيقتُه «لا بيانات». والكاتبُ لا يُضاف هنا: لا منتِجَ لتنبّؤ الخلايا، ومخطّط
v74 لا يحمل مقامات التقييم (hours_evaluated · frost/heat_evaluable_hours) التي بدونها
تُرجِع النواة صفرَ إشارات لأيّ صفّ — أي أنّ كاتباً بلا هجرة يُنتج صفوفاً لا تُولِّد
شيئاً. والقرارُ بين المنتِج الحقيقيّ وإزالة القارئ معلّقٌ لدى المالك
(docs/architecture/decisions_pending/FIELD-WEATHER-OVERLAY-HAS-A-READER-AND-NO-WRITER-01.md).
لذلك تُعيد الدورةُ **حالةً مُسمّاة** (CycleReport) لا عدداً: لا بيانات · بيانات بائتة ·
تراكب بلا أساس تقييم · عُولِج — وتُعلَن غيرُ «عُولِج» بتحذيرٍ يُسمّي سببها.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import asyncpg
from core.weather_overlay_pipeline import build_signal_records

from shared.startup_retry import retry_startup_connect

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
# يُستعلَم فقط حين لا تراكب طازجاً: يُفرِّق «لا صفّ قطّ» (لا منتِج) عن «منتِجٌ توقّف».
_NEWEST_OVERLAY_SQL = "SELECT max(time) FROM field_weather_overlay"
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


GAP_ID = "FIELD-WEATHER-OVERLAY-HAS-A-READER-AND-NO-WRITER-01"

# حالاتُ الدورة — كلٌّ منها جوابٌ مختلف عن «لماذا لا إشارات؟»، فلا تُدمَج في عددٍ صفريّ.
STATE_NO_OVERLAY_DATA = "no_overlay_data"  # الجدول بلا أيّ صفّ: لا منتِج يكتبه
STATE_STALE_OVERLAY_DATA = "stale_overlay_data"  # صفوفٌ قديمة، لا شيء خلال الساعة
STATE_OVERLAY_NOT_EVALUABLE = "overlay_not_evaluable"  # صفوفٌ طازجة بلا ساعاتٍ مُقيَّمة
STATE_PROCESSED = "processed"


class CycleReport(NamedTuple):
    """نتيجةُ دورةٍ واحدة بحالتها المُسمّاة، لا عددُ إشاراتٍ وحده.

    «0 إشارة» وحدها لا تُفرِّق بين «رُصِد طقسٌ لا يستدعي إشارة» و«لا شيء رُصِد» —
    والثاني هو الواقع اليوم. الحالةُ تقول أيّهما."""

    state: str
    overlays: int = 0
    signals: int = 0
    failed: int = 0
    unevaluable: int = 0
    newest_overlay_at: datetime | None = None


def is_evaluable(overlay) -> bool:
    """صفٌّ بلا ساعاتٍ مُقيَّمة لا يُولِّد إشارةً أبداً (generate_signals يُرجِع [] عند 0).

    ومخطّط v74 لا يحمل العمود، فالاستعلامُ لا يُعيده — أي أنّ كلَّ صفٍّ يُقرَأ اليوم غيرُ
    قابلٍ للتقييم. يُعَدّ ويُعلَن بدل أن يذوب في «0 إشارة»."""
    try:
        return (overlay.get("hours_evaluated") or 0) > 0
    except AttributeError:
        return False


def classify_cycle(
    *,
    overlays: int,
    signals: int,
    failed: int = 0,
    unevaluable: int = 0,
    newest_overlay_at: datetime | None = None,
) -> CycleReport:
    """يُسمّي حالةَ الدورة من مقاييسها (نقيّ)."""
    if overlays == 0:
        state = STATE_NO_OVERLAY_DATA if newest_overlay_at is None else STATE_STALE_OVERLAY_DATA
    elif signals == 0 and unevaluable == overlays:
        state = STATE_OVERLAY_NOT_EVALUABLE
    else:
        state = STATE_PROCESSED
    return CycleReport(
        state=state,
        overlays=overlays,
        signals=signals,
        failed=failed,
        unevaluable=unevaluable,
        newest_overlay_at=newest_overlay_at,
    )


def describe_cycle(report: CycleReport, previous_state: str | None = None) -> tuple[int, str]:
    """(مستوى السجلّ، الرسالة). غيرُ «عُولِج» تحذيرٌ عند الانتقال إليه، ثمّ INFO ما دام قائماً
    — يُرى أوّلَ مرّة ولا يُغرِق السجلّ كلَّ خمس دقائق. والرسالةُ تُسمّي الحالة دائماً."""
    if report.state == STATE_PROCESSED:
        return logging.INFO, (
            f"دورة الإشارات [{report.state}]: أُدرِجَت {report.signals} إشارة "
            f"من {report.overlays} تراكب"
        )
    if report.state == STATE_NO_OVERLAY_DATA:
        msg = (
            f"دورة الإشارات [{report.state}]: field_weather_overlay بلا أيّ صفّ — لا منتِج "
            f"يكتبه ({GAP_ID}). لا إشارات طقس من هذا المصدر، وغيابُها ليس «لا خطر»."
        )
    elif report.state == STATE_STALE_OVERLAY_DATA:
        msg = (
            f"دورة الإشارات [{report.state}]: أحدثُ تراكب {report.newest_overlay_at} أقدمُ من "
            f"ساعة — لا إشارات؛ المنتِجُ متوقّف ({GAP_ID})."
        )
    else:
        msg = (
            f"دورة الإشارات [{report.state}]: {report.unevaluable} تراكباً طازجاً بلا ساعاتٍ "
            f"مُقيَّمة (hours_evaluated لا يحمله مخطّط v74) — لا إشارة تُحسَب ({GAP_ID})."
        )
    level = logging.WARNING if report.state != previous_state else logging.INFO
    return level, msg


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


async def run_cycle(pool) -> CycleReport:
    """دورة واحدة: يجلب أحدث التراكبات الطازجة ويولّد إشاراتها. يُرجِع حالتها المُسمّاة.

    **لا تراكب طازجاً ≠ لا خطر.** حين يعود الاستعلامُ فارغاً يُسأل الجدولُ عن أحدث صفٍّ
    فيه، فتُفرَّق «لا بيانات قطّ» عن «بيانات بائتة» — ولا تخرج الدورةُ عدداً صفريّاً صامتاً.

    **الحراسةُ لكلّ صفٍّ لا للدورة:** حقلٌ واحدٌ ببياناتٍ فاسدة كان يرفع استثناءً
    يخرج من الحلقة كلِّها، فتبقى **بقيّةُ الحقول بلا إشارات** حتّى الدورة التالية —
    وعقوبةُ صفٍّ واحدٍ تقع على كلّ مستأجرٍ في الدفعة. والسجلُّ كان يقول «تعذّرت
    دورة توليد الإشارات» بلا اسم الحقل الجاني، فيتكرّر العطلُ كلَّ دورةٍ بلا مَقود.

    ولا يُبتلَع الفشل: كلُّ إخفاقٍ يُسجَّل باسم مستأجره وحقله، والعددُ يُرفَع في
    نهاية الدورة — فصمتُ السجلّ يعني نجاحاً لا ابتلاعاً.
    """
    total = 0
    failed = 0
    unevaluable = 0
    newest = None
    async with pool.acquire() as conn:
        overlays = await conn.fetch(_RECENT_OVERLAYS_SQL)
        if not overlays:
            newest = await conn.fetchval(_NEWEST_OVERLAY_SQL)
        for ov in overlays:
            if not is_evaluable(ov):
                unevaluable += 1
            try:
                total += await process_overlay(conn, ov)
            except Exception as exc:  # noqa: BLE001 — صفٌّ واحدٌ لا يُسقِط الدفعة
                failed += 1
                log.warning(
                    "تعذّرت إشاراتُ الحقل tenant=%s field=%s: %s",
                    ov["tenant_id"],
                    ov["field_id"],
                    exc,
                )
    if failed:
        log.warning("دورة الإشارات: %s حقلاً أخفق من %s", failed, len(overlays))
    return classify_cycle(
        overlays=len(overlays),
        signals=total,
        failed=failed,
        unevaluable=unevaluable,
        newest_overlay_at=newest,
    )


async def run() -> None:
    if not JOBS_DSN:
        log.error("JOBS_DATABASE_URL/DATABASE_URL غير مضبوط — المحرّك معطّل")
        return
    # RESTART-POLICY-BYPASSES-DEPENDS-ON-HEALTH-01: إعادة restart لا تنتظر Postgres.
    pool = await retry_startup_connect(
        asyncpg.create_pool, JOBS_DSN, statement_cache_size=0, min_size=1, max_size=4
    )
    _touch_worker_file(READY_FILE)
    _touch_worker_file(HEARTBEAT_FILE)
    log.info("✓ weather-signal-engine بدأ — دورة كلّ %ss", INTERVAL_SEC)
    previous_state: str | None = None
    try:
        while True:
            try:
                report = await run_cycle(pool)
                # النبضةُ تشهد لحياة العامل لا لوجود بيانات؛ الحالةُ في السجلّ تقول الثاني.
                _touch_worker_file(HEARTBEAT_FILE)
                level, msg = describe_cycle(report, previous_state)
                log.log(level, msg)
                previous_state = report.state
            except Exception as e:  # noqa: BLE001 — فشل دورة واحدة لا يُسقِط الحلقة
                log.warning("تعذّرت دورة توليد الإشارات: %s", e)
            await asyncio.sleep(INTERVAL_SEC)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
