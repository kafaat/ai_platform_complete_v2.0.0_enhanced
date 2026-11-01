"""إقلاع relay الأحداث (outbox → NATS) بمهلة محدودة للاتّصال الأوّل — R2.

العطل: ``nats.connect(max_reconnect_attempts=-1)`` لا يرفع أبداً على الاتّصال الأوّل
(حلقة nats-py تُكرِّر بلا حدّ عند ``max_reconnect_attempts < 0``)، و``_lifespan`` ينتظره
⇒ إن غاب NATS لا يكتمل الإقلاع ولا تخدم المنصّة أيّ طلب.

الإصلاح: محاولة أولى محدودة بـ``asyncio.wait_for``؛ فشلُها ⇒ إقلاع متدهور (الناشر معطّل،
الأحداث تبقى في ``event_outbox`` الدائم) ومهمّة خلفيّة تُعيد المحاولة حتى تنجح. إعادة
الاتّصال الأبديّة (``-1``) تبقى سلوكَ العميل **بعد** أوّل اتّصال ناجح فقط.
الحالة تُعرَض على ``/readyz`` (``nats``) إضافةً لا تغيّر رمز الجاهزيّة: غياب الوسيط
لا يُخرج المنصّة من الخدمة (الصندوق الصادر يحفظ الأحداث).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

INITIAL_CONNECT_TIMEOUT_ENV = "NATS_INITIAL_CONNECT_TIMEOUT_SECONDS"
RETRY_INTERVAL_ENV = "NATS_CONNECT_RETRY_SECONDS"
DEFAULT_INITIAL_CONNECT_TIMEOUT = 10.0
DEFAULT_RETRY_INTERVAL = 30.0

Connect = Callable[[], Awaitable[Any]]
OnConnected = Callable[[Any], Awaitable[None]]


def _env_seconds(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


class NatsRelayState:
    """حالة relay المنصّة كما تقرؤها ``/readyz``: disabled | degraded | up | reconnecting."""

    def __init__(self) -> None:
        self.conn: Any = None
        self.phase = "disabled"
        self.last_error: str | None = None
        self.retry_task: asyncio.Task | None = None

    @property
    def status(self) -> str:
        if self.conn is None:
            return self.phase
        return "up" if getattr(self.conn, "is_connected", True) else "reconnecting"

    async def reset(self) -> None:
        """يُلغي إعادة المحاولة الخلفيّة (قبل إيقاف العامل) ويُعيد الحالة إلى disabled."""
        task, self.retry_task = self.retry_task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self.conn, self.phase, self.last_error = None, "disabled", None


NATS_RELAY = NatsRelayState()


async def _connect_once(connect: Connect, on_connected: OnConnected, timeout_s: float) -> None:
    conn = await asyncio.wait_for(connect(), timeout=timeout_s)
    try:
        await on_connected(conn)
    except Exception:
        try:
            await conn.close()
        except Exception as close_err:  # noqa: BLE001 — الخطأ الأصليّ هو المُرفَع
            logger.debug("NATS close بعد فشل التهيئة: %s", type(close_err).__name__)
        raise
    NATS_RELAY.conn, NATS_RELAY.last_error = conn, None


async def _retry_until_connected(
    connect: Connect, on_connected: OnConnected, label: str, timeout_s: float, retry_s: float
) -> None:
    while True:
        await asyncio.sleep(retry_s)
        try:
            await _connect_once(connect, on_connected, timeout_s)
        except Exception as e:  # noqa: BLE001 — الوسيط ما زال غائباً: تبقى متدهورة وتُعيد
            NATS_RELAY.last_error = type(e).__name__
            logger.warning(
                "NATS %s ما زال غير متاح (%s) — إعادة بعد %ss", label, type(e).__name__, retry_s
            )
            continue
        logger.info("✓ NATS %s متاح بعد تدهور — relay الأحداث استُؤنف", label)
        return


async def start_relay(
    connect: Connect,
    on_connected: OnConnected,
    *,
    label: str,
    timeout_s: float | None = None,
    retry_s: float | None = None,
) -> bool:
    """محاولة أولى محدودة؛ فشلُها ⇒ متدهور + إعادة خلفيّة. يُرجِع: هل اتّصل الآن."""
    timeout_s = timeout_s or _env_seconds(
        INITIAL_CONNECT_TIMEOUT_ENV, DEFAULT_INITIAL_CONNECT_TIMEOUT
    )
    retry_s = retry_s or _env_seconds(RETRY_INTERVAL_ENV, DEFAULT_RETRY_INTERVAL)
    await NATS_RELAY.reset()
    NATS_RELAY.phase = "connecting"
    try:
        await _connect_once(connect, on_connected, timeout_s)
        return True
    except Exception as e:  # noqa: BLE001 — غياب NATS لا يحجب الإقلاع
        NATS_RELAY.phase, NATS_RELAY.last_error = "degraded", type(e).__name__
        logger.warning(
            "NATS %s غير متاح خلال %ss (%s) — إقلاع متدهور: الأحداث تبقى في outbox "
            "وإعادة المحاولة كلّ %ss في الخلفيّة",
            label,
            timeout_s,
            type(e).__name__,
            retry_s,
        )
    NATS_RELAY.retry_task = asyncio.create_task(
        _retry_until_connected(connect, on_connected, label, timeout_s, retry_s)
    )
    return False
