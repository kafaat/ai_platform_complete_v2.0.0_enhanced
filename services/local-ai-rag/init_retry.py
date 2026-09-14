"""init_retry.py — تهيئةٌ خلفيّة بمحاولات محدودة وتراجعٍ أسّيّ (local-ai-rag).

التدقيق الموحَّد 2026-09-13 (P0): كانت ``_init_models_background`` محاولةً واحدة بلا
إعادة، فتأخّرُ Qdrant/Ollama ثوانيَ عند الإقلاع يترك الخدمة 503 إلى الأبد بينما
``/readyz`` يقول «قيد التحميل». هذه الوحدة نقيّة (بلا FastAPI/LangChain) كي تُختبَر
بحقن ``sleep`` ومُهيّئ صناعيّ، وتُحدِّث قاموسَ حالةٍ يقرؤه ``/readyz`` بصدق:
``pending`` → ``retrying`` → ``ready`` | ``failed`` (مع آخر خطأ وعدد المحاولات).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
from collections.abc import Awaitable, Callable
from typing import Any

_log = logging.getLogger("local-ai-rag")


def new_state() -> dict[str, Any]:
    return {"status": "pending", "attempts": 0, "last_error": None}


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


def backoff_seconds(attempt: int, *, base: float, cap: float) -> float:
    """تراجعٌ أسّيّ محدود: base·2^(attempt-1) بسقف cap. نقيّ؛ attempt يبدأ من 1.

    يرفض قاعدةً أو سقفاً سالبَين/غيرَ منتهيَين (يفشل مغلقاً) — التطبيعُ مسؤوليّةُ حدود الإعداد.
    """
    if not (math.isfinite(base) and math.isfinite(cap)) or base < 0 or cap < 0:
        raise ValueError(f"backoff base/cap must be finite and >= 0 (got {base!r}, {cap!r})")
    return float(min(cap, base * (2 ** max(0, attempt - 1))))


async def run_init_with_retry(
    init_fn: Callable[[], Any | Awaitable[Any]],
    state: dict[str, Any],
    *,
    max_attempts: int,
    base: float,
    cap: float,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    log: logging.Logger | None = None,
) -> dict[str, Any]:
    """يُشغّل ``init_fn`` (متزامنة أو async) حتّى تنجح أو تُستنفَد المحاولات.

    ``state`` يُحدَّث في مكانه (يقرؤه /readyz)؛ ``ready`` عند النجاح، ``retrying`` بين
    المحاولات، ``failed`` بعد الاستنفاد مع آخر خطأ. ``sleep`` قابل للحقن للاختبار.
    """
    logger = log or _log
    do_sleep = asyncio.sleep if sleep is None else sleep
    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        state["attempts"] = attempt
        try:
            result = init_fn()
            # أيُّ awaitable (coroutine/Task/Future) يُنتظَر — لا coroutine وحدَه (Copilot على #1001).
            if inspect.isawaitable(result):
                await result
            state["status"] = "ready"
            state["last_error"] = None
            return dict(state)
        except Exception as exc:  # noqa: BLE001 — الفشل يُسجَّل ويُعاد بحدود
            state["last_error"] = f"{type(exc).__name__}: {exc}"
            if attempt >= attempts:
                state["status"] = "failed"
                logger.error(
                    "فشلت التهيئة الخلفيّة نهائيّاً بعد %d محاولات: %s",
                    attempt,
                    state["last_error"],
                )
                return dict(state)
            state["status"] = "retrying"
            delay = backoff_seconds(attempt, base=base, cap=cap)
            logger.warning(
                "فشلت محاولة التهيئة %d/%d (%s) — إعادة بعد %.0fث",
                attempt,
                attempts,
                state["last_error"],
                delay,
            )
            await do_sleep(delay)
    return dict(state)
