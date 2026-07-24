"""عقد الثقة المُركَّب (الشريحة 3، P0-4) — اختبار وحدة نقيّ.

يؤكّد: الدرجة أصرم من available_count (محصول مجهول/مكوّن مُدهوَر ⇒ low) · السقف الصادق (high غير
قابلة للبلوغ) · وسم العوامل غير المُقيَّمة not_assessed (لا اختلاق) · تركيبة العوامل.
"""

import pytest
from core.crop_intelligence.confidence import compose_confidence

pytestmark = pytest.mark.unit


def _status(available, degraded=0, total=8):
    d = {}
    for i in range(available):
        d[f"a{i}"] = "available"
    for i in range(degraded):
        d[f"d{i}"] = "degraded"
    for i in range(total - available - degraded):
        d[f"u{i}"] = "unavailable"
    return d


def test_crop_unknown_forces_low_even_with_full_evidence():
    out = compose_confidence(_status(8), crop_known=False)
    assert out["grade"] == "low"  # لا ثقة توصية بلا هويّة محصول
    assert "crop_unknown" in out["limits"]
    assert out["factors"]["crop_identity"] == "unknown"


def test_any_degraded_component_forces_low():
    out = compose_confidence(_status(6, degraded=1), crop_known=True)
    assert out["grade"] == "low"
    assert out["factors"]["degradation"]["penalized"] is True
    assert "components_degraded" in out["limits"]


def test_clean_and_complete_reaches_medium_not_high():
    out = compose_confidence(_status(6), crop_known=True)
    assert out["grade"] == "medium"
    # سقف صدق: high غير قابلة للبلوغ حتّى تُقيَّم العوامل المؤجَّلة.
    assert "high" in out["unreachable"]
    assert out["grade"] != "high"


def test_sparse_evidence_is_low():
    out = compose_confidence(_status(2, total=8), crop_known=True)
    assert out["grade"] == "low"
    assert out["factors"]["evidence_completeness"]["score"] < 0.5


def test_unassessed_factors_labeled_not_fabricated():
    out = compose_confidence(_status(6), crop_known=True)
    for f in ("freshness", "spatial_alignment", "local_calibration", "model_validation"):
        assert out["factors"][f] == "not_assessed"  # لا قيمة مُختلَقة
    assert "critical_factors_not_assessed" in out["limits"]


def test_recommendation_degraded_recorded():
    out = compose_confidence(_status(6), crop_known=True, recommendation_status="degraded")
    assert "recommendation_degraded" in out["limits"]
