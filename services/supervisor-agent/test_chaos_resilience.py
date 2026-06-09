#!/usr/bin/env python3
"""
test_chaos_resilience.py — اختبارات السلوك تحت الفشل (chaos/failure injection).

تحقن أعطالاً حقيقيّة وتتحقّق من تعافي النظام — offline، بلا بنية حيّة.
تكمّل اختبارات circuit_breaker المنطقيّة بسيناريوهات فشل واقعيّة:
  • انقطاع خدمة متتالٍ → القاطع يفتح (fail-fast)
  • تعافي بعد المهلة → half-open → closed
  • عاصفة طلبات أثناء الانقطاع → لا انهيار
  • فشل خدمة واحدة لا يُسقط البقيّة (عزل)
  • تذبذب (flapping) → القاطع يستقرّ

التشغيل:
  python3 services/supervisor-agent/test_chaos_resilience.py
  أو: pytest services/supervisor-agent/test_chaos_resilience.py -v
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from circuit_breaker import CircuitBreaker, CircuitBreakerRegistry, CircuitState  # noqa: E402


# ── سيناريو ١: انقطاع خدمة متتالٍ → fail-fast ──
def test_sustained_outage_trips_breaker():
    """خدمة منقطعة تماماً: بعد العتبة، القاطع يرفض فوراً (لا انتظار)."""
    cb = CircuitBreaker(name="weather", failure_threshold=5)
    # حقن: 5 فشل متتالٍ (انقطاع تامّ)
    for _ in range(5):
        assert cb.allow_request() is True
        cb.record_failure()
    # الآن القاطع مفتوح → يرفض فوراً (fail-fast، يحمي من retry storm)
    assert cb.state == CircuitState.OPEN
    rejected = sum(1 for _ in range(100) if not cb.allow_request())
    assert rejected == 100, "القاطع المفتوح يجب أن يرفض كلّ الطلبات فوراً"


# ── سيناريو ٢: تعافي بعد المهلة ──
def test_recovery_after_outage():
    """بعد انتهاء الانقطاع: half-open ثمّ closed عند النجاح."""
    cb = CircuitBreaker(name="mcp", failure_threshold=3, recovery_timeout=0.05, success_threshold=2)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    # الخدمة عادت — ننتظر المهلة
    time.sleep(0.06)
    assert cb.allow_request() is True  # يسمح بطلب اختبار
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    cb.record_success()  # نجاحان → تعافى
    assert cb.state == CircuitState.CLOSED


# ── سيناريو ٣: عاصفة طلبات أثناء الانقطاع ──
def test_request_storm_during_outage():
    """1000 طلب أثناء الانقطاع → لا استثناء، رفض نظيف (لا retry storm)."""
    cb = CircuitBreaker(name="market", failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    # عاصفة: 1000 محاولة — يجب أن تُرفض بهدوء بلا انهيار
    allowed = 0
    for _ in range(1000):
        if cb.allow_request():
            allowed += 1
            cb.record_failure()
    # القاطع مفتوح يمنع الأغلبيّة (يسمح فقط بمحاولات نصف-مفتوح النادرة)
    assert allowed < 50, "القاطع يجب أن يمنع عاصفة الطلبات"


# ── سيناريو ٤: عزل الأعطال (failure isolation) ──
def test_failure_isolation_across_services():
    """انقطاع خدمة واحدة لا يُسقط بقيّة الخدمات (عزل عبر registry)."""
    reg = CircuitBreakerRegistry(failure_threshold=3)
    weather = reg.get("weather")
    market = reg.get("market")
    wofost = reg.get("wofost")
    # weather تنهار تماماً
    for _ in range(3):
        weather.record_failure()
    assert weather.state == CircuitState.OPEN
    # البقيّة سليمة — لا تتأثّر
    assert market.state == CircuitState.CLOSED
    assert wofost.state == CircuitState.CLOSED
    assert market.allow_request() is True
    assert wofost.allow_request() is True


# ── سيناريو ٥: تذبذب الخدمة (flapping) ──
def test_flapping_service_stabilizes():
    """خدمة متذبذبة (نجاح/فشل متناوب) لا تُبقي القاطع يرفرف بلا استقرار."""
    cb = CircuitBreaker(
        name="sentinel", failure_threshold=3, recovery_timeout=0.02, success_threshold=2
    )
    # تذبذب: فشل-فشل-فشل (يفتح) ثمّ نصف-مفتوح-فشل (يعيد الفتح)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.03)
    cb.allow_request()  # half-open
    cb.record_failure()  # فشل في الاختبار → يعيد الفتح فوراً
    assert cb.state == CircuitState.OPEN, "فشل نصف-مفتوح يجب أن يعيد الفتح"


# ── سيناريو ٦: انقطاع جزئي ثمّ تعافٍ كامل ──
def test_partial_failure_then_full_recovery():
    """فشل دون العتبة ثمّ نجاح → يبقى مغلقاً (لا فتح مبكّر)."""
    cb = CircuitBreaker(name="db", failure_threshold=5)
    # 4 فشل (دون العتبة 5)
    for _ in range(4):
        cb.record_failure()
    assert cb.state == CircuitState.CLOSED, "دون العتبة يجب أن يبقى مغلقاً"
    # نجاح → يصفّر العدّاد
    cb.record_success()
    # 4 فشل أخرى — لا يفتح (العدّاد صُفِّر)
    for _ in range(4):
        cb.record_failure()
    assert cb.state == CircuitState.CLOSED


# ── سيناريو ٧: أحداث مكرّرة (idempotency-style فحص منطقي) ──
def test_duplicate_failures_dont_double_count_after_open():
    """بعد الفتح، الفشل الإضافي لا يكسر الحالة (ثبات)."""
    cb = CircuitBreaker(name="queue", failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    # فشل إضافي بعد الفتح — يبقى مفتوحاً، لا استثناء
    for _ in range(10):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    s = cb.status()
    assert s["state"] == "open"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  \u2713 {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            print(f"  \u2717 {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} \u0646\u062c\u0627\u062d")
    sys.exit(0 if passed == len(fns) else 1)
