"""Weather → Field Timeline link — pure-logic tests for the weather decision-record builder.

يختبر الدالّتين النقيّتين اللتين تربطان محرّك الطقس بالخطّ الزمني للحقل:
``_weather_decision_why_ar`` (جملة «لماذا» العربيّة) و``_build_weather_decision_record``
(شكل صفّ decision_record). لا قاعدة بيانات — منطق صرف فقط.
"""

from __future__ import annotations

import pytest
from api.routers.weather import (
    _build_weather_decision_record,
    _weather_decision_why_ar,
)

pytestmark = pytest.mark.unit


def _plan_item(**overrides):
    item = {
        "operation": "spraying",
        "advice_ar": "نافذة رش قابلة للتنفيذ.",
        "priority": 82,
        "best": {
            "time": "+3h",
            "weather_time": "2026-06-29T15:00:00Z",
            "operation": {
                "operation": "spraying",
                "score": 0.82,
                "suitability": "optimal",
                "limiting_factors": [],
            },
        },
    }
    item.update(overrides)
    return item


def test_why_ar_mentions_operation_window_and_score():
    why = _weather_decision_why_ar(
        "spraying",
        {"time": "+3h"},
        {"suitability": "optimal", "score": 0.82, "limiting_factors": []},
        82,
    )
    assert "الرش" in why  # operation label
    assert "+3h" in why  # best window
    assert "82%" in why  # priority/score
    assert "Weather Operation Plan" in why  # source provenance


def test_why_ar_lists_limiting_factors_when_present():
    why = _weather_decision_why_ar(
        "spraying",
        {"time": "now"},
        {"suitability": "unsafe", "score": 0.1, "limiting_factors": ["wind_speed_high"]},
        10,
    )
    assert "wind_speed_high" in why


def test_build_decision_record_shape_for_task():
    rec = _build_weather_decision_record(
        "field-123", _plan_item(), model="best_match", target="task"
    )
    assert rec["field_id"] == "field-123"
    # decision_type must stay within the existing free-text VARCHAR(60) column, no new table.
    assert rec["decision_type"] == "weather_operation_plan"
    assert len(rec["decision_type"]) <= 60
    assert rec["confidence"] == pytest.approx(0.82)
    assert rec["why_ar"] == rec["decision_value"]["why_ar"]

    value = rec["decision_value"]
    assert value["target"] == "task"
    assert value["operation"] == "spraying"
    assert value["best_window"] == "+3h"
    assert value["best_weather_time"] == "2026-06-29T15:00:00Z"
    assert value["score"] == pytest.approx(0.82)
    assert value["suitability"] == "optimal"
    assert value["priority_score"] == 82
    assert value["model"] == "best_match"
    assert value["source"] == "weather_operation_plan"


def test_build_decision_record_target_recommendation():
    rec = _build_weather_decision_record(
        "field-9", _plan_item(operation="irrigation"), target="recommendation"
    )
    assert rec["decision_value"]["target"] == "recommendation"
    assert rec["decision_value"]["operation"] == "irrigation"


def test_build_decision_record_missing_best_is_honest_not_fabricated():
    # No best window / decision ⇒ unsafe fallback, score 0, confidence 0.0 (not fabricated).
    rec = _build_weather_decision_record(
        "field-x", {"operation": "harvesting", "best": None}, target="task"
    )
    assert rec["decision_value"]["suitability"] == "unsafe"
    assert rec["decision_value"]["score"] == 0
    assert rec["decision_value"]["best_window"] is None
    assert rec["confidence"] == pytest.approx(0.0)


def test_confidence_is_none_when_score_non_numeric():
    rec = _build_weather_decision_record(
        "field-x",
        {"operation": "spraying", "best": {"time": "now", "operation": {"score": None}}},
        target="task",
    )
    assert rec["confidence"] is None
