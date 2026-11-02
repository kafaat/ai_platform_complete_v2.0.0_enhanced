"""
api/scheduler.py — جدولة المهام الدوريّة (أتمتة داخليّة خفيفة)

الفجوة التي يسدّها:
  المنصّة فيها event_bus بنمط outbox موثوق (للأحداث) وNATS (للتنسيق)، لكن
  لا يوجد ما **يُطلق** المهام الدوريّة تلقائيّاً: سحب الطقس يوميّاً، فحص صور
  Sentinel الجديدة كلّ دورة قمر، تنظيف البيانات، فحص نضارة القرارات.

لماذا هذا بدل n8n (قرار صريح):
  ✓ قابل للاختبار آليّاً (جزء من 283 اختبار)، عكس صناديق n8n
  ✓ يستخدم event_bus + asyncio الموجودين — بلا تبعيّة خارجيّة جديدة
  ✓ المنطق يبقى في كود مُراجَع، لا في طبقة بصريّة منفصلة
  ✗ ليس بديلاً لـNATS (التنسيق الحدثي) — مكمّل له (الإطلاق الزمني)
  n8n يبقى مناسباً للأتمتة المحيطيّة الخارجيّة (Telegram/Odoo/بريد) لو رغبت
  لاحقاً، لكنّ منطق القرار الزراعي يبقى هنا.

التصميم:
  - تسجيل مهامّ بفاصل زمني (seconds) + دالّة async
  - كلّ مهمّة معزولة: فشلها لا يُسقط البقيّة (try/except + backoff)
  - asyncio خالص، يبدأ/يتوقّف مع دورة حياة التطبيق (lifespan)
  - يسجّل آخر تشغيل/نجاح/فشل لكلّ مهمّة (مراقبة)
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("sahool.scheduler")

# نوع دالّة المهمّة: async بلا وسائط، تُرجع None
TaskFn = Callable[[], Awaitable[None]]


# R7: القفل الاستشاريّ يمنع **التداخل** فقط؛ نسخٌ بأطوارٍ مختلفة تُشغّل المهمّة N مرّة لكلّ
# فترة متتابعةً. نحجز «الفترة» في Redis (SET NX PX) فتعمل مرّة واحدة عبر العنقود لكلّ فترة.
# Redis مُلزَم للـdenylist في الإنتاج أصلاً (main._build_rate_redis)؛ بلا Redis أو عند عطله
# ⇒ fail-open إلى سلوك القفل وحده (عمل مكرّر أهون من تخطّي سحب الطقس).
_PERIOD_KEY_PREFIX = "sahool:scheduler:period:"
_PERIOD_SLACK_MAX_SECONDS = 30.0
# حذفٌ شرطيّ بالمالك: فشلُ نسختنا لا يمحو حجزاً أخذته نسخة أخرى بعد انقضاء TTL.
_RELEASE_IF_OWNER = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0"
)
_period_client: Any = None
_period_client_url: str | None = None


def _period_redis() -> Any:
    """عميل Redis للحجز الدوريّ أو None (يُبنى كسولاً من REDIS_URL؛ لا اتّصال عند البناء)."""
    global _period_client, _period_client_url
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    if _period_client is None or _period_client_url != url:
        import redis as _redis

        _period_client = _redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        _period_client_url = url
    return _period_client


def _period_ttl_ms(period_seconds: float) -> int:
    """TTL الحجز = الفترة ناقص هامش صغير (≤5%، ≤30ث).

    التكّة التالية لنسخةٍ واحدة تأتي بعد ``period`` كاملة من نهاية التشغيل ⇒ الحجز قد
    انقضى دائماً ⇒ سلوك النسخة الواحدة لا يتغيّر. الهامش يمتصّ انجراف الساعات/المؤقّتات.
    """
    slack = min(period_seconds * 0.05, _PERIOD_SLACK_MAX_SECONDS)
    return max(1, int((period_seconds - slack) * 1000))


async def _claim_period(task_name: str, period_seconds: float) -> str | bool:
    """يحجز فترة هذه المهمّة عبر العنقود. يُرجِع رمز الحجز، أو False إن حجزتها نسخة
    أخرى، أو True إن تعذّر Redis (fail-open: يُشغَّل كما قبل R7)."""
    client = _period_redis()
    if client is None:
        return True
    token = secrets.token_hex(8)
    try:
        claimed = await asyncio.to_thread(
            client.set,
            _PERIOD_KEY_PREFIX + task_name,
            token,
            nx=True,
            px=_period_ttl_ms(period_seconds),
        )
    except Exception as e:  # noqa: BLE001 — عطل Redis لا يُجمّد المهامّ (fail-open)
        logger.warning("مهمّة %s: تعذّر حجز الفترة في Redis (%s) — تشغيل بالقفل وحده", task_name, e)
        return True
    return token if claimed else False


async def _settle_period(task_name: str, period_seconds: float, token: str, ok: bool) -> None:
    """نجاح ⇒ تُعاد الفترة من **نهاية** التشغيل (التشغيل الطويل لا يُقصِّرها).
    فشل ⇒ يُحرَّر الحجز ليُعاد المحاولة (backoff أو نسخة أخرى) — تُسجَّل الفترة الناجحة فقط."""
    client = _period_redis()
    if client is None:
        return
    key = _PERIOD_KEY_PREFIX + task_name
    try:
        if ok:
            await asyncio.to_thread(client.set, key, token, px=_period_ttl_ms(period_seconds))
        else:
            await asyncio.to_thread(client.eval, _RELEASE_IF_OWNER, 1, key, token)
    except Exception as e:  # noqa: BLE001 — أسوأ الحالات: تشغيل إضافيّ، لا تجميد
        logger.warning("مهمّة %s: تعذّر تسوية حجز الفترة (%s)", task_name, e)


@asynccontextmanager
async def _advisory_session_lock(pool: Any, lock_key: str) -> AsyncIterator[bool]:
    """قفل استشاريّ جلسيّ غير حاجب؛ يُعطي True إن مُلِك، ويُحرَّر على نفس الاتّصال."""
    async with pool.acquire() as conn:
        locked = await conn.fetchval("SELECT pg_try_advisory_lock(hashtext($1))", lock_key)
        if not locked:
            yield False
            return
        try:
            yield True
        finally:
            # نفس الاتّصال ⇒ نفس الجلسة ⇒ تحرير صحيح (القفل جلسيّ لا معامليّ).
            await conn.execute("SELECT pg_advisory_unlock(hashtext($1))", lock_key)


def cluster_singleton(fn: TaskFn, *, task_name: str, pool_getter: Callable[[], Any]) -> TaskFn:
    """يلفّ مهمّة مجدولة لتعمل على **نسخة واحدة فقط** عبر نسخ المنصّة (أفضل ممارسة).

    المُجدوِل يعمل داخل العمليّة (asyncio) في كلّ نسخة؛ بلا تنسيق، N نسخة تُطلق نفس
    المهمّة الدوريّة N مرّة (ضرب مزوّد مكرّر، عمل زائد). هذا اللفّ يحصل على قفل استشاريّ
    **غير حاجب على مستوى الجلسة** (``pg_try_advisory_lock``): النسخة التي تملك القفل
    تُشغّل المهمّة، والبقيّة تتخطّى هذه التكّة بلا خطأ. جلسة لا معاملة مفتوحة (المهمّة قد
    تطول — لا نُبقي transaction مفتوحاً)؛ القفل يُحرَّر في ``finally``، ويُحرِّره Postgres
    تلقائيّاً إن ماتت الجلسة (انهيار النسخة لا يُجمِّد المهمّة أبداً).

    والقفل وحده يمنع التداخل لا التكرار (R7): تحته يُحجَز «الفترة» عبر Redis فتعمل المهمّة
    مرّة لكلّ فترة عبر العنقود. الفترة = فاصل التسجيل، يربطها ``Scheduler.register`` عبر
    ``bind_period`` (مصدر واحد للحقيقة). بلا ربط ⇒ القفل وحده (السلوك السابق).

    بلا مسبح (تطوير/متدهور): تعمل المهمّة محليّاً — عمليّة واحدة أصلاً، لا تنازع.
    """
    lock_key = f"sahool-scheduler:{task_name}"
    period: dict[str, float | None] = {"seconds": None}

    async def _run_once_per_period() -> None:
        seconds = period["seconds"]
        if seconds is None:
            await fn()
            return
        claim = await _claim_period(task_name, seconds)
        if claim is False:
            logger.info("مهمّة %s: تُخطّيت — نُفِّذت في هذه الفترة على نسخة أخرى", task_name)
            return
        if claim is True:  # Redis غير متاح ⇒ القفل وحده
            await fn()
            return
        try:
            await fn()
        except BaseException:
            await _settle_period(task_name, seconds, claim, ok=False)
            raise
        await _settle_period(task_name, seconds, claim, ok=True)

    async def _wrapped() -> None:
        pool = pool_getter()
        if pool is None:
            await fn()
            return
        async with _advisory_session_lock(pool, lock_key) as locked:
            if not locked:
                logger.info(
                    "مهمّة %s: تُخطّيت هذه التكّة — نسخة أخرى تحمل القفل الاستشاريّ",
                    task_name,
                )
                return
            await _run_once_per_period()

    def _bind_period(seconds: float) -> None:
        period["seconds"] = float(seconds)

    _wrapped.bind_period = _bind_period  # type: ignore[attr-defined]
    return _wrapped


@dataclass
class ScheduledTask:
    name: str
    interval_seconds: float
    fn: TaskFn
    enabled: bool = True
    # حالة المراقبة
    last_run_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    run_count: int = 0
    error_count: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "last_run_at": self.last_run_at,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "run_count": self.run_count,
            "error_count": self.error_count,
        }


class Scheduler:
    """جدولة خفيفة قائمة على asyncio. كلّ مهمّة في حلقتها المستقلّة."""

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._handles: list[asyncio.Task] = []
        self._running = False

    def register(
        self,
        name: str,
        interval_seconds: float,
        fn: TaskFn,
        enabled: bool = True,
    ) -> None:
        """يسجّل مهمّة دوريّة. الاسم فريد — التسجيل المكرّر يستبدل."""
        if interval_seconds <= 0:
            raise ValueError(f"interval_seconds يجب أن يكون موجباً: {name}")
        # R7: المهمّة الملفوفة بـcluster_singleton تأخذ فترتها من فاصل التسجيل نفسه.
        bind_period = getattr(fn, "bind_period", None)
        if callable(bind_period):
            bind_period(interval_seconds)
        self._tasks[name] = ScheduledTask(name, interval_seconds, fn, enabled)
        logger.info(f"مهمّة مُسجّلة: {name} كلّ {interval_seconds}ث")

    async def _run_task_loop(self, task: ScheduledTask) -> None:
        """حلقة مهمّة واحدة — معزولة: فشلها لا يؤثّر على غيرها."""
        # backoff تصاعدي عند الفشل المتكرّر (سقف ساعة)
        backoff = task.interval_seconds
        while self._running:
            if not task.enabled:
                await asyncio.sleep(task.interval_seconds)
                continue
            task.last_run_at = datetime.now(UTC).isoformat()
            task.run_count += 1
            try:
                await task.fn()
                task.last_success_at = datetime.now(UTC).isoformat()
                task.last_error = None
                backoff = task.interval_seconds  # أعِد الضبط عند النجاح
                await asyncio.sleep(task.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001 — عزل المهمّة مقصود
                task.error_count += 1
                task.last_error = f"{type(e).__name__}: {e}"
                logger.exception(f"فشل المهمّة {task.name}: {e}")
                # backoff تصاعدي بسقف ساعة
                backoff = min(backoff * 2, 3600)
                await asyncio.sleep(backoff)

    def start(self) -> None:
        """يبدأ كلّ المهامّ المسجّلة (يُستدعى في lifespan startup)."""
        if self._running:
            return
        self._running = True
        for task in self._tasks.values():
            self._handles.append(asyncio.create_task(self._run_task_loop(task)))
        logger.info(f"الجدولة بدأت — {len(self._handles)} مهمّة")

    async def stop(self) -> None:
        """يوقف كلّ المهامّ بأمان (يُستدعى في lifespan shutdown)."""
        self._running = False
        for h in self._handles:
            h.cancel()
        # انتظر إلغاءها
        if self._handles:
            await asyncio.gather(*self._handles, return_exceptions=True)
        self._handles.clear()
        logger.info("الجدولة توقّفت")

    def status(self) -> dict:
        """حالة كلّ المهامّ — للمراقبة عبر endpoint."""
        return {
            "running": self._running,
            "task_count": len(self._tasks),
            "tasks": [t.to_dict() for t in self._tasks.values()],
        }

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """تفعيل/تعطيل مهمّة وقت التشغيل."""
        if name in self._tasks:
            self._tasks[name].enabled = enabled
            return True
        return False


# مثيل وحيد للتطبيق
scheduler = Scheduler()


# ─── المهامّ الافتراضيّة (placeholders صادقة — تُربط بالمنطق الفعلي) ──
# ملاحظة صدق: هذه الدوال تُعرّف ماذا يُؤتمت ومتى. الربط بالمصادر الفعليّة
# (Open-Meteo، STAC، event_bus) يتمّ في lifespan التطبيق حيث تتوفّر الـpool
# والـhttp client. هنا نُعرّف الهيكل القابل للاختبار فقط.


def register_default_tasks(
    *,
    fetch_weather: TaskFn | None = None,
    scan_new_imagery: TaskFn | None = None,
    check_decision_freshness: TaskFn | None = None,
    run_alerts_evaluation: TaskFn | None = None,
    alerts_evaluation_interval_seconds: float = 21600,
) -> None:
    """يسجّل المهامّ الدوريّة القياسيّة لـSAHOOL.

    تُمرَّر الدوال الفعليّة من lifespan (حيث الـpool متاح). إن لم تُمرَّر
    دالّة، تُتخطّى مهمّتها — صدق: لا نسجّل مهمّة فارغة تدّعي عملاً.
    """
    if fetch_weather:
        # الطقس يوميّاً (Open-Meteo) — 24 ساعة
        scheduler.register("fetch_weather", 86400, fetch_weather)
    if scan_new_imagery:
        # فحص صور Sentinel الجديدة — كلّ 24 ساعة. الكنس اليوميّ كافٍ (دورة القمر
        # ~5 أيّام)، والحقل نفسه لا يُعاد فحصه إلّا بعد مرور 24 ساعة على وقت التقاط
        # صورته السابقة (حارس per-field في imagery_automation.scan_all).
        scheduler.register("scan_new_imagery", 86400, scan_new_imagery)
    if check_decision_freshness:
        # فحص نضارة القرارات — كلّ ساعة
        scheduler.register("check_decision_freshness", 3600, check_decision_freshness)
    if run_alerts_evaluation:
        # تقييم تنبيهات كلّ الحقول دوريّاً — الكادينس قابل للضبط (افتراض 6 ساعات).
        # يُعرَض في scheduler-status ليتأكّد المشغّل من جريانه (أو ضربه خارجيّاً).
        scheduler.register(
            "alerts_evaluation",
            alerts_evaluation_interval_seconds,
            run_alerts_evaluation,
        )
    # D1: تسليمُ نيّات إبطال كاش الراستر إلى مالكها بعد الالتزام. يُسجَّل هنا لا في
    # main.py (سقفُ أسطره ممتلئ)، ومسبحُه يُقرأ عند كلّ تكّة من main (العقد في الوحدة).
    from api.spatial_sync import register_dispatch_task

    register_dispatch_task(scheduler, cluster_singleton)
