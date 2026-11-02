"""عنوانُ الوسيط يُطبَع مُنقَّى من الاعتماد — `NATS-BROKER-HAS-NO-AUTHENTICATION-…-01`.

**لمَ وُجِد هذا الملفّ:** إغلاقُ فتحةِ الوسيط المفتوح وضع الاعتمادَ **داخل**
`NATS_URL` — وهي القناةُ الوحيدة التي تبلغ كلَّ عميلٍ في هذه الشجرة بلا تعديل
`phase_runtime_workers.py` (ينادي ``nats.connect(nats_url)`` بلا وسائطِ اعتماد،
وتعديلُه ممنوعٌ بقرار المالك). فالعلاجُ فتح عطلاً ثانياً بيده: سطران يطبعان العنوان
في السجلّ (`main.py` عند بدء OutboxWorker · `irrigation_dispatch_relay_worker.py`
عند الاتّصال)، فكانا سيُسرِّبان كلمةَ المرور إلى سجلّاتٍ تُجمَع وتُشحَن.

**وهذا صنفٌ مقيسٌ لا متخيَّل:** «العلاجُ الظاهر يفتح عطلاً في مكانٍ آخر» — نفسُ
الصنف الذي أوجب إعلانَ المُنتِجين في حزمة الاعتماد. فالتنقيةُ تُكتَب **مرّةً واحدة**
هنا: نسختان في ملفَّين تتّفقان اليوم وتنحرفان غداً، وهو ما يقيسه هذا المستودع مراراً.

**حدُّ صدقٍ مُعلَن:** هذا يُنقّي ما **نطبعه نحن**. ولا يمنع مكتبةً أخرى أو أثرَ
استثناءٍ من طباعة العنوان الخام، ولا يُغني عن عدم تسجيل الأسرار أصلاً.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

#: ما يحلّ محلّ الاعتماد في المخرَج. صريحٌ لا نجومٌ مبهمة: القارئُ يجب أن يعرف أنّ
#: هناك اعتماداً حُذِف، لا أن يظنّ العنوانَ بلا اعتماد فيطارد عطلاً غير موجود.
PLACEHOLDER = "***:***"


def redact_broker_url(url: str | None) -> str:
    """يُعيد العنوانَ بلا اسمِ مستخدمٍ ولا كلمةِ مرور — صالحاً للطباعة.

    ``nats://u:p@host:4222`` ⇒ ``nats://***:***@host:4222``.
    والعنوانُ بلا اعتماد يعود كما هو، فلا يُقلِق قارئَه بتنقيةٍ لم تقع.
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:  # عنوانٌ مشوَّه — لا يُطبَع خاماً على كلّ حال
        return "<عنوانٌ غيرُ صالح>"
    if not parts.netloc or "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit(
        (parts.scheme, f"{PLACEHOLDER}@{host}", parts.path, parts.query, parts.fragment)
    )


def make_jetstream_publisher(nats_conn):
    """ناشرٌ **مُقِرّ** للصندوق الصادر — `OUTBOX-RELAY-MARKS-SENT-WITHOUT-JETSTREAM-ACK-01`.

    **العطلُ مقيسٌ على stack معزول:** حدثٌ نُشِر إلى موضعٍ لا يغطّيه أيُّ دفق صار صفُّه
    `sent` بـ`last_error=NULL` ومحاولةً `published` — **ولم تُخزَّن الرسالة**. والسببُ
    أنّ الناشرَ المحقون كان `nats_conn.publish`: **Core NATS**، إطلاقٌ بلا إقرار ينجح
    ما دام الاتّصالُ قائماً، وُجِد دفقٌ أم لا. فـ`sent` كانت تعني «سُلِّمت إلى المقبس»
    لا «صارت دائمة». وأُعيد الـcounterexample حيّاً على JetStream:
    `docs/evidence/outbox_jetstream_ack_live_certification.json`.

    **والعلاجُ ليس في `OutboxWorker`:** بنيتُه سليمة — ينشر ثمّ يَسِم داخل معاملة، وأيُّ
    استثناءٍ يُعيد الصفَّ `pending/failed` بـ`last_error` ومحاولةً فاشلة. فالمسارُ الصحيح
    كان **موجوداً ومعطَّلاً** لأنّ الناشرَ لا يفشل أبداً. و`js.publish` ينتظر `PubAck`
    ويرفع `NoStreamResponseError` حين لا يغطّي الموضعَ دفقٌ، فيسلك المسارَ القائم —
    **الإصلاح يُفعِّل حارساً موجوداً بدل أن يضيف ثانياً.**

    **وموضعُها هنا اختارته بوّابتان لا الراحة:** `main.py` محدودٌ بميزانيّة أسطرٍ حاجبة
    (٢٥٥٣، بلا هامش)، و`api/event_bus.py` **مسارٌ مجمَّد خلف GATE-01** — وتفويضُه
    قرارُ مالكٍ لمرّةٍ واحدة، لا يُنتزَع لأجل نقلِ دالّة. وهذا الملفُّ هو الموضعُ
    القانونيُّ لشؤون الوسيط بنصّه أعلاه: «تُكتَب مرّةً واحدة هنا». فالبوّابتان دلّتا
    على الموضع الصحيح بدل أن تُعطَّلا.
    """
    jetstream = nats_conn.jetstream()

    async def publish(subject: str, payload: bytes) -> None:
        ack = await jetstream.publish(subject, payload)
        # حزامٌ ثانٍ: عميلٌ يُرجِع `None` أو إقراراً بلا تسلسلٍ لا يُثبِت دواماً — وبلا
        # هذا الشرط يعود `sent` يعني «لم يُرفَع استثناء» لا «خُزِّنت».
        if ack is None or getattr(ack, "seq", None) in (None, 0):
            raise RuntimeError(
                f"JETSTREAM_PUBACK_MISSING: {subject} — نُشِر بلا إقرارِ تخزين، فلا يُوسَم الحدثُ `sent`."
            )

    return publish


# ─────────────── إقلاع relay الأحداث (outbox → NATS) بمهلة محدودة — R2 ───────────────
#
# العطل: ``nats.connect(max_reconnect_attempts=-1)`` لا يرفع أبداً على الاتّصال الأوّل
# (حلقة nats-py تُكرِّر بلا حدّ عند ``max_reconnect_attempts < 0``)، و``_lifespan`` في
# المنصّة ينتظره ⇒ إن غاب NATS لا يكتمل الإقلاع ولا تخدم المنصّة أيّ طلب.
#
# الإصلاح: محاولة أولى محدودة بـ``asyncio.wait_for``؛ فشلُها ⇒ إقلاع متدهور (الناشر معطّل،
# الأحداث تبقى في ``event_outbox`` الدائم) ومهمّة خلفيّة تُعيد المحاولة حتى تنجح. إعادة
# الاتّصال الأبديّة (``-1``) تبقى سلوكَ العميل **بعد** أوّل اتّصال ناجح فقط.
# الحالة تُعرَض على ``/readyz`` (``nats``) إضافةً لا تغيّر رمز الجاهزيّة: غياب الوسيط
# لا يُخرج المنصّة من الخدمة (الصندوق الصادر يحفظ الأحداث).
#
# **وموضعُه هنا للسبب نفسه الذي وضع ``make_jetstream_publisher`` أعلاه:** ``main.py``
# محدودٌ بميزانيّة أسطر، و``api/event_bus.py`` مجمَّدٌ خلف GATE-01، ووحدةٌ جديدة في
# المنصّة تكسر ميزانيّة وحداتها — وشؤونُ الوسيط تُكتَب مرّةً واحدة في هذا الملفّ.

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
