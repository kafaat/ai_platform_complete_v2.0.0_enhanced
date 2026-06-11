#!/usr/bin/env python3
"""
اختبارات رصد القاطع — تتحقّق أنّ انتقالات الحالة لم تَعُد صامتة:
تُصدِر سجلّاً بنيويّاً + مقياس Prometheus، وأنّ الرفض السريع يُعَدّ.

تعمل offline بلا خدمة حيّة (نمط test_circuit_breaker.py). تقرأ قيم المقاييس
مباشرةً من كائنات prometheus_client بلا حاجة لخادم scrape.
"""

import logging

from circuit_breaker import (
    _CIRCUIT_REJECTIONS,
    _CIRCUIT_STATE,
    _CIRCUIT_TRANSITIONS,
    CircuitBreaker,
    CircuitState,
)


def _gauge(service: str) -> float:
    return _CIRCUIT_STATE.labels(service=service)._value.get()


def _transitions(service: str, to_state: str) -> float:
    return _CIRCUIT_TRANSITIONS.labels(service=service, to_state=to_state)._value.get()


def _rejections(service: str) -> float:
    return _CIRCUIT_REJECTIONS.labels(service=service)._value.get()


def test_open_sets_gauge_and_counter():
    cb = CircuitBreaker(name="obs_open", failure_threshold=2)
    before = _transitions("obs_open", "open")
    cb.record_failure()
    cb.record_failure()  # يفتح
    assert cb.state == CircuitState.OPEN
    assert _gauge("obs_open") == 2  # 2 == open
    assert _transitions("obs_open", "open") == before + 1


def test_state_change_is_logged(caplog):
    cb = CircuitBreaker(name="obs_log", failure_threshold=1)
    with caplog.at_level(logging.WARNING, logger="supervisor-agent.circuit"):
        cb.record_failure()  # closed -> open
    assert any(
        "circuit.state_change" in r.message and "obs_log" in r.message for r in caplog.records
    )


def test_no_transition_when_state_unchanged(caplog):
    # نجاحات متتالية في CLOSED يجب ألّا تُسجّل أيّ انتقال (لا تضخيم).
    cb = CircuitBreaker(name="obs_noop")
    with caplog.at_level(logging.WARNING, logger="supervisor-agent.circuit"):
        cb.record_success()
        cb.record_success()
    assert not any("circuit.state_change" in r.message for r in caplog.records)


def test_fast_reject_is_counted():
    cb = CircuitBreaker(name="obs_reject", failure_threshold=1, recovery_timeout=999)
    cb.record_failure()  # يفتح
    before = _rejections("obs_reject")
    assert cb.allow_request() is False  # رفض سريع #1
    assert cb.allow_request() is False  # رفض سريع #2
    assert _rejections("obs_reject") == before + 2


def test_recovery_path_returns_gauge_to_closed():
    cb = CircuitBreaker(
        name="obs_recover", failure_threshold=1, recovery_timeout=0.0, success_threshold=1
    )
    cb.record_failure()  # open
    assert _gauge("obs_recover") == 2
    assert cb.allow_request() is True  # open -> half_open (timeout=0)
    assert _gauge("obs_recover") == 1  # half_open
    cb.record_success()  # half_open -> closed
    assert cb.state == CircuitState.CLOSED
    assert _gauge("obs_recover") == 0
