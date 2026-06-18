"""أداة: حاسبة احتياج الأسمدة (N/P/K) — نقيّة حتميّة.

تحسب الكمّيّة العمليّة من السماد التجاريّ (كغ/هكتار) اللازمة لتلبية احتياج المحصول من
عنصر غذائيّ، انطلاقاً من الغلّة المستهدفة ومعامل الامتصاص، بعد خصم إمداد التربة وتعديل
كفاءة استخدام السماد ونسبة العنصر في المنتج التجاريّ — أرقام يحتاجها مهندس التغذية يوميّاً.
"""

from __future__ import annotations

from ..registry import Tool, ToolParam, register


def compute(inp: dict) -> dict:
    target_yield_t_ha = inp["target_yield_t_ha"]
    uptake_kg_per_t = inp["uptake_kg_per_t"]
    soil_supply_kg_ha = inp["soil_supply_kg_ha"] or 0.0
    fertilizer_grade_pct = inp["fertilizer_grade_pct"]
    use_efficiency = inp["use_efficiency"] or 0.7

    # احتياج المحصول الكلّيّ من العنصر = الغلّة × الامتصاص لكلّ طنّ.
    crop_demand_kg_ha = target_yield_t_ha * uptake_kg_per_t
    # الصافي بعد خصم إمداد التربة (لا يقلّ عن صفر — التربة لا "تأخذ" سماداً).
    net_nutrient_kg_ha = max(0.0, crop_demand_kg_ha - soil_supply_kg_ha)
    # تعويض كفاءة الاستخدام (جزء من السماد يُفقَد/لا يُمتَصّ).
    nutrient_to_apply_kg_ha = net_nutrient_kg_ha / use_efficiency
    # تحويل كمّيّة العنصر إلى كمّيّة المنتج التجاريّ حسب نسبة العنصر فيه.
    product_kg_ha = nutrient_to_apply_kg_ha / (fertilizer_grade_pct / 100.0)

    return {
        "crop_demand_kg_ha": round(crop_demand_kg_ha, 2),
        "net_nutrient_kg_ha": round(net_nutrient_kg_ha, 2),
        "nutrient_to_apply_kg_ha": round(nutrient_to_apply_kg_ha, 2),
        "product_kg_ha": round(product_kg_ha, 2),
    }


register(
    Tool(
        id="fertilizer_requirement",
        name_ar="حاسبة احتياج الأسمدة (N/P/K)",
        category="nutrition",
        description_ar=(
            "كمّيّة السماد التجاريّ (كغ/هكتار) لتلبية احتياج المحصول من عنصر غذائيّ، "
            "بعد خصم إمداد التربة وتعديل الكفاءة ونسبة العنصر في المنتج."
        ),
        params=[
            ToolParam(
                "target_yield_t_ha",
                "number",
                "الغلّة المستهدفة",
                unit="طن/هكتار",
                min=0,
            ),
            ToolParam(
                "uptake_kg_per_t",
                "number",
                "امتصاص العنصر لكلّ طنّ غلّة",
                unit="كغ/طن",
                min=0,
            ),
            ToolParam(
                "soil_supply_kg_ha",
                "number",
                "إمداد التربة",
                unit="كغ/هكتار",
                required=False,
                default=0.0,
                min=0,
            ),
            ToolParam(
                "fertilizer_grade_pct",
                "number",
                "نسبة العنصر في السماد",
                unit="%",
                min=1,
                max=100,
            ),
            ToolParam(
                "use_efficiency",
                "number",
                "كفاءة استخدام السماد (0..1)",
                required=False,
                default=0.7,
                min=0.1,
                max=1.0,
            ),
        ],
        compute=compute,
        result_unit_ar="كغ/هكتار",
        tags=("تغذية", "أسمدة", "NPK"),
    )
)
