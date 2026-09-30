"""init_retry.py — تهيئةٌ خلفيّة بمحاولات محدودة وتراجعٍ أسّيّ (local-ai-rag).

التدقيق الموحَّد 2026-09-13 (P0): كانت ``_init_models_background`` محاولةً واحدة بلا
إعادة، فتأخّرُ Qdrant/Ollama ثوانيَ عند الإقلاع يترك الخدمة 503 إلى الأبد بينما
``/readyz`` يقول «قيد التحميل». هذه الوحدة نقيّة (بلا FastAPI/LangChain) كي تُختبَر
بحقن ``sleep`` ومُهيّئ صناعيّ، وتُحدِّث قاموسَ حالةٍ يقرؤه ``/readyz`` بصدق:
``pending`` → ``retrying`` → ``ready`` | ``failed`` (مع آخر خطأ وعدد المحاولات).

تدقيقُ التشغيل الحيّ 2026-09-29 (آلةٌ نظيفة): استُنفِدت المحاولاتُ الستّ والنماذجُ لم تُسحَب
بعد، فصارت ``failed`` **نهائيّةً** — لا إعادةَ حتّى إعادةِ تشغيل الحاوية — وآخرُ خطأٍ عامٌّ
(«Ollama not available») لا يقول أيُّ تبعيّةٍ غابت. فصار أمران:

* ``keep_retrying=True``: بعد ميزانية الإقلاع تبقى ``failed`` (صادقة: الميزانيةُ استُنفِدت) لكنّ
  الإعادةَ تستمرّ بتراجعٍ **مسقوف** (``cap`` وأرضيّة ``PERSISTENT_RETRY_FLOOR_S``) فتتعافى الخدمةُ
  حين تظهر التبعيّة (بذرٌ أُعيد، نموذجٌ سُحِب) بلا إعادة تشغيل.
* ``InitNotReady(reason, detail)``: سببٌ **مُسمّى** (``model_missing`` · ``collection_missing`` …)
  يُحفَظ في ``state["reason"]`` ويقرؤه ``/readyz`` كما هو.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
from collections.abc import Awaitable, Callable
from typing import Any

_log = logging.getLogger("local-ai-rag")

#: أدنى فاصلٍ بين محاولاتِ ما بعد الميزانية. تراجعٌ صفريّ مسموحٌ داخل الميزانية (``base=0``)،
#: لكنّه بلا نهايةٍ للمحاولات يصير حلقةً ساخنةً أبديّة — فالأرضيّةُ تُفرَض هنا وحدَه.
PERSISTENT_RETRY_FLOOR_S = 5.0


class InitNotReady(RuntimeError):
    """سببُ عدمِ الجاهزيّة **مُسمّى**: ``reason`` رمزٌ ثابت يقرؤه ``/readyz``، و``detail`` ما قِيس."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def reason_of(exc: BaseException) -> str:
    """الرمزُ من ``InitNotReady`` وحدَه — ``URLError.reason`` وأشباهُه نصٌّ حرّ لا رمز."""
    return exc.reason if isinstance(exc, InitNotReady) else "unclassified"


def new_state() -> dict[str, Any]:
    return {
        "status": "pending",
        "attempts": 0,
        "last_error": None,
        "reason": None,
        "next_retry_s": None,
    }


def non_negative_float(
    raw: str | None, default: float, *, name: str, log: logging.Logger | None = None
) -> float:
    """يقرأ قيمةَ إعدادٍ عشريّةً **منتهيةً غير سالبة** وإلّا يُعيد الافتراضيّ مع تحذير.

    Copilot على #1001: قيمةٌ سالبة لـ``RAG_INIT_BACKOFF_*`` كانت تمرّ فيُعيد التراجعُ زمناً
    سالباً و``asyncio.sleep`` يعامله كصفر — حلقةُ إعادة ضيّقة بدل تراجعٍ محدود. الحدُّ يُفرَض
    عند حدود الإعداد (هنا) لا في منتصف حلقة الإعادة.
    """
    if raw is None or not str(raw).strip():
        return float(default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = float("nan")
    if not math.isfinite(value) or value < 0:
        (log or _log).warning("%s=%r غير صالح (يلزم عددٌ منتهٍ ≥ 0) — استُعمِل %s", name, raw, default)
        return float(default)
    return value


def int_or_default(
    raw: str | None, default: int, *, name: str, log: logging.Logger | None = None
) -> int:
    """يقرأ قيمةَ إعدادٍ صحيحةً وإلّا يُعيد الافتراضيّ مع تحذير — لا يُسقِط الوحدة عند الاستيراد.

    Copilot على #1001: تحويلُ سقف المحاولات بـ``int(...)`` مباشرةً على نصّ غير رقميّ كان يرفع
    عند استيراد ``main`` فلا تبلغ الخدمةُ ``/readyz`` ولا حلقةَ الإعادة أصلاً. التقييدُ الأدنى
    (``max(1, …)``) يبقى مسؤوليّةَ المُنادي كما هو موثَّق هناك.
    """
    if raw is None or not str(raw).strip():
        return int(default)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        (log or _log).warning("%s=%r غير صالح (يلزم عددٌ صحيح) — استُعمِل %s", name, raw, default)
        return int(default)


def backoff_seconds(attempt: int, *, base: float, cap: float) -> float:
    """تراجعٌ أسّيّ محدود: base·2^(attempt-1) بسقف cap. نقيّ؛ attempt يبدأ من 1.

    يرفض قاعدةً أو سقفاً سالبَين/غيرَ منتهيَين (يفشل مغلقاً) — التطبيعُ مسؤوليّةُ حدود الإعداد.
    """
    if not (math.isfinite(base) and math.isfinite(cap)) or base < 0 or cap < 0:
        raise ValueError(f"backoff base/cap must be finite and >= 0 (got {base!r}, {cap!r})")
    # مضاعفةٌ محدودة بدل ``2 ** (attempt-1)`` المفتوح: سقفُ محاولاتٍ ضخم كان يبني عدداً صحيحاً
    # هائلاً قبل ``min`` (تعليقٌ/MemoryError عند جدولة الإعادة؛ Copilot على #1001). الحلقة تتوقّف
    # حين يبلغ التأخيرُ السقفَ — عددُ الدورات ≤ log2(cap/base).
    delay = float(base)
    if delay <= 0:
        return 0.0
    for _ in range(max(0, attempt - 1)):
        if delay >= cap:
            break
        delay *= 2
    return float(min(cap, delay))


async def run_init_with_retry(
    init_fn: Callable[[], Any | Awaitable[Any]],
    state: dict[str, Any],
    *,
    max_attempts: int,
    base: float,
    cap: float,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    log: logging.Logger | None = None,
    keep_retrying: bool = False,
) -> dict[str, Any]:
    """يُشغّل ``init_fn`` (متزامنة أو async) حتّى تنجح أو تُستنفَد المحاولات.

    ``state`` يُحدَّث في مكانه (يقرؤه /readyz)؛ ``ready`` عند النجاح، ``retrying`` بين
    المحاولات، ``failed`` بعد الاستنفاد مع آخر خطأ وسببه المُسمّى. ``sleep`` قابل للحقن للاختبار.

    ``keep_retrying=False`` (الافتراضيّ): الاستنفادُ نهاية. ``True``: الاستنفادُ يُعلَن ``failed`` ثمّ
    تستمرّ الإعادةُ بفاصلٍ مسقوف (لا يقلّ عن ``PERSISTENT_RETRY_FLOOR_S``) حتّى تنجح أو تُلغى
    المهمّة — ``next_retry_s`` يقول متى، فـ«فشلت» لا تعني «توقّفت عن المحاولة» ولا العكس.
    """
    logger = log or _log
    do_sleep = asyncio.sleep if sleep is None else sleep
    attempts = max(1, int(max_attempts))
    attempt = 0
    while True:
        attempt += 1
        state["attempts"] = attempt
        try:
            result = init_fn()
            # أيُّ awaitable (coroutine/Task/Future) يُنتظَر — لا coroutine وحدَه (Copilot على #1001).
            if inspect.isawaitable(result):
                await result
            state["status"] = "ready"
            state["last_error"] = None
            state["reason"] = None
            state["next_retry_s"] = None
            return dict(state)
        except Exception as exc:  # noqa: BLE001 — الفشل يُسجَّل ويُعاد بحدود
            state["last_error"] = f"{type(exc).__name__}: {exc}"
            state["reason"] = reason_of(exc)
            if attempt >= attempts:
                state["status"] = "failed"
                if not keep_retrying:
                    state["next_retry_s"] = None
                    logger.error(
                        "فشلت التهيئة الخلفيّة نهائيّاً بعد %d محاولات: %s",
                        attempt,
                        state["last_error"],
                    )
                    return dict(state)
                delay = max(backoff_seconds(attempt, base=base, cap=cap), PERSISTENT_RETRY_FLOOR_S)
                (logger.error if attempt == attempts else logger.warning)(
                    "استُنفِدت ميزانيةُ الإقلاع (%d محاولات) [%s] %s — الإعادةُ مستمرّة كلّ %.0fث",
                    attempts,
                    state["reason"],
                    state["last_error"],
                    delay,
                )
            else:
                state["status"] = "retrying"
                delay = backoff_seconds(attempt, base=base, cap=cap)
                logger.warning(
                    "فشلت محاولة التهيئة %d/%d (%s) — إعادة بعد %.0fث",
                    attempt,
                    attempts,
                    state["last_error"],
                    delay,
                )
            state["next_retry_s"] = delay
            await do_sleep(delay)
