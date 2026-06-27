"""Lab sampling and soil/water decision context for SAHOOL.

Pure functions only: no DB, no fabricated values. This module models field sample
points with GPS coordinates and converts soil/water lab results into conservative
agronomic flags that can be consumed by Field State, fertilizer, irrigation and AI
advisor engines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

SampleKind = Literal["soil", "water"]
SampleStatus = Literal["planned", "collected", "submitted", "analyzed", "approved"]


@dataclass(frozen=True)
class GeoSamplePoint:
    sample_id: str
    field_id: str
    kind: SampleKind
    latitude: float
    longitude: float
    sampled_on: date | None = None
    depth_cm_from: int | None = None
    depth_cm_to: int | None = None
    status: SampleStatus = "planned"
    gps_accuracy_m: float | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.sample_id:
            errors.append("sample_id is required")
        if not self.field_id:
            errors.append("field_id is required")
        if not (-90 <= self.latitude <= 90):
            errors.append("latitude out of range")
        if not (-180 <= self.longitude <= 180):
            errors.append("longitude out of range")
        if self.kind == "soil":
            if self.depth_cm_from is None or self.depth_cm_to is None:
                errors.append("soil sample depth range is required")
            elif self.depth_cm_from < 0 or self.depth_cm_to <= self.depth_cm_from:
                errors.append("invalid soil sample depth range")
        if self.gps_accuracy_m is not None and self.gps_accuracy_m < 0:
            errors.append("gps_accuracy_m cannot be negative")
        return errors


@dataclass(frozen=True)
class SoilLabResult:
    sample_id: str
    ph: float | None = None
    ec_dsm: float | None = None
    organic_matter_pct: float | None = None
    nitrogen_mg_kg: float | None = None
    phosphorus_mg_kg: float | None = None
    potassium_mg_kg: float | None = None
    cec_cmol_kg: float | None = None
    calcium_carbonate_pct: float | None = None
    texture: str | None = None
    approved: bool = False


def classify_soil_ph(ph: float | None) -> dict:
    if ph is None:
        return {"class": None, "note_ar": "pH غير مقيس"}
    if ph < 5.5:
        return {"class": "acidic", "note_ar": "حموضة مرتفعة"}
    if ph <= 7.8:
        return {"class": "acceptable", "note_ar": "مقبول لمعظم المحاصيل"}
    if ph <= 8.5:
        return {"class": "alkaline", "note_ar": "قلوية متوسطة"}
    return {"class": "strong_alkaline", "note_ar": "قلوية عالية تحدّ امتصاص العناصر"}


def classify_soil_ec(ec_dsm: float | None) -> dict:
    if ec_dsm is None:
        return {"class": None, "note_ar": "EC غير مقيس"}
    if ec_dsm < 2.0:
        return {"class": "low", "note_ar": "ملوحة منخفضة"}
    if ec_dsm < 4.0:
        return {"class": "moderate", "note_ar": "ملوحة متوسطة — راقب المحصول الحساس"}
    if ec_dsm < 8.0:
        return {"class": "high", "note_ar": "ملوحة مرتفعة — يحتاج إدارة ري وغسيل"}
    return {"class": "severe", "note_ar": "ملوحة شديدة"}


def classify_organic_matter(om: float | None) -> dict:
    if om is None:
        return {"class": None, "note_ar": "المادة العضوية غير مقيسة"}
    if om < 1.0:
        return {"class": "very_low", "note_ar": "منخفضة جداً"}
    if om < 2.0:
        return {"class": "low", "note_ar": "منخفضة"}
    if om <= 4.0:
        return {"class": "adequate", "note_ar": "مقبولة"}
    return {"class": "high", "note_ar": "مرتفعة"}


def analyze_soil_lab_result(result: SoilLabResult) -> dict:
    ph_c = classify_soil_ph(result.ph)
    ec_c = classify_soil_ec(result.ec_dsm)
    om_c = classify_organic_matter(result.organic_matter_pct)
    flags: list[str] = []
    if ph_c["class"] in {"acidic", "strong_alkaline"}:
        flags.append("pH خارج النطاق الملائم")
    if ec_c["class"] in {"high", "severe"}:
        flags.append("ملوحة تربة مرتفعة")
    if om_c["class"] in {"very_low", "low"}:
        flags.append("مادة عضوية منخفضة")
    missing = [
        name
        for name, value in {
            "ph": result.ph,
            "ec_dsm": result.ec_dsm,
            "organic_matter_pct": result.organic_matter_pct,
            "nitrogen_mg_kg": result.nitrogen_mg_kg,
            "phosphorus_mg_kg": result.phosphorus_mg_kg,
            "potassium_mg_kg": result.potassium_mg_kg,
        }.items()
        if value is None
    ]
    return {
        "sample_id": result.sample_id,
        "approved": result.approved,
        "classification": {"ph": ph_c, "salinity_ec": ec_c, "organic_matter": om_c},
        "nutrients": {
            "n_mg_kg": result.nitrogen_mg_kg,
            "p_mg_kg": result.phosphorus_mg_kg,
            "k_mg_kg": result.potassium_mg_kg,
            "cec_cmol_kg": result.cec_cmol_kg,
            "caco3_pct": result.calcium_carbonate_pct,
            "texture": result.texture,
        },
        "hazard_flags_ar": flags,
        "missing_inputs": missing,
        "data_complete": len(missing) == 0,
        "decision_usable": result.approved and len(missing) == 0,
    }


def lab_decision_context(*, soil: dict | None, water: dict | None) -> dict:
    """Merge lab analyses into a conservative decision context.

    Only approved/complete soil lab data is eligible for fertilizer decisions.
    Water data can still inform irrigation risk even if some ions are missing, but
    missing values are explicitly propagated.
    """
    blockers: list[str] = []
    warnings: list[str] = []
    if not soil:
        warnings.append("لا توجد نتيجة تربة مخبرية")
        soil_ready = False
    else:
        soil_ready = bool(soil.get("decision_usable"))
        if not soil.get("approved"):
            blockers.append("نتيجة التربة غير معتمدة")
        warnings.extend(soil.get("hazard_flags_ar") or [])
        if soil.get("missing_inputs"):
            warnings.append("نتيجة التربة ناقصة: " + ",".join(soil["missing_inputs"]))
    if water:
        warnings.extend(water.get("hazard_flags_ar") or [])
        if water.get("missing_inputs"):
            warnings.append("تحليل الماء ناقص: " + ",".join(water["missing_inputs"]))
    else:
        warnings.append("لا يوجد تحليل ماء ري")
    return {
        "soil_lab_ready_for_fertilizer": soil_ready,
        "water_lab_available": water is not None,
        "blockers_ar": blockers,
        "warnings_ar": warnings,
        "recommendation_gate": "allow" if soil_ready and not blockers else "needs_review",
    }
