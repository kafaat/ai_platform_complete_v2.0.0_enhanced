"""
circuit_breaker.py — قاطع دائرة بسيط لمكالمات MCP (مرونة حقيقيّة).

يعالج فجوة المراجعة: "لا circuit breaker". يمنع إغراق خدمة فاشلة بالطلبات:
- CLOSED: الطلبات تمرّ طبيعيّاً. عند تجاوز عتبة الفشل → OPEN.
- OPEN: الطلبات تُرفض فوراً (fail-fast) دون إزعاج الخدمة الفاشلة.
- HALF_OPEN: بعد مهلة، يُسمح بطلب اختباري واحد. نجاح → CLOSED، فشل → OPEN.

منطق صرف (لا بنية تحتيّة): قابل للاختبار بالكامل بلا شبكة/خدمات.
لكلّ خدمة MCP قاطعها المستقلّ (عزل الفشل).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "closed"  # طبيعي
    OPEN = "open"  # مفتوح (يرفض) بعد فشل متكرّر
    HALF_OPEN = "half_open"  # اختبار التعافي


class CircuitOpenError(Exception):
    """يُرفع حين القاطع مفتوح (الخدمة تُعتبر متعطّلة)."""


@dataclass
class CircuitBreaker:
    """قاطع دائرة لخدمة واحدة.

    failure_threshold: عدد الإخفاقات المتتالية قبل الفتح.
    recovery_timeout: ثوانٍ قبل السماح بطلب اختباري (HALF_OPEN).
    success_threshold: نجاحات في HALF_OPEN قبل العودة لـCLOSED.
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    success_threshold: int = 2

    state: CircuitState = CircuitState.CLOSED
    _failures: int = 0
    _successes: int = 0
    _opened_at: float = 0.0

    def _now(self) -> float:
        return time.monotonic()

    def allow_request(self) -> bool:
        """هل يُسمح بالطلب الآن؟ ينقل OPEN→HALF_OPEN عند انتهاء المهلة."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self._now() - self._opened_at >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self._successes = 0
                return True  # طلب اختباري واحد
            return False  # ما زال مفتوحاً → fail-fast
        # HALF_OPEN: نسمح بطلبات الاختبار
        return True

    def record_success(self) -> None:
        """يُسجّل نجاحاً (يُعيد الإغلاق التدريجي في HALF_OPEN)."""
        if self.state == CircuitState.HALF_OPEN:
            self._successes += 1
            if self._successes >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self._failures = 0
        elif self.state == CircuitState.CLOSED:
            self._failures = 0  # صفّر العدّاد عند النجاح

    def record_failure(self) -> None:
        """يُسجّل فشلاً (يفتح القاطع عند تجاوز العتبة)."""
        if self.state == CircuitState.HALF_OPEN:
            # فشل أثناء الاختبار → ارجع لـOPEN فوراً
            self.state = CircuitState.OPEN
            self._opened_at = self._now()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self._opened_at = self._now()

    def status(self) -> dict:
        return {"name": self.name, "state": self.state.value, "failures": self._failures}


class CircuitBreakerRegistry:
    """سجلّ قواطع — قاطع مستقلّ لكلّ خدمة MCP (عزل الفشل)."""

    def __init__(self, **defaults):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._defaults = defaults

    def get(self, name: str) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name=name, **self._defaults)
        return self._breakers[name]

    def status_all(self) -> list:
        return [b.status() for b in self._breakers.values()]


# سجلّ مشترك لمكالمات MCP (عتبات محافظة)
mcp_breakers = CircuitBreakerRegistry(
    failure_threshold=5, recovery_timeout=30.0, success_threshold=2
)
