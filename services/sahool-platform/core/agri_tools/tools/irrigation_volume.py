"""أداة: حاسبة حجم مياه الريّ — نقيّة حتميّة.

تحسب حجم الماء اللازم لريّ مساحة بعمقٍ مُعطى. القاعدة الزراعيّة الأساسيّة: عمق 1 مم
من الماء فوق هكتار واحد = 10 م³. الحجم الصافي هو احتياج المحصول، والحجم الإجماليّ
يضيف فاقد النظام عبر كفاءة الريّ. كما تُقدّر زمن التشغيل من معدّل التدفّق.
"""

from __future__ import annotations

from ..registry import Tool, ToolParam, register

# عمق 1 مم على هكتار واحد = 10 م³.
_M3_PER_MM_HA = 10.0
_LITERS_PER_M3 = 1000.0


def compute(inp: dict) -> dict:
    depth_mm = inp["depth_mm"]
    area_ha = inp["area_ha"]
    efficiency = inp["efficiency"]
    flow_rate_m3h = inp["flow_rate_m3h"] or 0.0

    net_volume_m3 = depth_mm * area_ha * _M3_PER_MM_HA
    gross_volume_m3 = net_volume_m3 / efficiency
    net_volume_liters = net_volume_m3 * _LITERS_PER_M3
    run_time_hours = gross_volume_m3 / flow_rate_m3h if flow_rate_m3h > 0 else None

    return {
        "net_volume_m3": round(net_volume_m3, 2),
        "gross_volume_m3": round(gross_volume_m3, 2),
        "net_volume_liters": round(net_volume_liters, 1),
        "run_time_hours": round(run_time_hours, 2) if run_time_hours is not None else None,
    }


register(
    Tool(
        id="irrigation_volume",
        name_ar="حاسبة حجم مياه الريّ",
        category="irrigation",
        description_ar="حجم مياه الريّ الصافي والإجماليّ (مع كفاءة النظام) وزمن التشغيل من معدّل التدفّق.",
        params=[
            ToolParam("depth_mm", "number", "عمق الريّ", unit="مم", min=0),
            ToolParam("area_ha", "number", "المساحة", unit="هكتار", min=0),
            ToolParam(
                "efficiency",
                "number",
                "كفاءة الريّ (0..1)",
                required=False,
                default=0.85,
                min=0.1,
                max=1.0,
            ),
            ToolParam(
                "flow_rate_m3h",
                "number",
                "معدّل التدفّق",
                unit="م³/ساعة",
                required=False,
                default=0,
                min=0,
            ),
        ],
        compute=compute,
        result_unit_ar="م³ / لتر / ساعة",
        tags=("ريّ", "حجم", "ماء"),
    )
)
