"""اختبارات قبول: سياسة دليل القرار لـNDVI (C5).

يثبت أنّ NDVI **لا يقلب قراراً قانونيّاً/تشغيليّاً وحده** دون معايرة:
  • لا قيمة ⇒ informational.
  • قيمة بلا معايرة/سياق ⇒ supporting (الافتراضيّ) — لا حجب.
  • قيمة + سياق محصول كامل + معايرة محليّة + جودة مشهد ⇒ decision_blocking.
  • معايرة لكن غيوم/نضارة سيّئة ⇒ supporting (بوّابة الجودة).
  • **ثابت سلامة:** decision_blocking مستحيل دون locally_calibrated=True.
  • **حارس بنيويّ:** ``resolve_field_state`` لا يقبل قيمة NDVI (عُمر فقط) ⇒ القيمة
    لا تدخل القرار أصلاً.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.evidence_policy import (  # noqa: E402
    EVIDENCE_DECISION_BLOCKING,
    EVIDENCE_INFORMATIONAL,
    EVIDENCE_SUPPORTING,
    classify_ndvi_evidence,
)
from api.field_operational_state import resolve_field_state  # noqa: E402

# سياق محصول كامل + معايرة + جودة جيّدة (الحالة الوحيدة المسموح فيها بالحجب).
_FULL = dict(
    crop="wheat",
    growth_stage="mid",
    planting_date="2026-01-01",
    locally_calibrated=True,
    cloud_pct=5.0,
    ndvi_age_days=3.0,
)


def test_no_value_is_informational():
    r = classify_ndvi_evidence(ndvi_mean=None)
    assert r["role"] == EVIDENCE_INFORMATIONAL
    assert r["confidence"] == 0.0


def test_value_without_context_is_supporting():
    """قيمة موجودة بلا معايرة/سياق ⇒ supporting، لا تحجب."""
    r = classify_ndvi_evidence(ndvi_mean=0.3)
    assert r["role"] == EVIDENCE_SUPPORTING
    assert r["calibrated"] is False


def test_full_context_and_calibration_is_decision_blocking():
    r = classify_ndvi_evidence(ndvi_mean=0.2, **_FULL)
    assert r["role"] == EVIDENCE_DECISION_BLOCKING
    assert r["calibrated"] is True


def test_poor_scene_quality_blocks_promotion():
    """معايرة + سياق لكن غيوم فوق العتبة ⇒ يبقى supporting (جودة المشهد)."""
    bad = dict(_FULL)
    bad["cloud_pct"] = 80.0
    r = classify_ndvi_evidence(ndvi_mean=0.2, **bad)
    assert r["role"] == EVIDENCE_SUPPORTING


def test_stale_ndvi_blocks_promotion():
    """معايرة + سياق لكن مشهد بايت ⇒ يبقى supporting."""
    stale = dict(_FULL)
    stale["ndvi_age_days"] = 60.0
    r = classify_ndvi_evidence(ndvi_mean=0.2, **stale)
    assert r["role"] == EVIDENCE_SUPPORTING


@pytest.mark.parametrize("crop", ["wheat", None])
@pytest.mark.parametrize("cloud", [5.0, 90.0])
@pytest.mark.parametrize("stage", ["mid", None])
def test_safety_invariant_no_blocking_without_calibration(crop, cloud, stage):
    """ثابت السلامة: لا decision_blocking أبداً دون معايرة محليّة، مهما اكتمل الباقي."""
    r = classify_ndvi_evidence(
        ndvi_mean=0.2,
        crop=crop,
        growth_stage=stage,
        planting_date="2026-01-01",
        locally_calibrated=False,  # المعايرة مُطفأة
        cloud_pct=cloud,
        ndvi_age_days=3.0,
    )
    assert r["role"] != EVIDENCE_DECISION_BLOCKING


def test_resolve_field_state_has_no_ndvi_value_param():
    """حارس بنيويّ: القرار يأخذ عُمر NDVI فقط لا قيمته ⇒ القيمة لا تقلب الصلاحيّة."""
    params = set(inspect.signature(resolve_field_state).parameters)
    assert "ndvi_age_days" in params, "نضارة NDVI (العُمر) مُدخَل مشروع"
    for forbidden in ("ndvi", "ndvi_mean", "ndvi_value"):
        assert forbidden not in params, (
            f"قيمة NDVI ({forbidden}) دخلت قرار الصلاحيّة — يخالف سياسة C5 (إشارة لا حاكم)"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
