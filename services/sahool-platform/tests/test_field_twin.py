"""اختبارات التوأم الرقميّ للحقل (core.field_twin) — المرحلة B، الشريحة 6.

نقيّة وحتميّة ⇒ `unit`. تثبّت اشتقاق الحالة بالأسبقيّة (محجوب←قديم←يحتاج انتباهاً←سليم)،
حساب قِدَم البيانات، وأسباب الانتباه الصريحة، وقابليّة التسلسل.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from core.field_twin import assemble_twin  # noqa: E402


def test_healthy_when_good_ndvi_and_no_open_decisions():
    t = assemble_twin(
        "f1",
        crop="قمح",
        latest_indices={"ndvi": 0.72, "evi": 0.5},
        observed_at="2026-06-16",
        now="2026-06-17",
    )
    assert t.state == "healthy"
    assert t.ndvi == 0.72
    assert t.attention_reasons_ar == []
    assert t.data_age_days == 1


def test_blocked_dominates_everything():
    t = assemble_twin(
        "f1",
        latest_indices={"ndvi": 0.8},
        observed_at="2026-06-17",
        now="2026-06-17",
        open_decisions=[{"state": "blocked", "exec_status": "not_executed"}],
    )
    assert t.state == "blocked"
    assert t.blocked_decisions == 1
    assert any("محجوب" in r for r in t.attention_reasons_ar)


def test_stale_when_no_indices():
    t = assemble_twin("f1", latest_indices={}, now="2026-06-17")
    assert t.state == "stale"
    assert any("لا مؤشّرات" in r for r in t.attention_reasons_ar)
    assert t.data_age_days is None


def test_stale_when_data_old():
    t = assemble_twin(
        "f1",
        latest_indices={"ndvi": 0.7},
        observed_at="2026-06-01",
        now="2026-06-17",  # 16 يوماً > 7
    )
    assert t.state == "stale"
    assert t.data_age_days == 16
    assert any("أقدم" in r for r in t.attention_reasons_ar)


def test_needs_attention_low_ndvi():
    t = assemble_twin(
        "f1",
        latest_indices={"ndvi": 0.22},
        observed_at="2026-06-16",
        now="2026-06-17",
    )
    assert t.state == "needs_attention"
    assert any("غطاء نباتيّ ضعيف" in r for r in t.attention_reasons_ar)


def test_needs_attention_active_decision():
    t = assemble_twin(
        "f1",
        latest_indices={"ndvi": 0.65},
        observed_at="2026-06-16",
        now="2026-06-17",
        open_decisions=[{"state": "ready", "exec_status": "dispatched"}],
    )
    assert t.state == "needs_attention"
    assert t.open_decisions == 1
    assert any("قيد التنفيذ" in r for r in t.attention_reasons_ar)


def test_blocked_takes_priority_over_low_ndvi():
    t = assemble_twin(
        "f1",
        latest_indices={"ndvi": 0.1},  # ضعيف أيضاً
        observed_at="2026-06-17",
        now="2026-06-17",
        open_decisions=[{"state": "blocked", "exec_status": "not_executed"}],
    )
    assert t.state == "blocked"  # المحجوب يسبق


def test_freshness_threshold_configurable():
    t = assemble_twin(
        "f1",
        latest_indices={"ndvi": 0.7},
        observed_at="2026-06-10",
        now="2026-06-17",  # 7 أيّام
        freshness_days=10,
    )
    assert t.state == "healthy"  # ضمن النافذة الموسَّعة


def test_last_execution_passthrough_and_serializable():
    import json

    t = assemble_twin(
        "f1",
        latest_indices={"ndvi": 0.7},
        observed_at="2026-06-16",
        now="2026-06-17",
        last_execution={"outcome": "executed", "action_type": "irrigation"},
    )
    blob = json.dumps(t.to_dict(), ensure_ascii=False)
    parsed = json.loads(blob)
    assert parsed["last_execution"]["outcome"] == "executed"
    assert parsed["field_id"] == "f1"
    assert parsed["state"] == "healthy"


def test_handles_datetime_observed_at():
    from datetime import datetime

    t = assemble_twin(
        "f1",
        latest_indices={"ndvi": 0.7},
        observed_at=datetime(2026, 6, 15, 10, 0),
        now=datetime(2026, 6, 17, 10, 0),
    )
    assert t.data_age_days == 2
    assert t.observed_at == "2026-06-15"
