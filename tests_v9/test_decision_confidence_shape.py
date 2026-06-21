"""اختبارات نقيّة لدمج ثقة القرار (api.decision_confidence).

تركيبة موزونة على المصادر المتوفّرة فقط: الغائب يُعلَن missing لا يُفترَض، لا مصدر ⇒
insufficient — عرض فقط، لا تلفيق.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.decision_confidence import fuse_decision_confidence  # noqa: E402


def test_all_sources_present_high():
    out = fuse_decision_confidence(
        {
            "sensor": {"value": 0.9},
            "evidence": {"value": 0.8},
            "satellite": {"value": 0.85},
            "weather": {"value": 0.8},
        }
    )
    assert out["level"] == "high"
    assert out["confidence"] >= 0.75
    assert out["missing"] == []
    assert out["present_count"] == 4


def test_missing_sources_declared_not_assumed():
    # حسّاس فقط ⇒ التركيبة عليه وحده، والبقيّة missing مُعلَنة (لا تُفترَض).
    out = fuse_decision_confidence({"sensor": {"value": 0.6}})
    assert out["confidence"] == 0.6  # وزن واحد ⇒ القيمة نفسها بعد التطبيع
    assert set(out["missing"]) == {"evidence", "satellite", "weather"}
    by = {c["source"]: c for c in out["components"]}
    assert by["evidence"]["available"] is False
    assert by["evidence"]["value"] is None


def test_no_sources_is_insufficient_not_zero():
    out = fuse_decision_confidence({})
    assert out["confidence"] is None
    assert out["level"] == "insufficient"
    assert out["present_count"] == 0


def test_none_value_means_unavailable():
    out = fuse_decision_confidence({"sensor": {"value": None}, "evidence": {"value": 0.5}})
    by = {c["source"]: c for c in out["components"]}
    assert by["sensor"]["available"] is False
    assert by["evidence"]["available"] is True
    assert out["confidence"] == 0.5


def test_weighted_average_over_available_only():
    # حسّاس 1.0 (وزن 0.30) + طقس 0.0 (وزن 0.20) ⇒ (0.30)/(0.50)=0.6.
    out = fuse_decision_confidence({"sensor": {"value": 1.0}, "weather": {"value": 0.0}})
    assert out["confidence"] == 0.6
    assert out["level"] == "medium"


def test_values_clamped_and_detail_passthrough():
    out = fuse_decision_confidence(
        {"sensor": {"value": 1.5, "detail_ar": "أسطول سليم"}, "evidence": {"value": -0.2}}
    )
    by = {c["source"]: c for c in out["components"]}
    assert by["sensor"]["value"] == 1.0  # قُصَّ إلى [0,1]
    assert by["evidence"]["value"] == 0.0
    assert by["sensor"]["detail_ar"] == "أسطول سليم"


def test_provenance_and_levels():
    low = fuse_decision_confidence({"sensor": {"value": 0.2}})
    assert low["level"] == "low"
    out = fuse_decision_confidence(
        {"sensor": {"value": 0.5}}, generated_at="2026-06-21T00:00:00+00:00"
    )
    assert out["generated_at"] == "2026-06-21T00:00:00+00:00"
    assert out["provenance"]["calibrated"] == "not_applicable"
    assert "عرض فقط" in out["provenance"]["note_ar"]


def test_thresholds_estimated_flagged():
    out = fuse_decision_confidence({"sensor": {"value": 0.5}})
    assert out["provenance"]["thresholds_estimated"] is True
