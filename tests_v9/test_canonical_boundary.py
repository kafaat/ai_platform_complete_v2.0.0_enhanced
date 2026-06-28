"""اختبار وحدة لقارئ ثقة الحدود الكنسيّة (Bundle B) — قراءة/تطبيع صرف، بلا حساب.

يقفل: كتلة `boundary` تُطبَّع عند توفّر `confidence_score` (مع source مُعلَن +
`review_recommended` من نفس عتبة score_boundary)؛ وتغيب (None) عند غياب الثقة/مدخل
غير صالح — فلا يقرأ المستهلكون قيمة مُلفَّقة، ولا يُصعَّد على ثقة غائبة.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

try:
    from api.boundary_confidence import CONFIDENCE_REVIEW_THRESHOLD
    from api.canonical_boundary import canonical_boundary
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable", allow_module_level=True)


def test_block_when_confidence_present():
    """ثقة عالية موجودة ⇒ كتلة مكتملة بمصدر مُعلَن، بلا توصية مراجعة."""
    row = {
        "confidence_score": 0.92,
        "source_type": "manual",
        "model_version": "v1",
        "review_status": "approved",
    }
    b = canonical_boundary(row)
    assert b is not None
    assert b["boundary_confidence"] == 0.92
    assert b["boundary_source"] == "manual"
    assert b["boundary_version"] == "v1"
    assert b["review_status"] == "approved"
    assert b["review_recommended"] is False  # 0.92 ≥ العتبة
    assert b["source"] == "field_state.canonical"


def test_review_recommended_below_threshold():
    """ثقة منخفضة (< العتبة) ⇒ review_recommended=True (دافع التصعيد للمراجعة)."""
    low = round(CONFIDENCE_REVIEW_THRESHOLD - 0.1, 3)
    b = canonical_boundary({"confidence_score": low})
    assert b is not None
    assert b["boundary_confidence"] == low
    assert b["review_recommended"] is True
    # المفاتيح الاختياريّة الغائبة تُعامَل بأمان (None لا رمي).
    assert b["boundary_source"] is None
    assert b["boundary_version"] is None
    assert b["review_status"] is None


def test_none_when_confidence_missing():
    """غياب confidence_score ⇒ None (لا كتلة، لا تصعيد على قيمة غائبة)."""
    assert canonical_boundary({"source_type": "manual"}) is None
    assert canonical_boundary({"confidence_score": None}) is None
    assert canonical_boundary({}) is None


def test_none_on_invalid_input():
    """مدخل غير قاموس أو ثقة فاسدة ⇒ None (صدق + fail-safe)."""
    assert canonical_boundary(None) is None
    assert canonical_boundary("nope") is None
    assert canonical_boundary({"confidence_score": "abc"}) is None
