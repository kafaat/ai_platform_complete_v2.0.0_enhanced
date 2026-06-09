#!/usr/bin/env python3
"""
اختبارات وحدة لقاطع الدائرة — تعمل offline بلا خدمة حيّة.
ترفع تغطية supervisor-agent (كانت 0% — فجوة المراجعة الحرجة).
"""

import time

from circuit_breaker import CircuitBreaker, CircuitBreakerRegistry, CircuitOpenError, CircuitState


def test_starts_closed():
    cb = CircuitBreaker(name="t")
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_opens_after_threshold():
    cb = CircuitBreaker(name="t", failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False  # fail-fast


def test_success_resets_failures_when_closed():
    cb = CircuitBreaker(name="t", failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()  # يصفّر العدّاد
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED  # لم يصل للعتبة


def test_half_open_after_timeout():
    cb = CircuitBreaker(name="t", failure_threshold=2, recovery_timeout=0.05)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.06)
    assert cb.allow_request() is True  # ينقل لـHALF_OPEN
    assert cb.state == CircuitState.HALF_OPEN


def test_recovers_to_closed():
    cb = CircuitBreaker(name="t", failure_threshold=2, recovery_timeout=0.05, success_threshold=2)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.06)
    cb.allow_request()  # HALF_OPEN
    cb.record_success()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED  # تعافى


def test_half_open_failure_reopens():
    cb = CircuitBreaker(name="t", failure_threshold=2, recovery_timeout=0.05)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.06)
    cb.allow_request()  # HALF_OPEN
    cb.record_failure()  # فشل أثناء الاختبار
    assert cb.state == CircuitState.OPEN


def test_registry_isolates_services():
    reg = CircuitBreakerRegistry(failure_threshold=2)
    weather = reg.get("weather")
    soil = reg.get("soil")
    assert weather is not soil  # قاطع مستقلّ لكلّ خدمة
    assert reg.get("weather") is weather  # نفس الكائن عند الاستدعاء الثاني
    # فشل weather لا يؤثّر على soil
    weather.record_failure()
    weather.record_failure()
    assert weather.state == CircuitState.OPEN
    assert soil.state == CircuitState.CLOSED


def test_status_reporting():
    cb = CircuitBreaker(name="weather-mcp", failure_threshold=5)
    cb.record_failure()
    s = cb.status()
    assert s["name"] == "weather-mcp"
    assert s["state"] == "closed"
    assert s["failures"] == 1


if __name__ == "__main__":
    # تشغيل مباشر بلا pytest (للبيئة offline)
    import sys

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            print(f"  ✗ {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} نجاح")
    sys.exit(0 if passed == len(fns) else 1)
