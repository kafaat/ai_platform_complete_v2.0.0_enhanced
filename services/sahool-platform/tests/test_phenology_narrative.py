"""اختبارات سرد النموّ الفينولوجي من سلسلة NDVI (offline).

يتحقّق من: حدّ المشاهد الأدنى؛ تصنيف الأطوار (إنبات→خضري→ذروة→شيخوخة)؛ تجاهل
قيم NDVI غير المنتهية؛ كشف الشذوذ مقابل مظروف متوقَّع فقط (لا قيم مُقحَمة).
"""

import math

from core.engines.phenology_narrative import (
    GrowthPhase,
    NarrativeConfidence,
    NDVIObservation,
    build_growth_narrative,
)


def _series(values, start_dap=10, step=10):
    """يبني سلسلة مشاهد من قيم NDVI بأيّام-بعد-الزراعة متصاعدة."""
    return [
        NDVIObservation(
            date=f"2026-0{1 + i // 3}-{1 + i:02d}", ndvi=v, days_after_planting=start_dap + i * step
        )
        for i, v in enumerate(values)
    ]


# ─── الحدّ الأدنى للمشاهد ─────────────────────────────────────────────────


def test_insufficient_observations_no_narrative():
    out = build_growth_narrative(_series([0.3, 0.5, 0.6]), crop="wheat")
    assert out["confidence"] == NarrativeConfidence.INSUFFICIENT.value
    assert out["trajectory"] == []
    assert out["current_phase"] == GrowthPhase.UNKNOWN.value


# ─── تصنيف الأطوار ────────────────────────────────────────────────────────


def test_phase_classification_emergence_to_senescence():
    # منحنى نموّ نموذجي: إنبات منخفض → صعود خضري → ذروة → انحدار شيخوخة.
    out = build_growth_narrative(_series([0.15, 0.35, 0.55, 0.75, 0.80, 0.60, 0.40]), crop="wheat")
    phases = [p["phase"] for p in out["trajectory"]]
    assert phases[0] == GrowthPhase.EMERGENCE.value  # NDVI<0.2 مبكّراً
    assert phases[1] == GrowthPhase.VEGETATIVE.value
    assert GrowthPhase.PEAK.value in phases
    assert out["current_phase"] == GrowthPhase.SENESCENCE.value
    assert out["peak_ndvi"] == 0.80


def test_peak_detected_at_max():
    out = build_growth_narrative(_series([0.3, 0.5, 0.85, 0.7, 0.6]), crop="barley")
    assert out["peak_ndvi"] == 0.85
    peak_pts = [p for p in out["trajectory"] if p["phase"] == GrowthPhase.PEAK.value]
    assert len(peak_pts) == 1 and peak_pts[0]["ndvi"] == 0.85


# ─── تجاهل القيم غير المنتهية ─────────────────────────────────────────────


def test_non_finite_ndvi_ignored():
    obs = _series([0.3, 0.5, 0.7, 0.8])
    obs.insert(2, NDVIObservation(date="2026-02-15", ndvi=float("nan"), days_after_planting=35))
    obs.append(NDVIObservation(date="2026-03-20", ndvi=math.inf, days_after_planting=80))
    out = build_growth_narrative(obs, crop="wheat")
    assert out["n_valid"] == 4  # NaN و inf مُستبعدان
    assert out["n_observations"] == 6


# ─── كشف الشذوذ مقابل مظروف متوقَّع فقط ───────────────────────────────────


def test_no_anomaly_claim_without_expected_envelope():
    # بلا مظروف متوقَّع: سرد وصفيّ فقط، لا ادّعاء شذوذ (لا قيم مُقحَمة).
    out = build_growth_narrative(_series([0.15, 0.25, 0.30, 0.28]), crop="wheat")
    assert out["anomalies"] == []
    assert out["anomaly_check_available"] is False


def test_low_peak_anomaly_against_floor():
    out = build_growth_narrative(
        _series([0.2, 0.35, 0.45, 0.40]), crop="wheat", peak_ndvi_floor=0.65
    )
    assert out["anomaly_check_available"] is True
    assert any(a["type"] == "low_peak" for a in out["anomalies"])


def test_early_senescence_anomaly():
    # الذروة مبكّرة (عند 30 يوم) ثمّ انحدار، والمتوقّع ≥70 — شيخوخة مبكّرة.
    obs = _series([0.3, 0.75, 0.6, 0.45], start_dap=10, step=10)  # ذروة عند dap=20
    out = build_growth_narrative(obs, crop="wheat", expected_peak_dap_min=60)
    assert any(a["type"] == "early_senescence" for a in out["anomalies"])


def test_healthy_curve_no_anomaly_with_envelope():
    out = build_growth_narrative(
        _series([0.2, 0.45, 0.65, 0.80, 0.78, 0.6]),
        crop="wheat",
        peak_ndvi_floor=0.65,
        expected_peak_dap_min=40,
    )
    assert out["anomalies"] == []


# ─── حالات حدّيّة (مراجعة نقديّة) ──────────────────────────────────────────


def test_all_below_bare_floor_is_emergence_no_fake_peak_or_senescence():
    # سلسلة كلّها دون عتبة التربة العارية: لا نموّ فعليّ ⇒ إنبات فقط، لا ذروة/شيخوخة وهميّة.
    out = build_growth_narrative(_series([0.05, 0.10, 0.08, 0.06]), crop="wheat")
    phases = {p["phase"] for p in out["trajectory"]}
    assert phases == {GrowthPhase.EMERGENCE.value}
    assert out["current_phase"] == GrowthPhase.EMERGENCE.value


def test_mixed_dap_none_sorts_last_not_front():
    # مشاهدة بلا days_after_planting يجب ألّا تُقحَم في المقدّمة كأنّها يوم 0.
    obs = [
        NDVIObservation(date="2026-03-01", ndvi=0.5, days_after_planting=None),
        NDVIObservation(date="2026-01-01", ndvi=0.3, days_after_planting=10),
        NDVIObservation(date="2026-01-11", ndvi=0.6, days_after_planting=20),
        NDVIObservation(date="2026-01-21", ndvi=0.7, days_after_planting=30),
    ]
    out = build_growth_narrative(obs, crop="wheat")
    assert out["trajectory"][0]["days_after_planting"] == 10  # المعروف أوّلاً
    assert out["trajectory"][-1]["days_after_planting"] is None  # المجهول أخيراً
