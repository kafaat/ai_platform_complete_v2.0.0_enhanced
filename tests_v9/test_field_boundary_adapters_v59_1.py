"""تحقّق V59.1 — سلسلة محوّلات حدود الحقل + تقييم الجودة + حارس التراجع.

يفرض:
- الترتيب best-first: registered > ftw > sentinel2(usable) > bbox.
- كتلة الجودة السباعيّة على كلّ مقترح.
- الحدّ المسجَّل (المؤكَّد بشريّاً) يفوز بأعلى ثقة.
- **حارس التراجع:** صور موجودة لكن غير صالحة (غيوم عالية) ⇒ فوز bbox مع
  ``degraded_to_bbox_despite_imagery=True`` (ضعف زراعيّ ظاهر لا مخفيّ).
- كلّ نتيجة اقتراح فقط (requires_user_confirmation) — لا حفظ آليّ.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import field_boundary_ai as FBA  # noqa: E402
from services.ai_agronomist import field_boundary_backends as B  # noqa: E402

_BBOX = [44.18, 16.16, 44.19, 16.17]


def test_registered_boundary_wins_with_highest_trust():
    reg = {
        "type": "Polygon",
        "coordinates": [[[44.18, 16.16], [44.19, 16.16], [44.19, 16.17], [44.18, 16.16]]],
    }
    out = FBA.propose_boundaries(
        {"bbox": _BBOX, "source": "truecolor"},
        field_id="f",
        imagery_context={"registered_boundary": reg, "total_dates": 5},
    )
    assert out["boundary_source"] == "registered_boundary"
    assert out["proposed_boundaries"][0]["confidence"] == 0.95
    assert out["quality"]["edge_strength"] >= 0.85
    assert out["quality"]["requires_user_confirmation"] is True  # لا حفظ آليّ حتى للمسجَّل


def test_sentinel2_wins_on_usable_imagery():
    out = FBA.propose_boundaries(
        {"bbox": _BBOX, "source": "truecolor"},
        field_id="f",
        imagery_context={"total_dates": 5},
    )
    assert out["boundary_source"] == "sentinel2_fallback"
    assert out["degraded_to_bbox_despite_imagery"] is False
    assert "ftw_boundary_adapter" in out["adapters_tried"]  # جُرّب FTW قبل السقوط


def test_bbox_wins_without_imagery_and_is_not_flagged_degraded():
    out = FBA.propose_boundaries({"bbox": _BBOX}, field_id="f", imagery_context=None)
    assert out["boundary_source"] == "bbox_fallback"
    assert out["degraded_to_bbox_despite_imagery"] is False  # لا صور ⇒ ليس تراجعاً


def test_guard_flags_degradation_when_imagery_is_cloudy():
    out = FBA.propose_boundaries(
        {"bbox": _BBOX, "source": "truecolor"},
        field_id="f",
        imagery_context={"total_dates": 4, "cloud_risk": 0.9},  # موجودة لكن غير صالحة
    )
    assert out["boundary_source"] == "bbox_fallback"
    assert out["degraded_to_bbox_despite_imagery"] is True
    assert out["quality"]["cloud_risk"] == 0.9


def test_quality_block_has_seven_signals():
    out = FBA.propose_boundaries({"bbox": _BBOX}, field_id="f", imagery_context={"total_dates": 2})
    q = out["quality"]
    for key in (
        "boundary_confidence",
        "edge_strength",
        "shape_validity",
        "area_reasonableness",
        "source_resolution_m",
        "cloud_risk",
        "requires_user_confirmation",
    ):
        assert key in q
    assert q["shape_validity"] == 1.0  # bbox polygon مغلق وصالح


def test_adapter_chain_order_and_failsafe():
    assert [a.__name__ for a in B.BOUNDARY_ADAPTER_CHAIN] == [
        "registered_boundary_lookup",
        "ftw_boundary_adapter",
        "sentinel2_boundary_fallback",
        "bbox_fallback",
    ]
    # محوّل يرمي ⇒ يُتخطّى بأمان إلى التالي.
    out = B.run_boundary_adapters({"bbox": _BBOX}, {"cloud_risk": "not-a-number"})
    assert out is not None and out["boundary_source"] in {"sentinel2_fallback", "bbox_fallback"}


def test_area_reasonableness_flags_absurd_area():
    # حقل ضخم غير معقول (bbox بحجم قارّة) ⇒ area_reasonableness يهبط دون 1.0.
    huge = FBA.propose_boundaries({"bbox": [0.0, 0.0, 20.0, 20.0]}, field_id="f")
    assert huge["quality"]["area_reasonableness"] < 1.0
