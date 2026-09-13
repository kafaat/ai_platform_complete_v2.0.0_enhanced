"""init_retry.py — تهيئةٌ خلفيّة بمحاولات محدودة وتراجعٍ أسّيّ (local-ai-rag).

التدقيق الموحَّد 2026-09-13 (P0): كانت ``_init_models_background`` محاولةً واحدة بلا
إعادة، فتأخّرُ Qdrant/Ollama ثوانيَ عند الإقلاع يترك الخدمة 503 إلى الأبد بينما
``/readyz`` يقول «قيد التحميل». هذه الوحدة نقيّة (بلا FastAPI/LangChain) كي تُختبَر
بحقن ``sleep`` ومُهيّئ صناعيّ، وتُحدِّث قاموسَ حالةٍ يقرؤه ``/readyz`` بصدق:
``pending`` → ``retrying`` → ``ready`` | ``failed`` (مع آخر خطأ وعدد المحاولات).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

_log = logging.getLogger("local-ai-rag")


def new_state() -> dict[str, Any]:
    return {"status": "pending", "attempts": 0, "last_error": None}


def backoff_seconds(attempt: int, *, base: float, cap: float) -> float:
    """تراجعٌ أسّيّ محدود: base·2^(attempt-1) بسقف cap. نقيّ؛ attempt يبدأ من 1."""
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
            if asyncio.iscoroutine(result):
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
