"""أداة: حاسبة تغطية الريّ المحوريّ (center pivot) — نقيّة حتميّة.

المحور المركزيّ يروي قرصاً نصف قطره طول الذراع. مع مدفع طرفيّ (end-gun) يزيد نصف
القطر الفعّال. تُرجِع المساحة المرويّة (هكتار)، ونسبة تغطية حقل مربّع مُحيط، والزوايا
الميتة (الأركان غير المرويّة) — أرقام يحتاجها مهندس الريّ يوميّاً.
"""

from __future__ import annotations

import math

from ..registry import Tool, ToolParam, register

_M2_PER_HA = 10_000.0


def compute(inp: dict) -> dict:
    radius_m = inp["radius_m"]
    end_gun_m = inp["end_gun_m"] or 0.0
    effective_r = radius_m + end_gun_m

    irrigated_m2 = math.pi * effective_r**2
    # الحقل المربّع المُحيط بأصغر قدر يسع الدائرة: ضلعه = القُطر الفعّال.
    bounding_field_m2 = (2 * effective_r) ** 2
    coverage_ratio = irrigated_m2 / bounding_field_m2 if bounding_field_m2 else 0.0
    dead_corners_m2 = bounding_field_m2 - irrigated_m2

    return {
        "effective_radius_m": round(effective_r, 2),
        "irrigated_area_ha": round(irrigated_m2 / _M2_PER_HA, 4),
        "bounding_field_ha": round(bounding_field_m2 / _M2_PER_HA, 4),
        "coverage_ratio": round(coverage_ratio, 4),  # = π/4 ≈ 0.785 (دائرة داخل مربّع)
        "dead_corner_area_ha": round(dead_corners_m2 / _M2_PER_HA, 4),
        "perimeter_m": round(2 * math.pi * effective_r, 2),
    }


register(
    Tool(
        id="pivot_coverage",
        name_ar="حاسبة تغطية الريّ المحوريّ",
        category="irrigation",
        description_ar="مساحة الريّ ونسبة تغطية الحقل والأركان الميتة لمحور مركزيّ بذراع ومدفع طرفيّ.",
        params=[
            ToolParam("radius_m", "number", "طول الذراع", unit="م", min=1, max=1000),
            ToolParam(
                "end_gun_m",
                "number",
                "مدى المدفع الطرفيّ",
                unit="م",
                required=False,
                default=0.0,
                min=0,
                max=200,
            ),
        ],
        compute=compute,
        result_unit_ar="هكتار / نسبة",
        tags=("ريّ", "محور", "تغطية"),
    )
)
