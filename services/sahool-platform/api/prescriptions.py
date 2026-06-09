"""
services/sahool-platform/api/prescriptions.py — Variable Rate Prescriptions

المرجع:
  FieldView Quick Start Guide:
    - Seed Scripting
    - Fertility Scripts (N/P/K + lime)
    - Crop Protection Plans
    - Enhanced Scripting
    - Easy Export (Shapefile/CSV)

كيف يختلف منهجنا عن FieldView:
  FieldView يبني على "أكثر من مليون قطعة تجريبيّة" — لا يوجد في اليمن.
  بدلاً منه: zone-based recipes من:
    ١. تحاليل التربة المختبريّة (lab samples حقيقيّة)
    ٢. NDVI zones (high/med/low من الأقمار)
    ٣. Soil texture + depth (من SoilFormScreen)
    ٤. Crop water/nutrient requirements (موسوعة كتب زراعيّة)

النتيجة: 5 zones × 3 inputs (seed/N/P/K) = prescription map.

ملاحظة منهجيّة (صادقة):
  هذا ليس "AI prescriptions". هذه قواعد agronomic + lab data + remote sensing.
  لا نحتاج ML model لتقول "المنطقة الأفقر تحتاج نيتروجين أكثر" — هذه قاعدة
  زراعيّة مُؤسَّسة منذ ١٠٠ سنة. الـAI زيادة لاحقة، ليست الأساس.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


# ─── Types ──────────────────────────────────────────────────────

class PrescriptionType(str, Enum):
    SEED = "seed"
    NITROGEN = "nitrogen"
    PHOSPHORUS = "phosphorus"
    POTASSIUM = "potassium"
    LIME = "lime"
    HERBICIDE = "herbicide"
    FUNGICIDE = "fungicide"
    INSECTICIDE = "insecticide"


class ZoneClass(str, Enum):
    """Zone classification based on NDVI + soil indicators."""
    LOW = "low"           # NDVI < 0.4، تربة فقيرة
    MEDIUM = "medium"     # NDVI 0.4-0.6، متوسّط
    HIGH = "high"         # NDVI > 0.6، خصب
    PROBLEM = "problem"   # ملوحة عالية أو pH متطرّف


@dataclass
class ZoneCharacteristics:
    """ما نعرفه عن zone واحدة."""
    zone_id: str
    zone_class: ZoneClass
    area_ha: float
    ndvi_mean: Optional[float] = None
    soil_ph: Optional[float] = None
    soil_ec: Optional[float] = None         # ملوحة dS/m
    soil_om: Optional[float] = None         # عضويّة %
    soil_n_ppm: Optional[float] = None
    soil_p_ppm: Optional[float] = None
    soil_k_ppm: Optional[float] = None
    soil_texture: Optional[str] = None      # "sandy", "loamy", "clayey"
    soil_depth_cm: Optional[int] = None


@dataclass
class ZonePrescription:
    """التطبيق الموصى به لكل zone."""
    zone_id: str
    rate: float                              # kg/ha أو seeds/m²
    unit: str                                # "kg/ha", "seeds/m2", "L/ha"
    confidence: float                        # 0-1
    rationale_ar: str                        # لماذا هذه القيمة بالعربيّة
    rationale_en: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class Prescription:
    """الوصفة الكاملة لحقل."""
    field_id: str
    prescription_type: PrescriptionType
    crop: str                                # "wheat", "tomato", إلخ
    season_id: str
    zones: List[ZonePrescription]
    total_amount: float                      # إجمالي كل الـzones
    total_amount_unit: str
    average_rate: float
    created_at: str
    notes_ar: str = ""


# ─── Knowledge Base (agronomic rules) ───────────────────────────

# مرجع: FAO + الكتب الزراعيّة اليمنيّة + EUROSTAT
# الجرعات: kg/ha من النيتروجين الفعّال (N)
# ⚠ UNVALIDATED DEFAULT — needs agronomist review (جلسة التصحيح الذاتي)
# القيم أدناه تقديريّة ومنطقيّة لكنّها لم تُتحقَّق من مصدر علمي/ميداني موثَّق.
# يجب مراجعتها مع مهندس زراعي يمني قبل الاعتماد عليها في قرارات حقيقيّة.
CROP_BASE_NITROGEN = {
    "wheat":     {"low": 80,  "medium": 120, "high": 150},
    "barley":    {"low": 60,  "medium": 90,  "high": 110},
    "corn":      {"low": 120, "medium": 180, "high": 220},
    "tomato":    {"low": 150, "medium": 200, "high": 250},
    "potato":    {"low": 120, "medium": 160, "high": 200},
    "onion":     {"low": 100, "medium": 130, "high": 160},
    "cotton":    {"low": 100, "medium": 140, "high": 180},
    "alfalfa":   {"low": 30,  "medium": 50,  "high": 60},
    "sorghum":   {"low": 60,  "medium": 90,  "high": 120},
}

# Phosphorus (P2O5 kg/ha)
CROP_BASE_PHOSPHORUS = {
    "wheat":     {"low": 60,  "medium": 80,  "high": 100},
    "tomato":    {"low": 100, "medium": 140, "high": 180},
    "corn":      {"low": 70,  "medium": 100, "high": 130},
    "alfalfa":   {"low": 80,  "medium": 120, "high": 150},
}

# Potassium (K2O kg/ha)
CROP_BASE_POTASSIUM = {
    "wheat":     {"low": 40,  "medium": 60,  "high": 80},
    "tomato":    {"low": 150, "medium": 200, "high": 280},
    "corn":      {"low": 60,  "medium": 90,  "high": 120},
}

# Seeding rates (seeds/m² لمعظم الحبوب، plants/m² للخضار)
CROP_BASE_SEEDING = {
    "wheat":     {"low": 350, "medium": 450, "high": 550},   # seeds/m²
    "barley":    {"low": 300, "medium": 400, "high": 500},
    "corn":      {"low": 5,   "medium": 7,   "high": 9},      # plants/m²
    "tomato":    {"low": 2.5, "medium": 3,   "high": 3.5},
    "sorghum":   {"low": 12,  "medium": 18,  "high": 24},
}


# ─── Generators ─────────────────────────────────────────────────

class PrescriptionGenerator:
    """يولّد prescriptions zone-based."""

    def __init__(self):
        pass

    def generate_nitrogen(
        self,
        field_id: str,
        season_id: str,
        crop: str,
        zones: List[ZoneCharacteristics],
    ) -> Prescription:
        """N prescription حسب الزون + tests."""
        crop = crop.lower()
        base_rates = CROP_BASE_NITROGEN.get(crop)
        if not base_rates:
            raise ValueError(f"crop '{crop}' not in knowledge base for nitrogen")

        zone_rxs: List[ZonePrescription] = []
        total_n = 0.0

        for zone in zones:
            zclass = self._zone_to_class(zone)
            # PROBLEM zone: تبدأ من "low" rate ثمّ تتعدّل
            base_key = zclass.value if zclass.value in base_rates else "low"
            base = base_rates[base_key]
            rate = float(base)
            warnings: List[str] = []
            adjustments: List[str] = []
            confidence = 0.75    # baseline من crop tables

            # تعديل ١: لو لدينا N test (لاب) — هذا أدقّ
            if zone.soil_n_ppm is not None:
                # Rule of thumb: 1 ppm N ≈ 4 kg/ha في top 30cm
                existing_n_kg = zone.soil_n_ppm * 4.0
                required_total = base + 30  # crop need + buffer
                rate = max(20, required_total - existing_n_kg)
                adjustments.append(f"خُصِم ٤×{zone.soil_n_ppm}={existing_n_kg:.0f} kg/ha من الفحص")
                confidence = 0.90    # ثقة أعلى مع lab data

            # تعديل ٢: لو منطقة "problem" (ملوحة)، خفّض
            if zone.zone_class == ZoneClass.PROBLEM:
                if zone.soil_ec and zone.soil_ec > 4.0:
                    rate *= 0.7
                    warnings.append(f"خُفّض ٣٠٪ بسبب ملوحة عالية ({zone.soil_ec} dS/m)")

            # تعديل ٣: لو OM عالٍ، خفّض
            if zone.soil_om and zone.soil_om > 3.0:
                rate *= 0.85
                adjustments.append(f"خُفّض ١٥٪ بسبب مادّة عضويّة عالية ({zone.soil_om}%)")

            # تعديل ٤: تربة رمليّة → split application warning
            if zone.soil_texture == "sandy":
                warnings.append("تربة رمليّة: قسّم الجرعة على ٢-٣ مرّات لتجنّب الـleaching")

            rate = round(rate, 1)
            total_n += rate * zone.area_ha

            rationale_parts = [f"محصول {crop} في منطقة {zclass.value}: أساس {base} kg/ha"]
            rationale_parts.extend(adjustments)

            zone_rxs.append(ZonePrescription(
                zone_id=zone.zone_id,
                rate=rate,
                unit="kg/ha (N)",
                confidence=round(confidence, 2),
                rationale_ar=" · ".join(rationale_parts),
                rationale_en=f"crop:{crop} zone:{zclass.value}",
                warnings=warnings,
            ))

        return Prescription(
            field_id=field_id,
            prescription_type=PrescriptionType.NITROGEN,
            crop=crop,
            season_id=season_id,
            zones=zone_rxs,
            total_amount=round(total_n, 1),
            total_amount_unit="kg N",
            # M1 FIX: احرس المساحة الكليّة لا مجرّد وجود zones — مناطق بمساحة 0 تقسم على صفر.
            average_rate=round(total_n / _total_area, 1) if (_total_area := sum(z.area_ha for z in zones)) > 0 else 0,
            created_at=_now_iso(),
            notes_ar="تطبيق متغيّر — راجع الـzones قبل التنفيذ. قد تحتاج تحاليل تربة حديثة للزونات الفقيرة.",
        )

    def generate_seeding(
        self,
        field_id: str,
        season_id: str,
        crop: str,
        zones: List[ZoneCharacteristics],
    ) -> Prescription:
        """Seeding rate (variable seeding) — أعلى في الـzones الخصبة."""
        crop = crop.lower()
        base_rates = CROP_BASE_SEEDING.get(crop)
        if not base_rates:
            raise ValueError(f"crop '{crop}' not in knowledge base for seeding")

        zone_rxs: List[ZonePrescription] = []
        total = 0.0

        for zone in zones:
            zclass = self._zone_to_class(zone)
            base_key = zclass.value if zclass.value in base_rates else "low"
            base = base_rates[base_key]
            rate = float(base)
            warnings: List[str] = []

            # تعديل: shallow soil → خفّض
            if zone.soil_depth_cm and zone.soil_depth_cm < 30:
                rate *= 0.8
                warnings.append("تربة ضحلة: خُفّضت الكثافة ٢٠٪")

            # تعديل: تربة طينيّة ثقيلة → خفّض قليلاً
            if zone.soil_texture == "clayey":
                rate *= 0.92

            rate = round(rate, 2)
            zone_rxs.append(ZonePrescription(
                zone_id=zone.zone_id,
                rate=rate,
                unit="seeds/m²" if crop in {"wheat", "barley"} else "plants/m²",
                confidence=0.78,
                rationale_ar=f"محصول {crop}، منطقة {zclass.value}",
                rationale_en=f"{crop}/{zclass.value}",
                warnings=warnings,
            ))
            total += rate * zone.area_ha * 10000  # m² → ha

        return Prescription(
            field_id=field_id,
            prescription_type=PrescriptionType.SEED,
            crop=crop,
            season_id=season_id,
            zones=zone_rxs,
            total_amount=round(total, 0),
            total_amount_unit="seeds",
            # M1 FIX: احرس المساحة الكليّة (مناطق بمساحة 0 ⇒ قسمة على صفر).
            average_rate=round(total / (_area_m2), 2) if (_area_m2 := sum(z.area_ha for z in zones) * 10000) > 0 else 0,
            created_at=_now_iso(),
            notes_ar="كثافة بذر متغيّرة. الـzones الخصبة تستوعب كثافة أعلى.",
        )

    def _zone_to_class(self, zone: ZoneCharacteristics) -> ZoneClass:
        """Decision: ما تصنيف هذه الـzone؟"""
        # explicit override
        if zone.zone_class != ZoneClass.MEDIUM:
            return zone.zone_class

        # infer من NDVI لو متوفّر
        if zone.ndvi_mean is not None:
            if zone.ndvi_mean < 0.4:
                return ZoneClass.LOW
            elif zone.ndvi_mean > 0.65:
                return ZoneClass.HIGH

        # problem detection
        if zone.soil_ec and zone.soil_ec > 4.0:
            return ZoneClass.PROBLEM
        if zone.soil_ph and (zone.soil_ph < 5.5 or zone.soil_ph > 8.5):
            return ZoneClass.PROBLEM

        return ZoneClass.MEDIUM


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ─── Export to CSV / Shapefile (FieldView "Easy Export") ────────

def prescription_to_csv(prescription: Prescription) -> str:
    """تحويل لـCSV قابل للتحميل لمعدّات الـapplicator."""
    lines = [
        f"# SAHOOL Prescription · {prescription.prescription_type.value}",
        f"# Field: {prescription.field_id}",
        f"# Crop: {prescription.crop}",
        f"# Season: {prescription.season_id}",
        f"# Generated: {prescription.created_at}",
        f"# Total: {prescription.total_amount} {prescription.total_amount_unit}",
        "",
        "zone_id,rate,unit,confidence,rationale_en",
    ]
    for z in prescription.zones:
        # CSV-safe (no commas in rationale)
        rationale = z.rationale_en.replace(",", ";")
        lines.append(f"{z.zone_id},{z.rate},{z.unit},{z.confidence},{rationale}")
    return "\n".join(lines)


def prescription_to_dict(prescription: Prescription) -> Dict:
    """JSON-friendly dict (للـAPI response)."""
    return {
        "field_id": prescription.field_id,
        "prescription_type": prescription.prescription_type.value,
        "crop": prescription.crop,
        "season_id": prescription.season_id,
        "total_amount": prescription.total_amount,
        "total_amount_unit": prescription.total_amount_unit,
        "average_rate": prescription.average_rate,
        "created_at": prescription.created_at,
        "notes_ar": prescription.notes_ar,
        "zones": [
            {
                "zone_id": z.zone_id,
                "rate": z.rate,
                "unit": z.unit,
                "confidence": z.confidence,
                "rationale_ar": z.rationale_ar,
                "warnings": z.warnings,
            }
            for z in prescription.zones
        ],
    }
