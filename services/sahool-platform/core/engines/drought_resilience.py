"""core/engines/drought_resilience.py — درجة تحمّل الجفاف المركّبة من صفات موثّقة.

الفكرة (مُستلهَمة من مبدأ TRY في المرفق — "كيف يعمل النبات أهمّ ممّا هو"، لا من
بياناتها): المرفق يقترح Trait Intelligence Module بصفات مخترعة (WUE=0.62،
SLA=18.2 — أرقام بلا مصدر لمحاصيل اليمن). الصواب: **اجمع صفات سهول الموثّقة
الموجودة فعلاً** في درجة تحمّل جفاف مركّبة، دون اختراع أرقام TRY.

الفجوة المسدودة: الصفات موجودة لكن **متفرّقة** (root_depth في
soil_moisture_advisor، thermal في البطاقات، threshold_ece في الملوحة) — لا
درجة مركّبة واحدة تقارن تحمّل المحاصيل للجفاف/الحرارة.

⚠ المبدأ (صدق صارم):
  • **من صفات موثّقة فقط**: root_depth (مرجعيّة الريّ)، flowering_safe_max_c
    (البطاقات)، threshold_ece (Maas-Hoffman) — لا WUE/SLA مخترعة
  • درجة استرشاديّة للمقارنة، لا رقم مطلق
  • الحرارة منفصلة عن الجفاف (نقطة المرفق الصحيحة: قد تكون الحرارة أخطر)
  • شفّاف: يُظهر مكوّنات الدرجة ومصدرها
  • لا يستبدل القرار الفيزيائي (ميزان الماء) — يضيف بُعد المقارنة بين المحاصيل

⚠ ليس استيراد TRY. لو توفّرت صفات TRY موثّقة لمحصول لاحقاً (root_depth قياسي،
WUE مقيس)، تُضاف للبطاقة بمصدرها — لكن لا نخترعها الآن.

المصادر: root_depth (soil_moisture_advisor، FAO-56)؛ thermal (بطاقات سهول)؛
threshold_ece (Maas-Hoffman في البطاقات). العتبات للمقارنة النسبيّة لا المطلقة.
"""

from __future__ import annotations

from dataclasses import dataclass

# عمق الجذور المرجعي (من soil_moisture_advisor — موثّق). أعمق = أصمد للجفاف.
ROOT_DEPTH_M = {
    "wheat": 1.2,
    "barley": 1.2,
    "maize": 1.0,
    "millet": 1.0,
    "sorghum": 1.5,
    "potato": 0.5,
    "tomato": 0.9,
    "onion": 0.4,
    "alfalfa": 1.5,
    "olive": 1.5,
    "citrus": 1.2,
    "grape": 1.2,
}
DEEP_ROOT_REF_M = 1.5  # مرجع التطبيع (أعمق جذور شائعة)

# حدّ حرارة الإزهار الآمن. القيم المُحقّقة من بطاقات سهول الموثّقة
# (core/crop_cards/*.yaml: wheat=31، barley=30، sorghum=38، millet=40)؛ وبقيّتها
# من مراجع زراعيّة قياسيّة حتى تُضاف بطاقاتها (لا بطاقة لها بعد في هذا المستودع).
FLOWERING_SAFE_MAX_C = {
    "wheat": 31.0,  # بطاقة سهول
    "barley": 30.0,  # بطاقة سهول
    "sorghum": 38.0,  # بطاقة سهول
    "millet": 40.0,  # بطاقة سهول
    "maize": 35.0,  # مرجع قياسي (لا بطاقة بعد)
    "tomato": 32.0,  # مرجع قياسي (لا بطاقة بعد)
    "potato": 30.0,  # مرجع قياسي (لا بطاقة بعد)
}

# عتبة ملوحة الجذور (Maas-Hoffman، من البطاقات). أعلى = أصمد للملوحة.
THRESHOLD_ECE = {
    "wheat": 6.0,
    "barley": 8.0,
    "sorghum": 6.8,
    "millet": 6.5,
    "maize": 1.7,
    "tomato": 2.5,
    "potato": 1.7,
}


@dataclass
class DroughtComponents:
    root_score: float  # عمق الجذور المطبّع
    heat_headroom: float  # هامش الحرارة قبل حدّ الإزهار
    salt_score: float  # تحمّل الملوحة المطبّع
    source_note_ar: str


def compute_drought_resilience(
    crop_id: str,
    forecast_max_temp_c: float | None = None,
    is_irrigated: bool | None = None,
) -> dict:
    """درجة تحمّل جفاف/حرارة مركّبة من صفات موثّقة (لا اختراع).

    forecast_max_temp_c: حرارة **الهواء** المتوقّعة — تُفعّل تحذير الإجهاد الحراري
    إن تجاوزت حدّ الإزهار الآمن (الحرارة قد تكون أخطر من الجفاف).

    is_irrigated: حالة الريّ. عند التحذير الحراريّ على حقل مرويّ يُضاف تنويه صادق:
    الريّ يبرّد سطح الغطاء (تبخّر-نتح) فالحرارة الفعليّة أدنى من الهواء، فتحذير
    الهواء قد يبالغ في الضرر الحراريّ على المرويّ (Zhu et al., HESS 2022). كيفيّ
    لا كمّيّ (لا نزرع أرقام نبراسكا)؛ لا يغيّر الدرجة (لا فبركة مقدار تبريد).
    """
    crop = crop_id.lower()
    root = ROOT_DEPTH_M.get(crop)
    heat_max = FLOWERING_SAFE_MAX_C.get(crop)
    ece = THRESHOLD_ECE.get(crop)

    available = [x for x in (root, heat_max, ece) if x is not None]
    if not available:
        return {
            "crop_id": crop_id,
            "resilience_score": None,
            "confidence": "none",
            "note_ar": (
                f"لا صفات موثّقة لـ'{crop_id}' في بطاقات سهول — لا درجة "
                "(لا اختراع). أضِف بطاقة محصول بمصادرها أوّلاً."
            ),
        }

    # المكوّنات (كلّ من صفة موثّقة، مطبّعة [0,1])
    root_score = min(root / DEEP_ROOT_REF_M, 1.0) if root else 0.5
    salt_score = min(ece / 8.0, 1.0) if ece else 0.5  # 8.0=أعلى (شعير)

    # هامش الحرارة: كم درجة قبل حدّ الإزهار الآمن
    heat_headroom = None
    heat_warning = None
    if heat_max is not None and forecast_max_temp_c is not None:
        headroom = heat_max - forecast_max_temp_c
        heat_headroom = round(headroom, 1)
        if headroom < 0:
            heat_warning = (
                f"⚠ الحرارة المتوقّعة {forecast_max_temp_c}°C تتجاوز حدّ "
                f"الإزهار الآمن {heat_max}°C — الإجهاد الحراري قد يكون أخطر "
                "من المائي (راجع التوقيت/التظليل)."
            )

    # الدرجة المركّبة (من المكوّنات المتاحة فقط — أوزان شفّافة)
    parts = []
    weights = []
    if root is not None:
        parts.append(root_score)
        weights.append(0.45)
    if ece is not None:
        parts.append(salt_score)
        weights.append(0.30)
    # الحرارة: مكوّن إيجابي لو الحدّ عالٍ (تحمّل حرّ)
    if heat_max is not None:
        heat_tol = min((heat_max - 30.0) / 10.0, 1.0) if heat_max > 30 else 0.0
        parts.append(max(0.0, heat_tol))
        weights.append(0.25)

    wsum = sum(weights) or 1.0
    score = round(sum(p * w for p, w in zip(parts, weights, strict=True)) / wsum, 3)

    def risk(s: float) -> str:
        if s > 0.7:
            return "تحمّل عالٍ"
        if s > 0.5:
            return "تحمّل متوسّط"
        if s > 0.3:
            return "تحمّل محدود"
        return "حسّاس للجفاف"

    result = {
        "crop_id": crop_id,
        "resilience_score": score,
        "risk_level_ar": risk(score),
        "components": {
            "root_depth_m": root,
            "root_score": round(root_score, 2),
            "threshold_ece": ece,
            "salt_score": round(salt_score, 2),
            "flowering_safe_max_c": heat_max,
            "heat_headroom_c": heat_headroom,
        },
        "confidence": "moderate" if len(available) >= 2 else "low",
        "source_note_ar": (
            "من صفات سهول الموثّقة: عمق الجذور (FAO-56)، حدّ حرارة الإزهار "
            "(بطاقات)، عتبة الملوحة (Maas-Hoffman). درجة نسبيّة للمقارنة."
        ),
    }
    if heat_warning:
        result["heat_warning_ar"] = heat_warning
        result["heat_basis_ar"] = "التحذير من حرارة الهواء المتوقّعة (لا حرارة سطح الغطاء)."
        # تصحيح علميّ: على الحقل المرويّ، الريّ يبرّد الغطاء فالهواء يبالغ في الضرر.
        if is_irrigated:
            result["heat_irrigation_caveat_ar"] = (
                "حقل مرويّ: الريّ يبرّد سطح الغطاء بالتبخّر-نتح، فحرارة الغطاء الفعليّة "
                "أدنى من حرارة الهواء؛ تحذيرٌ مبنيّ على حرارة الهواء قد يبالغ في الضرر "
                "الحراريّ على المرويّ (Zhu et al., HESS 2022). الأصدق حرارة السطح LST "
                "بالأقمار (مؤجَّل) — والريّ في الموجات الحارّة يحمي طور ملء الحبوب."
            )
    return result


def compare_crops_resilience(
    crop_ids: list[str],
    forecast_max_temp_c: float | None = None,
    is_irrigated: bool | None = None,
) -> dict:
    """يقارن تحمّل عدّة محاصيل للجفاف/الحرارة (لاختيار الأصمد لظرف صعب).

    يخدم قرار اختيار المحصول في موسم جفاف متوقّع — من صفات موثّقة.
    """
    assessed = [compute_drought_resilience(c, forecast_max_temp_c, is_irrigated) for c in crop_ids]
    scored = [a for a in assessed if a.get("resilience_score") is not None]
    scored.sort(key=lambda a: a["resilience_score"], reverse=True)
    return {
        "ranked_by_resilience": scored,
        "most_resilient": scored[0]["crop_id"] if scored else None,
        "note_ar": (
            "ترتيب نسبي من صفات موثّقة (لا أرقام TRY مخترعة). يساعد اختيار "
            "المحصول الأصمد لموسم جفاف متوقّع — يُدمَج مع الملاءمة والاقتصاد."
        ),
        "honesty_note_ar": (
            "درجة مركّبة من صفات سهول الموثّقة فقط. لو توفّرت صفات TRY مقيسة "
            "(WUE، SLA) لمحصول بمصدرها، تُضاف لبطاقته — لكن لا نخترعها."
        ),
    }
