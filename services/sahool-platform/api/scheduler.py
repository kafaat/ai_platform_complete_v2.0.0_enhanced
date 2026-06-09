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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger("sahool.scheduler")

# نوع دالّة المهمّة: async بلا وسائط، تُرجع None
TaskFn = Callable[[], Awaitable[None]]


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
) -> None:
    """يسجّل المهامّ الدوريّة القياسيّة لـSAHOOL.

    تُمرَّر الدوال الفعليّة من lifespan (حيث الـpool متاح). إن لم تُمرَّر
    دالّة، تُتخطّى مهمّتها — صدق: لا نسجّل مهمّة فارغة تدّعي عملاً.
    """
    if fetch_weather:
        # الطقس يوميّاً (Open-Meteo) — 24 ساعة
        scheduler.register("fetch_weather", 86400, fetch_weather)
    if scan_new_imagery:
        # فحص صور Sentinel الجديدة — كلّ 6 ساعات (دورة القمر ~5 أيّام)
        scheduler.register("scan_new_imagery", 21600, scan_new_imagery)
    if check_decision_freshness:
        # فحص نضارة القرارات — كلّ ساعة
        scheduler.register("check_decision_freshness", 3600, check_decision_freshness)
