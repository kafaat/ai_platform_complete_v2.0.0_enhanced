"""اختبارات قياس الأثر (core.impact_measurement) — المرحلة C، الشريحة 8.

نقيّة وحتميّة ⇒ `unit`. تثبّت: عدّ النتائج، نسبة النجاح، حساب الماء الموفَّر فقط بكمّيّتين
صالحتين (صدق التغطية)، التفصيل per-action، وحالات الحدود.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from core.impact_measurement import ImpactRecord, measure_impact  # noqa: E402


def test_empty_records():
    s = measure_impact([])
    assert s.total_decisions == 0
    assert s.success_rate == 0.0
    assert s.water_saved_mm == 0.0
    assert s.by_action == {}


def test_success_rate():
    recs = [
        ImpactRecord(action_type="irrigation", outcome="executed"),
        ImpactRecord(action_type="irrigation", outcome="executed"),
        ImpactRecord(action_type="irrigation", outcome="failed"),
    ]
    s = measure_impact(recs)
    assert s.executed == 2
    assert s.failed == 1
    assert s.success_rate == round(2 / 3, 3)


def test_water_saved_only_with_both_quantities():
    recs = [
        ImpactRecord(
            action_type="irrigation",
            outcome="executed",
            water_requested_mm=20.0,
            water_applied_mm=14.0,
        ),
        # ناقص الكمّيّة المُطبَّقة ⇒ يُستثنى من حساب الماء (لا من النتائج)
        ImpactRecord(action_type="irrigation", outcome="executed", water_requested_mm=20.0),
    ]
    s = measure_impact(recs)
    assert s.executed == 2
    assert s.water_saved_mm == 6.0  # فقط السجلّ الأوّل
    assert s.water_records == 1


def test_water_not_counted_for_failed():
    recs = [
        ImpactRecord(
            action_type="irrigation",
            outcome="failed",
            water_requested_mm=20.0,
            water_applied_mm=10.0,
        ),
    ]
    s = measure_impact(recs)
    assert s.water_saved_mm == 0.0
    assert s.water_records == 0


def test_invalid_water_pair_excluded():
    # المُطبَّق > المطلوب (غير منطقيّ) ⇒ يُستثنى بصدق
    recs = [
        ImpactRecord(
            action_type="irrigation",
            outcome="executed",
            water_requested_mm=10.0,
            water_applied_mm=15.0,
        ),
    ]
    s = measure_impact(recs)
    assert s.water_records == 0
    assert s.water_saved_mm == 0.0


def test_by_action_breakdown():
    recs = [
        ImpactRecord(
            action_type="irrigation",
            outcome="executed",
            water_requested_mm=20.0,
            water_applied_mm=12.0,
        ),
        ImpactRecord(action_type="spray", outcome="failed"),
        ImpactRecord(action_type="spray", outcome="executed"),
    ]
    s = measure_impact(recs)
    assert s.by_action["irrigation"]["executed"] == 1
    assert s.by_action["irrigation"]["water_saved_mm"] == 8.0
    assert s.by_action["spray"]["executed"] == 1
    assert s.by_action["spray"]["failed"] == 1
    assert s.by_action["spray"]["water_saved_mm"] == 0.0


def test_serializable():
    import json

    s = measure_impact([ImpactRecord(action_type="irrigation", outcome="executed")])
    blob = json.dumps(s.to_dict(), ensure_ascii=False)
    assert json.loads(blob)["executed"] == 1
