"""
api/manual_converter.py — محوّل وحدات التطبيق اليدوي

خارطة الطريق: المرحلة ١، البند ٩ (وضع التطبيق اليدوي).

المشكلة: prescriptions.py يُخرج kg/ha — رقم بلا معنى لمزارع يمني يطبّق بيده.
الحل: تحويل الجرعة إلى وحدات قابلة للتنفيذ:
  • كغ لكلّ مصطبة/قطعة (terrace)
  • أغطية/مكاييل لكلّ خزّان رشّ ظهري (caps per tank)
  • ري/سقايات لكلّ شجرة (watering cans per tree)

المعادلات الأساسيّة (هندسيّة بحتة، لا ثوابت زراعيّة):
  kg_per_terrace          = rate_kg_ha × terrace_area_m2 / 10,000
  caps_for_terrace        = kg_per_terrace / cap_weight_kg
  watering_cans_per_tree  = rate_kg_ha × tree_spacing_m2
                            / (10,000 × can_capacity_l × concentration_kg_l)

(1 هكتار = 10,000 م²)

⚠ القيم الافتراضيّة للمعدّات (وزن الغطاء، سعة الخزّان) تقديريّة وتُمرَّر من
المستخدم؛ المعادلات نفسها صحيحة هندسيّاً (تحويل وحدات لا أكثر).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class ApplicationMethod(str, Enum):
    """طريقة التطبيق اليدوي."""
    BROADCAST_TERRACE = "broadcast_terrace"   # نثر يدوي على مصطبة/قطعة
    BACKPACK_SPRAY = "backpack_spray"         # رشّ ظهري (خزّان)
    PER_TREE = "per_tree"                     # لكلّ شجرة (سقاية/جرعة)


# ثوابت هندسيّة (ليست زراعيّة — تحويل وحدات صرف)
M2_PER_HECTARE = 10_000.0


@dataclass
class EquipmentSpec:
    """مواصفات المعدّات اليدويّة (يُدخلها المستخدم — ليست ثوابت علميّة)."""
    # للنثر على مصطبة
    terrace_area_m2: Optional[float] = None       # مساحة المصطبة الواحدة
    # للرشّ الظهري
    cap_weight_kg: Optional[float] = None         # وزن الغطاء/المكيال (كمعيار جرعة)
    tank_capacity_l: Optional[float] = None       # سعة الخزّان (لتر)
    # للأشجار
    tree_spacing_m2: Optional[float] = None       # المساحة المخصّصة لكلّ شجرة
    can_capacity_l: Optional[float] = None        # سعة السقاية (لتر)
    concentration_kg_l: Optional[float] = None    # تركيز المحلول (كغ منتج/لتر)


@dataclass
class ManualDose:
    """الجرعة اليدويّة المحوّلة لزون واحدة."""
    zone_id: str
    rate_kg_ha: float
    method: ApplicationMethod
    # المخرجات المحوّلة (حسب الطريقة)
    kg_total: float                               # إجمالي الكمّيّة للزون
    kg_per_terrace: Optional[float] = None
    terraces_count: Optional[float] = None
    caps_per_terrace: Optional[float] = None
    tanks_needed: Optional[float] = None
    watering_cans_per_tree: Optional[float] = None
    trees_count: Optional[float] = None
    instruction_ar: str = ""

    def to_dict(self) -> Dict:
        return {
            "zone_id": self.zone_id,
            "rate_kg_ha": round(self.rate_kg_ha, 2),
            "method": self.method.value,
            "kg_total": round(self.kg_total, 3),
            "kg_per_terrace": round(self.kg_per_terrace, 3) if self.kg_per_terrace is not None else None,
            "terraces_count": round(self.terraces_count, 1) if self.terraces_count is not None else None,
            "caps_per_terrace": round(self.caps_per_terrace, 1) if self.caps_per_terrace is not None else None,
            "tanks_needed": round(self.tanks_needed, 1) if self.tanks_needed is not None else None,
            "watering_cans_per_tree": round(self.watering_cans_per_tree, 2) if self.watering_cans_per_tree is not None else None,
            "trees_count": round(self.trees_count, 0) if self.trees_count is not None else None,
            "instruction_ar": self.instruction_ar,
        }


def kg_per_terrace(rate_kg_ha: float, terrace_area_m2: float) -> float:
    """كغ المنتج لمصطبة واحدة = المعدّل × مساحة المصطبة / 10000."""
    return rate_kg_ha * terrace_area_m2 / M2_PER_HECTARE


def convert_zone(
    zone_id: str,
    rate_kg_ha: float,
    zone_area_ha: float,
    method: ApplicationMethod,
    equip: EquipmentSpec,
) -> ManualDose:
    """يحوّل جرعة zone من kg/ha إلى وحدات يدويّة قابلة للتنفيذ.

    يرفع ValueError لو المعدّات المطلوبة للطريقة ناقصة.
    """
    kg_total = rate_kg_ha * zone_area_ha  # kg/ha × ha = kg

    dose = ManualDose(
        zone_id=zone_id, rate_kg_ha=rate_kg_ha,
        method=method, kg_total=kg_total,
    )

    if method == ApplicationMethod.BROADCAST_TERRACE:
        if not equip.terrace_area_m2 or equip.terrace_area_m2 <= 0:
            raise ValueError("النثر على مصطبة يحتاج مساحة المصطبة (terrace_area_m2)")
        per_terrace = kg_per_terrace(rate_kg_ha, equip.terrace_area_m2)
        zone_area_m2 = zone_area_ha * M2_PER_HECTARE
        terraces = zone_area_m2 / equip.terrace_area_m2
        dose.kg_per_terrace = per_terrace
        dose.terraces_count = terraces
        # لو وزن الغطاء معطى، نحوّل لأغطية (أسهل للمزارع)
        if equip.cap_weight_kg and equip.cap_weight_kg > 0:
            dose.caps_per_terrace = per_terrace / equip.cap_weight_kg
            dose.instruction_ar = (
                f"انثر {dose.caps_per_terrace:.1f} غطاء على كلّ مصطبة "
                f"({terraces:.0f} مصطبة)"
            )
        else:
            dose.instruction_ar = (
                f"انثر {per_terrace:.2f} كغ على كلّ مصطبة ({terraces:.0f} مصطبة)"
            )

    elif method == ApplicationMethod.BACKPACK_SPRAY:
        if not equip.tank_capacity_l or equip.tank_capacity_l <= 0:
            raise ValueError("الرشّ الظهري يحتاج سعة الخزّان (tank_capacity_l)")
        # عدد الخزّانات = إجمالي المحلول المطلوب / سعة الخزّان.
        # نفترض أنّ المنتج يُذاب بتركيز concentration_kg_l (يُدخله المستخدم).
        if equip.concentration_kg_l and equip.concentration_kg_l > 0:
            total_solution_l = kg_total / equip.concentration_kg_l
            dose.tanks_needed = total_solution_l / equip.tank_capacity_l
            # أغطية المنتج لكلّ خزّان (لو وزن الغطاء معطى)
            kg_per_tank = equip.tank_capacity_l * equip.concentration_kg_l
            if equip.cap_weight_kg and equip.cap_weight_kg > 0:
                dose.caps_per_terrace = kg_per_tank / equip.cap_weight_kg  # caps per tank
                dose.instruction_ar = (
                    f"ضع {dose.caps_per_terrace:.1f} غطاء في كلّ خزّان، "
                    f"وارشّ {dose.tanks_needed:.1f} خزّان"
                )
            else:
                dose.instruction_ar = (
                    f"ضع {kg_per_tank:.2f} كغ في كلّ خزّان، "
                    f"وارشّ {dose.tanks_needed:.1f} خزّان"
                )
        else:
            raise ValueError("الرشّ الظهري يحتاج تركيز المحلول (concentration_kg_l)")

    elif method == ApplicationMethod.PER_TREE:
        if not equip.tree_spacing_m2 or equip.tree_spacing_m2 <= 0:
            raise ValueError("التطبيق لكلّ شجرة يحتاج مساحة الشجرة (tree_spacing_m2)")
        zone_area_m2 = zone_area_ha * M2_PER_HECTARE
        trees = zone_area_m2 / equip.tree_spacing_m2
        kg_per_tree = rate_kg_ha * equip.tree_spacing_m2 / M2_PER_HECTARE
        dose.trees_count = trees
        if equip.can_capacity_l and equip.can_capacity_l > 0 and equip.concentration_kg_l and equip.concentration_kg_l > 0:
            # سقايات لكلّ شجرة = كغ للشجرة / (سعة السقاية × التركيز)
            dose.watering_cans_per_tree = kg_per_tree / (equip.can_capacity_l * equip.concentration_kg_l)
            dose.instruction_ar = (
                f"اسقِ {dose.watering_cans_per_tree:.2f} سقاية لكلّ شجرة "
                f"({trees:.0f} شجرة)"
            )
        else:
            dose.instruction_ar = (
                f"ضع {kg_per_tree:.3f} كغ لكلّ شجرة ({trees:.0f} شجرة)"
            )

    return dose
