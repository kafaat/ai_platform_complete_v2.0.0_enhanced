"""
sahool_core.crop_inference
===========================
استنباط المحاصيل المرشّحة — يُنتج قائمة مرتّبة، لا قراراً.

القاعدة الذهبية (الوثيقة محقّة): الاستنباط لا يُقرر الزراعة، يُقرر التجريب.
المخرج قائمة مرشّحة (shortlist) يُعاد فحصها ميدانياً، لا أمر زراعة.

يتّكئ على engines.suitability.evaluate_suitability (لا يكرّره): هذا يضيف
طبقة الترتيب متعدّد المحاصيل + سقف صريح + توصية تجريب.

الأبعاد (أوزان أساسية): مناخ 0.35 (يحدّد هل ينمو أصلاً)، تربة 0.30
(الجودة/الملوحة)، ماء 0.20، سوق 0.15. بلا تربة مختبرية → يرتفع وزن
المناخ وينخفض السقف لـ LOW.

الفرق الحاسم بين المحصول والشجرة:
  محصول سنوي: التزام أشهر، مخاطرة منخفضة، سقف MEDIUM، "جرّب 50%".
  شجرة دائمة: التزام 5-20 سنة، مخاطرة عالية، سقف LOW، تتطلّب دراسة.
بلا بيانات تربة عميقة، الأشجار تُحظر (NONE) — القرار طويل الأمد يحتاج بيانات أكثر.
"""

from __future__ import annotations

from dataclasses import dataclass

_CONF_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
_RANK_CONF = {v: k for k, v in _CONF_RANK.items()}


@dataclass
class CropCandidate:
    crop_id: str
    score: float  # 0..1
    confidence: str  # none/low/medium
    is_tree: bool
    recommendation_ar: str  # توصية التجريب (لا قرار)
    note_ar: str = ""


def _min_conf(a: str, b: str) -> str:
    return _RANK_CONF[min(_CONF_RANK[a], _CONF_RANK[b])]


def infer_suitable_crops(
    *,
    crop_scores: list[dict],  # [{crop_id, climate, soil, water, market, is_tree, maturity_days}]
    has_lab_soil: bool,
) -> list[CropCandidate]:
    """يُنتج قائمة محاصيل مرشّحة مرتّبة. لا يُقرر — يقترح التجريب.

    كل عنصر crop_scores يحمل درجات الأبعاد (0..1) المحسوبة مسبقاً
    (climate من GDD، soil من EC/pH أو NDVI، إلخ) ونوع المحصول."""
    # الأوزان: بلا تربة مختبرية يرتفع المناخ وينخفض وزن التربة
    if has_lab_soil:
        w_climate, w_soil, w_water, w_market = 0.30, 0.40, 0.20, 0.10
        base_ceiling = "medium"
    else:
        w_climate, w_soil, w_water, w_market = 0.50, 0.15, 0.20, 0.15
        base_ceiling = "low"

    out: list[CropCandidate] = []
    for c in crop_scores:
        total = (
            c.get("climate", 0.5) * w_climate
            + c.get("soil", 0.5) * w_soil
            + c.get("water", 0.5) * w_water
            + c.get("market", 0.5) * w_market
        )
        is_tree = bool(c.get("is_tree") or (c.get("maturity_days", 0) or 0) > 365)

        # السقف: الأشجار أدنى دائماً (التزام طويل، مخاطرة عالية)
        ceiling = base_ceiling
        if is_tree:
            ceiling = "low" if has_lab_soil else "none"

        # التوصية: تجريب لا قرار — تُربط صراحةً بـ field_trial_design (RCBD)
        # ملاحظة (مراجعة 2026-05-27): "جرّب 20%" دون شاهد لا يكفي علمياً —
        # field_trial_design.design_rcbd يُلزم بشاهد + كتل + تكرار. المزارع
        # يجرّب 20%، لكن التصميم الصارم (لإيقاع المعرفة في الذراع البحثي)
        # يحدث عبر design_rcbd. هذه الواجهة "إشارة تجريب"؛ التصميم منفصل.
        if ceiling == "none":
            rec = "محظور — شجرة دائمة بلا بيانات تربة عميقة (قرار 5-20 سنة يحتاج دراسة)"
        elif is_tree:
            rec = "لا تزرع بلا دراسة تفصيلية — التزام طويل الأمد"
        elif has_lab_soil:
            rec = (
                "مرشّح — جرّب RCBD: قسّم 50% من المساحة لقطعتين متجانستين "
                "(معاملة + شاهد) في 3-4 كتل، وقِس الغلّة"
            )
        else:
            rec = (
                "مرشّح استكشافي — جرّب RCBD مصغّراً: 20% بقطعتين (معاملة + "
                "شاهد) في 3 كتل، أرسل عيّنات تربة مع التجربة"
            )

        # المحاصيل ضعيفة الدرجة تُرفض من القائمة
        if total < 0.55 and not is_tree:
            ceiling = "none"
            rec = "غير مرشّح — الدرجة منخفضة لظروف الموقع"

        out.append(
            CropCandidate(
                crop_id=c["crop_id"],
                score=round(total, 3),
                confidence=ceiling,
                is_tree=is_tree,
                recommendation_ar=rec,
                note_ar=("قائمة مرشّحة لا قرار — الفحص الميداني والمزارع يقرّران"),
            )
        )

    return sorted(out, key=lambda x: x.score, reverse=True)
