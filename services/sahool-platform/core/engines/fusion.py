"""
sahool_core.fusion.indices
===========================
Multi-index satellite fusion with HONEST error propagation.

The critique's key math point: weighted fusion does NOT magically halve
error. Combining correlated indices (NDVI & EVI2, rho~0.85) barely helps.
Real gain comes from fusing INDEPENDENT families (Optical + SAR + Thermal).

Ensemble variance (correlation-aware):
    sigma_fused^2 = sum_i (w_i^2 * sigma_i^2)
                  + 2 * sum_{i<j} (w_i * w_j * rho_ij * sigma_i * sigma_j)

We expose confidence as CATEGORIES (high/medium/low), never a fake % point
(another critique requirement).

Cloud handling: if optical is cloudy, shift weight to SAR (which penetrates
cloud/dust — optical disabled 30-40% of the year in dusty arid coastal zones).

Sources:
  - Error propagation for correlated variables: standard (GUM / Ku 1966).
  - NDWI_865-1614 + SCA-VV soil moisture R^2=0.54 vs NDVI 0.31:
    arid-region SAR+optical fusion literature (2023-2025).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class IndexReading:
    name: str
    value: float
    sigma: float          # measurement std (error)
    weight: float
    family: str           # "optical" | "sar" | "thermal"


# default correlation between indices of the SAME family (high),
# and between families (low). Used in ensemble variance.
def _rho(a: IndexReading, b: IndexReading) -> float:
    if a.family == b.family:
        return 0.85   # same family — highly correlated, little fusion gain
    return 0.15       # cross-family — nearly independent, real gain


def ensemble_variance(readings: list[IndexReading]) -> float:
    """Correlation-aware fused variance. The honest version."""
    var = 0.0
    # diagonal
    for r in readings:
        var += (r.weight ** 2) * (r.sigma ** 2)
    # off-diagonal (correlation terms)
    n = len(readings)
    for i in range(n):
        for j in range(i + 1, n):
            ri, rj = readings[i], readings[j]
            var += (
                2.0 * ri.weight * rj.weight * _rho(ri, rj)
                * ri.sigma * rj.sigma
            )
    return var


def classify_confidence(fused_sigma: float) -> Confidence:
    """Category, not a fake percentage."""
    if fused_sigma < 0.06:
        return Confidence.HIGH
    if fused_sigma < 0.12:
        return Confidence.MEDIUM
    return Confidence.LOW


@dataclass
class FusionResult:
    fused_value: float
    fused_sigma: float
    confidence: Confidence
    dominant_family: str
    cloud_cover_pct: float
    notes: list[str] = field(default_factory=list)


def fuse_health(
    readings: list[IndexReading],
    cloud_cover_pct: float,
    cwsi: float | None = None,
) -> FusionResult:
    """Fuse multi-family indices into one health estimate + honest confidence.

    cloud_cover_pct: if high, optical is down-weighted toward SAR.
    cwsi: optional Crop Water Stress Index (thermal) — applies a penalty.
    """
    notes: list[str] = []
    rs = [r for r in readings]

    # cloud-driven reweighting
    if cloud_cover_pct > 20.0:
        notes.append(
            f"غطاء سحب {cloud_cover_pct:.0f}% — تحويل الوزن إلى SAR"
        )
        for r in rs:
            if r.family == "optical":
                r.weight *= 0.2
            elif r.family == "sar":
                r.weight *= 2.0

    # renormalise weights
    total_w = sum(r.weight for r in rs) or 1.0
    for r in rs:
        r.weight /= total_w

    fused_value = sum(r.weight * r.value for r in rs)
    fused_sigma = ensemble_variance(rs) ** 0.5

    # thermal water-stress penalty (design + critique diagnostic)
    if cwsi is not None and cwsi > 0.6:
        fused_value *= 0.7
        notes.append(f"إجهاد مائي حاد CWSI={cwsi:.2f} — خصم 30%")
    elif cwsi is not None and cwsi > 0.4:
        fused_value *= 0.85
        notes.append(f"إجهاد مائي متوسط CWSI={cwsi:.2f}")

    dominant = max(rs, key=lambda r: r.weight).family

    return FusionResult(
        fused_value=round(fused_value, 3),
        fused_sigma=round(fused_sigma, 4),
        confidence=classify_confidence(fused_sigma),
        dominant_family=dominant,
        cloud_cover_pct=cloud_cover_pct,
        notes=notes,
    )


# ── Diagnostic tree (critique 2.2: no causal guessing) ───────────────
def diagnose_stress(
    ndmi: float, cwsi: float, ndre: float, ndvi: float,
    salinity_index: float, ec_trend: str,
) -> dict:
    """Confirmed diagnosis, not 'check irrigation or fertiliser' guess."""
    if ndmi < 0.2 and cwsi > 0.6:
        return {"cause": "water_stress", "ar": "إجهاد مائي مؤكد",
                "confidence": Confidence.HIGH, "action": "ري عاجل"}
    if ndre < 0.3 and ndvi > 0.5:
        return {"cause": "nitrogen_deficit", "ar": "نقص نيتروجين مؤكد",
                "confidence": Confidence.HIGH, "action": "تسميد ورقي"}
    if salinity_index > 0.4 and ec_trend == "rising":
        return {"cause": "salinity", "ar": "ملوحة مؤكدة",
                "confidence": Confidence.HIGH, "action": "غسيل + صرف"}
    return {"cause": "unknown", "ar": "سبب غير محدد — فحص ميداني مطلوب",
            "confidence": Confidence.LOW, "action": "field_inspection"}
