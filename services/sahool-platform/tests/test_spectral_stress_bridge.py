"""اختبارات جسر الإجهاد المائي الطيفي (offline) — NDMI/MSI → قرار، والصدق.

يتحقّق من: تحويل NDMI/MSI إلى إشارة إجهاد بعتباتها العلميّة، دمج المؤشّرين
(اتّفاق→ثقة عالية، تضارب→الأشدّ احترازاً)، الصدق عند غياب المؤشّر (unknown، لا
اختراع)، وتقرير شفافيّة الربط. لا قاعدة/شبكة.
"""

from core.engines.spectral_stress_bridge import (
    assess_water_stress_msi,
    assess_water_stress_ndmi,
    fuse_water_stress,
    index_coverage_report,
)

# ─── NDMI ────────────────────────────────────────────────────────────────


def test_ndmi_thresholds_map_to_signals():
    assert assess_water_stress_ndmi(0.5)["signal"] == "none"  # رطب
    assert assess_water_stress_ndmi(0.3)["signal"] == "mild"
    assert assess_water_stress_ndmi(0.1)["signal"] == "moderate"
    assert assess_water_stress_ndmi(-0.1)["signal"] == "severe"


def test_ndmi_missing_is_unknown_not_invented():
    out = assess_water_stress_ndmi(None)
    assert out["signal"] == "unknown"  # صدق: لا صورة → لا إشارة


# ─── MSI (عكس NDMI) ──────────────────────────────────────────────────────


def test_msi_thresholds_inverse_of_ndmi():
    assert assess_water_stress_msi(0.8)["signal"] == "none"  # MSI منخفض = صحّي
    assert assess_water_stress_msi(1.3)["signal"] == "mild"
    assert assess_water_stress_msi(1.8)["signal"] == "moderate"
    assert assess_water_stress_msi(2.5)["signal"] == "severe"  # مرتفع = إجهاد
    assert assess_water_stress_msi(None)["signal"] == "unknown"


# ─── الدمج ───────────────────────────────────────────────────────────────


def test_fuse_both_missing_is_unknown():
    out = fuse_water_stress(ndmi=None, msi=None)
    assert out["fused_signal"] == "unknown"
    assert out["confidence"] == "none"  # صدق: لا حكم بلا مؤشّر


def test_fuse_agreement_is_high_confidence():
    # NDMI رطب (none) + MSI صحّي (none) ⇒ اتّفاق ⇒ ثقة عالية
    out = fuse_water_stress(ndmi=0.5, msi=0.8)
    assert out["fused_signal"] == "none"
    assert out["agreement"] is True
    assert out["confidence"] == "high"


def test_fuse_conflict_takes_worst_cautiously():
    # NDMI يقول severe (-0.1) + MSI يقول none (0.8) ⇒ الأشدّ احترازاً = severe
    out = fuse_water_stress(ndmi=-0.1, msi=0.8)
    assert out["fused_signal"] == "severe"
    assert out["agreement"] is False
    assert out["confidence"] == "moderate"


def test_fuse_single_index_moderate_confidence():
    out = fuse_water_stress(ndmi=0.1, msi=None)  # MSI غير محسوب (واقع الشجرة)
    assert out["fused_signal"] == "moderate"
    assert out["confidence"] == "moderate"


# ─── تقرير الشفافيّة ─────────────────────────────────────────────────────


def test_coverage_report_marks_ndmi_linked_and_is_honest():
    rep = index_coverage_report()
    assert "ndmi" in rep["decision_linked"]
    assert "msi" in rep["decision_linked"]  # مذكور (الجسر يدعمه)
    assert "fapar" in rep["display_or_context_only"]
    assert "honesty_note_ar" in rep
