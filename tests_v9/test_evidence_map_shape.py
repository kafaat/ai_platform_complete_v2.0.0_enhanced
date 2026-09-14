"""اختبارات نقيّة لطبقة تشكيل خريطة الدليل (api.evidence_map).

تصنيف مستوى دليل كلّ حقل من العدّ المُدام (قرارات/قياسات) دون تلفيق: عتبة موسومة،
needs_data صريح للحقل بلا دليل، ولا رسم دون إحداثيّات حقيقيّة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.evidence_map import (  # noqa: E402
    EVIDENCE_VERIFIED_MIN_SAMPLES,
    shape_evidence_map,
)


def test_tiers_classified_by_persisted_counts():
    out = shape_evidence_map(
        [
            {
                "field_id": "f1",
                "decisions": 2,
                "outcomes": EVIDENCE_VERIFIED_MIN_SAMPLES,
                "successes": 25,
            },
            {"field_id": "f2", "decisions": 1, "outcomes": 3, "successes": 2},
            {"field_id": "f3", "decisions": 4, "outcomes": 0, "successes": 0},
            {"field_id": "f4", "decisions": 0, "outcomes": 0, "successes": 0},
        ]
    )
    tiers = {f["field_id"]: f["tier"] for f in out["fields"]}
    # U01 (Copilot على #1001): العدُّ ≥ العتبة «عيّنة مكتملة» لا «مؤكَّد» — المراجعة ليست في العدّ.
    assert tiers["f1"] == "field_sample_complete"
    assert tiers["f2"] == "field_preliminary"
    assert tiers["f3"] == "indicative"
    assert tiers["f4"] == "needs_data"
    assert out["totals_by_tier"] == {
        "field_verified": 0,
        "field_sample_complete": 1,
        "field_preliminary": 1,
        "indicative": 1,
        "needs_data": 1,
    }
    assert all(f["tier"] != "field_verified" for f in out["fields"]), (
        "العدُّ الخام لا يمنح field_verified — الاعتمادُ قرارُ مراجعة"
    )


def test_count_only_consumers_count_evaluated_rows_only():
    """Copilot على #1001: كان COUNT(*) يعدّ صفوف outcome_record الفارغة (n_evaluated=0) التي
    يُسقِطها سجلُّ الدليل — فتبدو 30 سجلّاً بلا قياس «عيّنة مكتملة» في الخريطة وبدرجة 0.8 في الثقة."""
    from pathlib import Path

    from api.evidence_map import EVALUATED_OUTCOME_PREDICATE

    assert "n_evaluated" in EVALUATED_OUTCOME_PREDICATE and "> 0" in EVALUATED_OUTCOME_PREDICATE
    assert "CASE WHEN" in EVALUATED_OUTCOME_PREDICATE  # لا تحويلَ لنصّ غير رقميّ قبل فحصه
    routers = Path(__file__).resolve().parents[1] / "services/sahool-platform/api/routers"
    ev_map = (routers / "evidence_map.py").read_text(encoding="utf-8")
    assert (
        ev_map.count("FILTER (WHERE {EVALUATED_OUTCOME_PREDICATE})") == 2
    )  # cnt + last_outcome_at
    assert "success IS TRUE AND {EVALUATED_OUTCOME_PREDICATE}" in ev_map
    assert "COUNT(*) AS cnt FROM decision_record" in ev_map  # القراراتُ تُعدّ كلُّها (لا metrics فيها)
    assert "SELECT field_id, COUNT(*) AS cnt, " not in ev_map, (
        "عدُّ outcome_record بلا شرط التقييم يُضخِّم العيّنة بصفوف بلا قياس"
    )
    dc = (routers / "decision_confidence.py").read_text(encoding="utf-8")
    assert "field_id, predicate=EVALUATED_OUTCOME_PREDICATE" in dc
    assert '_scalar(conn, "outcome_record", field_id)\n' not in dc, (
        "عدُّ outcome_record بلا شرط التقييم يمنح درجةَ «عيّنة مكتملة» لحقل بلا قياس"
    )


def test_needs_data_is_explicit_not_green():
    # حقل بلا قرار ولا قياس ⇒ needs_data رماديّ صريح (لا أخضر افتراضيّ).
    out = shape_evidence_map([{"field_id": "f1"}])
    f = out["fields"][0]
    assert f["tier"] == "needs_data"
    assert f["color"] == "gray"
    assert f["success_rate"] is None


def test_success_rate_only_when_outcomes_present():
    out = shape_evidence_map([{"field_id": "f1", "decisions": 1, "outcomes": 4, "successes": 3}])
    assert out["fields"][0]["success_rate"] == 0.75
    assert out["fields"][0]["samples_to_verified"] == EVIDENCE_VERIFIED_MIN_SAMPLES - 4


def test_no_coords_means_not_plottable_no_fabrication():
    # إحداثيّات غائبة/غير رقميّة ⇒ has_coords=False و lat/lon=None (لا تَفبرِك موقعاً).
    out = shape_evidence_map(
        [
            {"field_id": "f1", "lat": 15.0, "lon": 45.5, "decisions": 1},
            {"field_id": "f2", "lat": None, "lon": None, "decisions": 1},
            {"field_id": "f3", "lat": "x", "lon": "y", "decisions": 1},
        ]
    )
    by_id = {f["field_id"]: f for f in out["fields"]}
    assert by_id["f1"]["has_coords"] is True
    assert by_id["f2"]["has_coords"] is False and by_id["f2"]["lat"] is None
    assert by_id["f3"]["has_coords"] is False
    assert out["plottable_count"] == 1


def test_bad_counts_coerced_safely():
    # قيم شاذّة (سالب/نصّ) ⇒ 0 لا انهيار.
    out = shape_evidence_map([{"field_id": "f1", "decisions": -5, "outcomes": "x"}])
    f = out["fields"][0]
    assert f["decisions"] == 0 and f["outcomes"] == 0
    assert f["tier"] == "needs_data"


def test_legend_and_threshold_and_provenance():
    out = shape_evidence_map([], generated_at="2026-06-20T12:00:00+00:00")
    assert out["generated_at"] == "2026-06-20T12:00:00+00:00"
    assert [lg["tier"] for lg in out["legend"]] == [
        "field_verified",
        "field_sample_complete",
        "field_preliminary",
        "indicative",
        "needs_data",
    ]
    assert out["verified_threshold"] == EVIDENCE_VERIFIED_MIN_SAMPLES
    assert out["provenance"]["calibrated"] == "not_applicable"
    assert "needs_data" in out["provenance"]["note_ar"]
    assert out["field_count"] == 0


def test_thresholds_estimated_flagged():
    out = shape_evidence_map([{"field_id": "f1", "decisions": 1, "outcomes": 1, "successes": 1}])
    assert out["provenance"]["thresholds_estimated"] is True
