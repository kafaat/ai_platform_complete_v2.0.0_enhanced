"""
api/farm_economics.py — دراسة الجدوى الاقتصاديّة للمحصول

جانب جديد جوهري: المنصّة تقرّر "ماذا يُزرع" (الملاءمة) و"كيف" (الإدارة)، لكن
لا تجيب السؤال الأهمّ للمزارع: **هل سأربح؟** دليل "كيف تكون مزارعاً ناجحاً"
(Wikifarmer) يصرّ أنّ تقدير الجدوى أهمّ قرار، وأنّ إهماله "كارثة اقتصاديّة".

المعادلة (من المقال):
  الإيراد المتوقّع = المساحة (هكتار) × متوسّط الغلّة (طن/هكتار) × سعر السوق (/طن)
  صافي الربح = الإيراد − إجمالي التكاليف
  هامش الربح % = (صافي الربح / الإيراد) × 100

⚠ تقدير إرشادي بمدخلات المزارع المحلّيّة. الأسعار والغلّات تتغيّر — استشر
السوق المحلّي والمزارعين الناجحين والجمعيّات الزراعيّة. توجّه لا يفرض.
مبدأ صريح من المقال: لا تبدأ زراعةً دون معرفة **من سيشتري** و**بأيّ سعر**.
السياق اليمني: ضعف البنية التسويقيّة تحدٍّ — تقدير الجدوى يحمي من خسارة موسم.
"""

from __future__ import annotations

# بنود التكلفة القياسيّة (من المقال) — للإرشاد عند بناء التقدير
_COST_CATEGORIES = [
    {"key": "land_prep", "name_ar": "إعداد التربة (حرث/تسوية/تسميد أساسي)"},
    {"key": "seeds", "name_ar": "البذور/الشتلات"},
    {"key": "irrigation", "name_ar": "الريّ (نظام + ماء + طاقة)"},
    {"key": "fertilizer", "name_ar": "الأسمدة والسماد العضوي"},
    {"key": "protection", "name_ar": "حماية المحصول (مبيدات/شِباك)"},
    {"key": "labor", "name_ar": "العمالة (خاصّةً الحصاد)"},
    {"key": "machinery", "name_ar": "الآلات (بذر/حصاد/إيجار)"},
    {"key": "storage", "name_ar": "التخزين"},
    {"key": "transport", "name_ar": "النقل للسوق"},
    {"key": "insurance", "name_ar": "تأمين المحصول"},
    {"key": "consulting", "name_ar": "استشارات فنّيّة"},
]


def cost_categories() -> dict:
    """بنود التكلفة القياسيّة لبناء تقدير الجدوى."""
    return {
        "categories": _COST_CATEGORIES,
        "note_ar": ("قدّر كلّ بند بأسعار منطقتك. ليست كلّها تنطبق على كلّ محصول — املأ ما يخصّ حالتك."),
    }


def feasibility(
    area_ha: float,
    yield_t_per_ha: float,
    price_per_t: float,
    costs: dict[str, float] | None = None,
    total_cost: float | None = None,
) -> dict:
    """يحسب جدوى المحصول: الإيراد المتوقّع وصافي الربح والهامش.

    مرّر إمّا قاموس التكاليف المفصّل (costs) أو إجماليّاً (total_cost).
    """
    if area_ha <= 0 or yield_t_per_ha < 0 or price_per_t < 0:
        return {"supported": False, "message_ar": "أدخل مساحة وغلّة وسعراً صحيحة."}

    revenue = area_ha * yield_t_per_ha * price_per_t

    breakdown = None
    if costs:
        breakdown = {k: float(v) for k, v in costs.items() if v is not None}
        total = sum(breakdown.values())
    elif total_cost is not None:
        total = float(total_cost)
    else:
        # بلا تكاليف → إيراد فقط (غير مكتمل، نوضّح ذلك)
        return {
            "supported": True,
            "complete": False,
            "area_ha": area_ha,
            "expected_yield_t": round(area_ha * yield_t_per_ha, 2),
            "expected_revenue": round(revenue, 2),
            "message_ar": (
                "حُسب الإيراد المتوقّع فقط. أضف التكاليف لمعرفة صافي الربح — "
                "الإيراد وحده لا يكفي للقرار."
            ),
        }

    net = revenue - total
    margin = (net / revenue * 100) if revenue > 0 else 0.0

    if net > 0 and margin >= 30:
        verdict_ar = "✓ مجدٍ بهامش جيّد — لكن تحقّق من واقعيّة الأسعار والغلّة."
    elif net > 0:
        verdict_ar = "مجدٍ بهامش محدود — الهامش الضيّق يخاطر بأيّ تقلّب في السعر/التكلفة."
    elif net == 0:
        verdict_ar = "⚠ نقطة تعادل — لا ربح ولا خسارة؛ أيّ خطأ يقلب النتيجة لخسارة."
    else:
        verdict_ar = "✗ خسارة متوقّعة — راجع التكاليف أو الغلّة أو السعر أو غيّر المحصول."

    return {
        "supported": True,
        "complete": True,
        "area_ha": area_ha,
        "expected_yield_t": round(area_ha * yield_t_per_ha, 2),
        "expected_revenue": round(revenue, 2),
        "total_cost": round(total, 2),
        "cost_breakdown": breakdown,
        "net_profit": round(net, 2),
        "profit_margin_pct": round(margin, 1),
        "verdict_ar": verdict_ar,
        "principle_ar": (
            "اخترْ أدنى غلّة متوقّعة لا المتوسّط (المبتدئ نادراً يبلغ المتوسّط). "
            "وأهمّ من الربح الورقي: من سيشتري وبأيّ سعر فعليّاً؟"
        ),
        "market_check_ar": (
            "قبل الزراعة: حدّد المشتري، عدد المشترين المحتملين، سعرهم الفعلي، "
            "ووقت شرائهم. لا تزرع دون طلب مؤكّد."
        ),
        "yemen_note_ar": (
            "ضعف البنية التسويقيّة في اليمن تحدٍّ — الجمعيّات الزراعيّة قد تساعد "
            "في التسويق الجماعي. تقدير الجدوى يحمي من خسارة موسم كامل."
        ),
        "disclaimer_ar": (
            "تقدير إرشادي بمدخلاتك. الأسعار والغلّات تتغيّر — استشر السوق "
            "المحلّي والمزارعين الناجحين. توجّه لا يفرض."
        ),
    }


def break_even_price(area_ha: float, yield_t_per_ha: float, total_cost: float) -> dict:
    """سعر التعادل: أدنى سعر/طن يغطّي التكاليف (لا ربح لا خسارة)."""
    total_yield = area_ha * yield_t_per_ha
    if total_yield <= 0:
        return {"supported": False, "message_ar": "أدخل مساحة وغلّة صحيحة."}
    bep = total_cost / total_yield
    return {
        "supported": True,
        "total_yield_t": round(total_yield, 2),
        "break_even_price_per_t": round(bep, 2),
        "advice_ar": (
            f"سعر التعادل ~{round(bep, 2)} للطن. إن كان سعر السوق أعلى منه تربح، "
            "وإن كان أقلّ تخسر. قارنه بالسعر الفعلي قبل الزراعة."
        ),
        "disclaimer_ar": "تقدير إرشادي — السعر الفعلي من السوق المحلّي.",
    }
