"""
tests/test_circuit_breaker.py — اختبارات منطق صرف للقاطع العامّ.

حتميّة بالكامل عبر ساعة محقونة (لا sleep، لا شبكة). تغطّي آلة الحالات:
CLOSED→OPEN، حجب OPEN حتى انقضاء المهلة، الطلب الاختباريّ HALF_OPEN،
الإغلاق بالنجاح، إعادة الفتح بالفشل، تصفير العدّاد، وحقول snapshot.
"""

import pytest
from core.circuit_breaker import CircuitBreaker, CircuitState

pytestmark = pytest.mark.unit


class FakeClock:
    """ساعة محقونة قابلة للتقديم يدويّاً — حتميّة بلا انتظار حقيقيّ."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def make(**kw) -> tuple[CircuitBreaker, FakeClock]:
    clock = FakeClock()
    defaults = dict(failure_threshold=3, recovery_timeout_s=10.0, success_threshold=1)
    defaults.update(kw)
    cb = CircuitBreaker(name="t", now_fn=clock, **defaults)
    return cb, clock


def test_starts_closed_and_allows():
    cb, _ = make()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow() is True


def test_closed_to_open_after_threshold():
    cb, _ = make(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED  # عتبة لم تُبلَغ بعد
    cb.record_failure()  # الثالث
    assert cb.state == CircuitState.OPEN
    assert cb.allow() is False  # fail-fast


def test_open_blocks_until_recovery_timeout():
    cb, clock = make(failure_threshold=1, recovery_timeout_s=10.0)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow() is False
    clock.advance(9.999)
    assert cb.allow() is False  # ما زال ضمن التبريد
    clock.advance(0.001)  # بلغ ١٠ ثوانٍ تماماً
    assert cb.allow() is True  # طلب اختباريّ
    assert cb.state == CircuitState.HALF_OPEN


def test_success_in_half_open_closes():
    cb, clock = make(failure_threshold=1, recovery_timeout_s=5.0, success_threshold=1)
    cb.record_failure()
    clock.advance(5.0)
    assert cb.allow() is True
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.snapshot()["consecutive_failures"] == 0


def test_success_threshold_gt_one_in_half_open():
    cb, clock = make(failure_threshold=1, recovery_timeout_s=5.0, success_threshold=2)
    cb.record_failure()
    clock.advance(5.0)
    cb.allow()  # → HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.HALF_OPEN  # نجاح واحد لا يكفي
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_failure_in_half_open_reopens():
    cb, clock = make(failure_threshold=1, recovery_timeout_s=5.0)
    cb.record_failure()
    clock.advance(5.0)
    cb.allow()  # → HALF_OPEN
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_failure()  # سقط الاختبار
    assert cb.state == CircuitState.OPEN
    assert cb.allow() is False  # عاد التبريد من الصفر
    # لحظة الفتح أُعيد ضبطها على زمن إعادة الفتح
    clock.advance(5.0)
    assert cb.allow() is True


def test_success_resets_consecutive_failures_in_closed():
    cb, _ = make(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.snapshot()["consecutive_failures"] == 2
    cb.record_success()  # نجاح يكسر السلسلة
    assert cb.snapshot()["consecutive_failures"] == 0
    assert cb.state == CircuitState.CLOSED
    # يلزم ٣ إخفاقات جديدة كاملة للفتح
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED


def test_snapshot_fields():
    cb, clock = make(failure_threshold=2, recovery_timeout_s=10.0, success_threshold=1)
    snap = cb.snapshot()
    assert snap["name"] == "t"
    assert snap["state"] == "closed"
    assert snap["consecutive_failures"] == 0
    assert snap["opened_at"] is None
    assert snap["seconds_until_retry"] == 0.0
    assert snap["failure_threshold"] == 2
    assert snap["recovery_timeout_s"] == 10.0
    assert snap["success_threshold"] == 1

    cb.record_failure()
    cb.record_failure()  # يفتح
    snap = cb.snapshot()
    assert snap["state"] == "open"
    assert snap["opened_at"] == 0.0
    assert snap["seconds_until_retry"] == 10.0
    clock.advance(4.0)
    assert cb.snapshot()["seconds_until_retry"] == 6.0


def test_reset_returns_to_clean_closed():
    cb, _ = make(failure_threshold=1)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.snapshot()["opened_at"] is None
    assert cb.allow() is True


def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreaker(success_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreaker(recovery_timeout_s=-1)
