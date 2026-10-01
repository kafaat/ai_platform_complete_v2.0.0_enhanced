"""SAHOOL-DEBUG-FLAG-INVISIBLE-AT-RUNTIME-01 — حالةُ SAHOOL_DEBUG تظهر في سجلّ الإقلاع."""

from __future__ import annotations

import importlib
import logging

import pytest

pytestmark = pytest.mark.unit


def _reload_readiness(monkeypatch, caplog, value):
    if value is None:
        monkeypatch.delenv("SAHOOL_DEBUG", raising=False)
    else:
        monkeypatch.setenv("SAHOOL_DEBUG", value)
    import api.routers.readiness as readiness

    with caplog.at_level(logging.WARNING, logger=readiness.__name__):
        caplog.clear()
        readiness = importlib.reload(readiness)
    return readiness, [r.getMessage() for r in caplog.records if r.name == readiness.__name__]


@pytest.mark.parametrize(
    ("value", "state"), [("1", "on"), ("true", "on"), ("0", "off"), ("", "off"), (None, "off")]
)
def test_the_startup_log_states_the_debug_flag(monkeypatch, caplog, value, state) -> None:
    """الصفرُ مُميَّزٌ عن الغياب: السطرُ يُكتب في الحالتين، فغيابُه يعني أنّ الموجِّه لم يُستورَد."""
    readiness, messages = _reload_readiness(monkeypatch, caplog, value)
    assert readiness.DEBUG_FLAG_STATE == state
    assert messages == [f"SAHOOL_DEBUG={state}"]


def test_the_log_line_never_carries_the_raw_value(monkeypatch, caplog) -> None:
    _, messages = _reload_readiness(monkeypatch, caplog, "yes-secret-looking-value")
    assert messages == ["SAHOOL_DEBUG=off"]
    assert all("secret" not in m for m in messages)
