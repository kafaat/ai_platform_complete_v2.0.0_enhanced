"""
core/circuit_breaker.py — قاطع دائرة عامّ ومنطق صرف لـsahool-platform.

يعالج فجوة المرونة: استدعاء خدمة خارجيّة متعطّلة مراراً (مثل Open-Meteo) يُهدر
المهلات ويُغرِق المصدر الفاشل. القاطع يفشل سريعاً (fail-fast) عند تكرار الفشل
ويتيح تدهوراً رشيقاً (graceful degradation) بدل مطرقة على خدمة ساقطة.

آلة الحالات (state machine):
  ┌──────────────────────────────────────────────────────────────────┐
  │ CLOSED   : الطلبات تمرّ طبيعيّاً. كلّ فشل متتالٍ يزيد العدّاد؛ عند     │
  │            بلوغ failure_threshold ← الانتقال إلى OPEN. أيّ نجاح       │
  │            يُصفّر عدّاد الإخفاقات المتتالية.                          │
  │ OPEN     : الطلبات تُرفض فوراً (allow()→False) دون لمس المصدر.        │
  │            بعد مرور recovery_timeout_s من لحظة الفتح، يَسمح allow()    │
  │            بطلب اختباريّ واحد ناقلاً الحالة إلى HALF_OPEN.            │
  │ HALF_OPEN: طلب/طلبات اختبار تعافٍ. تتابُع success_threshold نجاحاً    │
  │            ← العودة إلى CLOSED (تصفير العدّادات). أيّ فشل واحد         │
  │            ← العودة الفوريّة إلى OPEN (مع إعادة ضبط لحظة الفتح).      │
  └──────────────────────────────────────────────────────────────────┘

منطق صرف بلا بنية تحتيّة (stdlib فقط): قابل للاختبار بالكامل بلا شبكة/خدمات.
الزمن محقون (now_fn) فتُصبح الانتقالات حتميّة بلا sleep في الاختبارات.

أمانة: snapshot يعكس العدّادات الحقيقيّة (الحالة، الإخفاقات المتتالية، لحظة
الفتح…) بلا تلفيق — مجرّد إسقاط للحالة الداخليّة الفعليّة.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"  # طبيعي — الطلبات تمرّ
    OPEN = "open"  # مفتوح — يرفض سريعاً بعد فشل متكرّر
    HALF_OPEN = "half_open"  # اختبار التعافي بطلب واحد


class CircuitBreaker:
    """قاطع دائرة لمصدر واحد (مثل Open-Meteo).

    المعاملات:
      name: اسم تعريفيّ للرصد/السجلّ.
      failure_threshold: عدد الإخفاقات المتتالية في CLOSED قبل الفتح.
      recovery_timeout_s: ثوانٍ تبريد قبل السماح بطلب اختباريّ (OPEN→HALF_OPEN).
      success_threshold: نجاحات متتالية في HALF_OPEN قبل العودة لـCLOSED.
      now_fn: مصدر الزمن (افتراضاً time.monotonic) — محقون للاختبار الحتميّ.

    monotonic مقصود: لا يتأثّر بتعديل ساعة النظام، فالمهلة تبقى صحيحة.
    """

    def __init__(
        self,
        name: str = "default",
        *,
        failure_threshold: int = 5,
        recovery_timeout_s: float = 30.0,
        success_threshold: int = 1,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold يجب أن يكون ≥ 1")
        if success_threshold < 1:
            raise ValueError("success_threshold يجب أن يكون ≥ 1")
        if recovery_timeout_s < 0:
            raise ValueError("recovery_timeout_s يجب أن يكون ≥ 0")

        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = float(recovery_timeout_s)
        self.success_threshold = success_threshold
        self._now = now_fn

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._opened_at: float | None = None

    # ─── الحالة ────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        """الحالة المنطقيّة الحاليّة.

        ملاحظة: القراءة لا تُحدِث انتقالاً — انتقال OPEN→HALF_OPEN يقع داخل
        allow() (نقطة القرار الوحيدة) فيبقى الانتقال صريحاً ومحدّد التوقيت.
        """
        return self._state

    def _cooldown_elapsed(self) -> bool:
        """هل انقضت مهلة التبريد منذ لحظة الفتح؟ (آمن إن لم يكن مفتوحاً)."""
        if self._opened_at is None:
            return True
        return (self._now() - self._opened_at) >= self.recovery_timeout_s

    # ─── البوّابة ──────────────────────────────────────────────────

    def allow(self) -> bool:
        """هل يُسمح بطلب الآن؟

        CLOSED    → True.
        OPEN      → True فقط إن انقضت مهلة التبريد (مع نقل الحالة لـHALF_OPEN
                    وفتح نافذة طلب اختباريّ)، وإلّا False (fail-fast).
        HALF_OPEN → True (نسمح بطلبات الاختبار؛ نتيجتها تُحسم عبر record_*).
        """
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if self._cooldown_elapsed():
                self._state = CircuitState.HALF_OPEN
                self._consecutive_successes = 0
                return True  # طلب اختباريّ
            return False  # ما زال مفتوحاً → رفض سريع
        # HALF_OPEN
        return True

    # ─── تسجيل النتائج ─────────────────────────────────────────────

    def record_success(self) -> None:
        """يُسجّل نجاحاً.

        HALF_OPEN: تتابُع success_threshold نجاحاً ← CLOSED.
        CLOSED   : يُصفّر عدّاد الإخفاقات المتتالية (نجاح يكسر سلسلة الفشل).
        OPEN     : لا أثر (لا ينبغي أن يُستدعى أثناء الفتح؛ نتركه آمناً).
        """
        if self._state == CircuitState.HALF_OPEN:
            self._consecutive_successes += 1
            if self._consecutive_successes >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._consecutive_failures = 0
                self._consecutive_successes = 0
                self._opened_at = None
        elif self._state == CircuitState.CLOSED:
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        """يُسجّل فشلاً.

        HALF_OPEN: أيّ فشل ← العودة الفوريّة لـOPEN (طلب الاختبار سقط).
        CLOSED   : يزيد العدّاد؛ عند بلوغ failure_threshold ← OPEN.
        """
        if self._state == CircuitState.HALF_OPEN:
            self._open()
            return
        if self._state == CircuitState.CLOSED:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._open()

    def _open(self) -> None:
        """ينقل إلى OPEN ويختم لحظة الفتح (بدء عدّ التبريد)."""
        self._state = CircuitState.OPEN
        self._opened_at = self._now()
        self._consecutive_successes = 0

    # ─── أدوات إضافيّة ─────────────────────────────────────────────

    def reset(self) -> None:
        """يُعيد القاطع إلى CLOSED نظيفاً (مفيد للاختبار/الإدارة)."""
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._opened_at = None

    def snapshot(self) -> dict:
        """إسقاط رصديّ صادق للحالة الداخليّة (لا تلفيق).

        opened_at: قيمة now_fn المختومة عند آخر فتح (None إن لم يُفتح).
        seconds_until_retry: ما تبقّى من التبريد قبل السماح بطلب اختباريّ
          (0.0 إن جاهز أو غير مفتوح) — مشتقّ من الزمن الحاليّ، لا مخزّن.
        """
        now = self._now()
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            remaining = self.recovery_timeout_s - (now - self._opened_at)
            seconds_until_retry = max(0.0, remaining)
        else:
            seconds_until_retry = 0.0
        return {
            "name": self.name,
            "state": self._state.value,
            "consecutive_failures": self._consecutive_failures,
            "consecutive_successes": self._consecutive_successes,
            "opened_at": self._opened_at,
            "seconds_until_retry": round(seconds_until_retry, 6),
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_s": self.recovery_timeout_s,
            "success_threshold": self.success_threshold,
        }
