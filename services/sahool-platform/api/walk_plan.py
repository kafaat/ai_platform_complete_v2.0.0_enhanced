"""
api/walk_plan.py — مولّد خطة المشي للتطبيق اليدوي

خارطة الطريق: المرحلة ١، البند ٩.

يأخذ وصفة (prescriptions.py) + مساحات الزونات + مواصفات المعدّات، ويُنتج
خطة مشي مرتّبة: ترتيب الزونات + الجرعة المحوّلة لكلّ زون + وقت مُقدَّر +
إجمالي المنتج المطلوب — جاهزة للعرض على الموبايل أو التصدير PDF.

الترتيب: من الأقرب/الأسهل إلى الأصعب (PROBLEM أخيراً لأنّها قد تحتاج عناية
خاصّة). pure-logic، قابل للاختبار.

⚠ معدّل العمل (دقائق/هكتار) تقديري ويُمرَّر من المستخدم — ليس ثابتاً علميّاً.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

from api.manual_converter import (
    ApplicationMethod, EquipmentSpec, ManualDose, convert_zone,
)


# ترتيب أولويّة الزونات (الأسهل أوّلاً، PROBLEM أخيراً)
_ZONE_ORDER = {"high": 0, "medium": 1, "low": 2, "problem": 3}

# معدّل عمل افتراضي تقديري (دقائق لكلّ هكتار) — يُمرَّر من المستخدم عادةً
# ⚠ UNVALIDATED DEFAULT — تقدير عملي لا مصدر علمي
DEFAULT_MINUTES_PER_HA = 60.0


@dataclass
class WalkStep:
    """خطوة واحدة في خطة المشي."""
    order: int
    zone_id: str
    zone_class: str
    area_ha: float
    dose: ManualDose
    estimated_minutes: float

    def to_dict(self) -> Dict:
        d = self.dose.to_dict()
        return {
            "order": self.order,
            "zone_id": self.zone_id,
            "zone_class": self.zone_class,
            "area_ha": round(self.area_ha, 3),
            "estimated_minutes": round(self.estimated_minutes, 0),
            "dose": d,
            "instruction_ar": self.dose.instruction_ar,
        }


@dataclass
class WalkPlan:
    """خطة المشي الكاملة لحقل."""
    field_id: str
    crop: str
    method: ApplicationMethod
    product_name_ar: str
    steps: List[WalkStep]
    total_product_kg: float
    total_estimated_minutes: float
    created_at: str
    notes_ar: str = ""

    def to_dict(self) -> Dict:
        return {
            "field_id": self.field_id,
            "crop": self.crop,
            "method": self.method.value,
            "product_name_ar": self.product_name_ar,
            "total_product_kg": round(self.total_product_kg, 2),
            "total_estimated_minutes": round(self.total_estimated_minutes, 0),
            "total_estimated_hours": round(self.total_estimated_minutes / 60, 1),
            "created_at": self.created_at,
            "notes_ar": self.notes_ar,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class ZoneRateInput:
    """مدخل لكلّ zone: المعدّل + المساحة + التصنيف."""
    zone_id: str
    rate_kg_ha: float
    area_ha: float
    zone_class: str = "medium"


def generate_walk_plan(
    field_id: str,
    crop: str,
    zones: List[ZoneRateInput],
    method: ApplicationMethod,
    equip: EquipmentSpec,
    *,
    product_name_ar: str = "السماد",
    minutes_per_ha: float = DEFAULT_MINUTES_PER_HA,
) -> WalkPlan:
    """يبني خطة مشي من معدّلات الزونات.

    Args:
        field_id, crop: سياق الحقل.
        zones: قائمة (zone_id, rate_kg_ha, area_ha, zone_class).
        method: طريقة التطبيق اليدوي.
        equip: مواصفات المعدّات.
        product_name_ar: اسم المنتج (سماد/مبيد...).
        minutes_per_ha: معدّل العمل التقديري.

    Returns:
        WalkPlan مرتّب + بإجماليّات.
    """
    # رتّب: الأسهل أوّلاً، PROBLEM أخيراً
    ordered = sorted(
        zones,
        key=lambda z: _ZONE_ORDER.get(z.zone_class.lower(), 1),
    )

    steps: List[WalkStep] = []
    total_kg = 0.0
    total_minutes = 0.0

    for i, z in enumerate(ordered, start=1):
        dose = convert_zone(z.zone_id, z.rate_kg_ha, z.area_ha, method, equip)
        est_min = z.area_ha * minutes_per_ha
        steps.append(WalkStep(
            order=i,
            zone_id=z.zone_id,
            zone_class=z.zone_class,
            area_ha=z.area_ha,
            dose=dose,
            estimated_minutes=est_min,
        ))
        total_kg += dose.kg_total
        total_minutes += est_min

    notes = (
        f"ابدأ بالمناطق الخصبة (high) وانتهِ بالمناطق المشكلة (problem). "
        f"إجمالي {product_name_ar}: {total_kg:.1f} كغ، "
        f"الوقت المُقدَّر: {total_minutes/60:.1f} ساعة."
    )

    return WalkPlan(
        field_id=field_id,
        crop=crop,
        method=method,
        product_name_ar=product_name_ar,
        steps=steps,
        total_product_kg=total_kg,
        total_estimated_minutes=total_minutes,
        created_at=datetime.now(timezone.utc).isoformat(),
        notes_ar=notes,
    )
