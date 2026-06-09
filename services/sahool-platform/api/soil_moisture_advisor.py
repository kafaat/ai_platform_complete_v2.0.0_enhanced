"""
api/soil_moisture_advisor.py — قراءة مستشعر الرطوبة + قرار الريّ الذكي (RWC)

يطبّق منهجيّة "الريّ الذكي — قراءة بيانات قياس الرطوبة" (ملاحظات نموذج نمو
المحاصيل، يونيو ٢٠٢٦): تحويل قراءة المستشعر الخام (محتوى رطوبة حجمي VWC)
إلى محتوى رطوبة نسبي RWC، ثمّ قرار ريّ مبنيّ على عتبات موثّقة.

الفكرة الجوهريّة (من المستند):
  لا ننظر إلى "كم الماء في التربة" بل إلى "كم يمكن للمحاصيل امتصاصه".
  قراءة VWC=0.30 قد تعني وفرة في الرمل وشُحّاً في الطين — الفرق هو RWC.

الصيغة (من المستند):
  RWC = (θ − θWP) / (θFC − θWP)
  حيث:
    θ   = الرطوبة الحجميّة الحاليّة (قراءة المستشعر)
    θWP = نقطة الذبول (Wilting Point) — تحتها لا يمتصّ النبات
    θFC = السعة الحقليّة (Field Capacity) — أقصى ماء مفيد محتجَز

عتبات قرار الريّ (من المستند):
  RWC < 60%   → يحتاج ريّاً
  RWC 60-80%  → إجهاد خفيف (راقب)
  RWC > 80%   → آمن (قرب السعة الحقليّة)

⚠ صدق: القيم المرجعيّة (θFC/θWP) تقديريّة حسب نوع التربة (من المستند، مصدرها
NRCCA). الأدقّ قياسها ميدانيّاً للحقل نفسه (ريّ مُشبع ثمّ صرف — كما يشرح
المستند). نوفّر القيم النوعيّة كبداية، ونحثّ على المعايرة الميدانيّة.
⚠ المستشعر يقيس VWC لا "صعوبة الامتصاص"؛ في الدفيئات عالية التسميد يلزم
أيضاً مراقبة EC وجهد الماء (المستند يفصّل ذلك للخيار مقابل الذرة).
"""
from __future__ import annotations

from typing import Dict, Optional


# جداول رطوبة التربة النوعيّة (من المستند — مصدرها NRCCA)
# (θs مشبع، θFC سعة حقليّة، θWP نقطة ذبول) — كنسب حجميّة
_SOIL_PARAMS = {
    "sand": {  # رمليّة
        "name_ar": "رمليّة", "theta_s": 0.33, "theta_fc": 0.20, "theta_wp": 0.075,
        "note_ar": "تحتفظ بماء أقلّ، تسرّب سريع، سعة حقليّة منخفضة.",
    },
    "loam": {  # طميّة
        "name_ar": "طميّة", "theta_s": 0.47, "theta_fc": 0.40, "theta_wp": 0.125,
        "note_ar": "احتفاظ معتدل بالماء — الأفضل للزراعة.",
    },
    "clay": {  # طينيّة
        "name_ar": "طينيّة", "theta_s": 0.55, "theta_fc": 0.50, "theta_wp": 0.175,
        "note_ar": "ماء كثير 'محبوس' — ليس كلّه متاحاً للنبات.",
    },
}

# عتبات قرار الريّ على RWC (من المستند)
_RWC_NEED = 0.60       # تحتها: يحتاج ريّاً
_RWC_SAFE = 0.80       # فوقها: آمن

# عمق منطقة الجذور الفعّال (متر) — لحساب كمّيّة الريّ (FAO-56 جدول ٢٢)
# المرجع: FAO Irrigation & Drainage Paper 56 (Allen et al. 1998)
_ROOT_DEPTH_M = {
    "wheat": 1.2, "barley": 1.2, "maize": 1.0, "ذرة": 1.0,
    "millet": 1.0, "sorghum": 1.5, "potato": 0.5, "tomato": 0.9,
    "onion": 0.4, "cucumber": 0.8, "خيار": 0.8, "alfalfa": 1.5,
    "olive": 1.5, "زيتون": 1.5, "citrus": 1.2, "grape": 1.2, "عنب": 1.2,
    "vegetables": 0.4, "خضروات": 0.4,
}
_DEFAULT_ROOT_DEPTH_M = 0.6   # افتراضي محافظ حين يُجهل المحصول


def list_soil_types() -> Dict:
    """أنواع التربة وقيمها المرجعيّة (للاختيار في الواجهة)."""
    return {
        "soil_types": _SOIL_PARAMS,
        "note_ar": (
            "قيم نوعيّة تقديريّة (مصدر NRCCA). للدقّة، عايِر حقلك ميدانيّاً: "
            "اروِ حتّى الإشباع، انتظر الصرف الطبيعي، وسجّل القراءة المستقرّة "
            "كسعة حقليّة."
        ),
    }


def compute_rwc(
    vwc: float,
    soil_type: str = "loam",
    theta_fc: Optional[float] = None,
    theta_wp: Optional[float] = None,
) -> Dict:
    """يحوّل قراءة المستشعر (VWC) إلى محتوى رطوبة نسبي RWC + قرار ريّ.

    vwc: الرطوبة الحجميّة من المستشعر (نسبة 0-1، مثلاً 0.20 = 20%).
    soil_type: sand/loam/clay (يحدّد θFC/θWP النوعيّة).
    theta_fc/theta_wp: قيم مُعايَرة ميدانيّاً (تتجاوز النوعيّة — الأدقّ).
    """
    st = _SOIL_PARAMS.get(soil_type.lower(), _SOIL_PARAMS["loam"])
    fc = theta_fc if theta_fc is not None else st["theta_fc"]
    wp = theta_wp if theta_wp is not None else st["theta_wp"]
    calibrated = theta_fc is not None or theta_wp is not None

    # تحقّق منطقي
    if fc <= wp:
        return {
            "ok": False,
            "error_ar": "السعة الحقليّة يجب أن تفوق نقطة الذبول — تحقّق من القيم.",
        }

    # المستند يعرض مقياسين:
    #  ١) RWC الكامل = (θ−θWP)/(θFC−θWP) — الأدقّ علميّاً (نطاق الماء المتاح)
    #  ٢) نسبة عمليّة مبسّطة = θ/θFC — يستخدمها المستند في مثاله العملي
    #     (قراءة 20% ÷ سعة حقليّة 35% ≈ 57%)
    # نحسب الاثنين؛ القرار على RWC الكامل (الأدقّ)، ونعرض النسبة المبسّطة أيضاً.
    rwc_raw = (vwc - wp) / (fc - wp)
    rwc = max(0.0, min(1.0, rwc_raw))
    rwc_pct = round(rwc * 100, 1)
    fc_ratio_pct = round(min(1.0, vwc / fc) * 100, 1) if fc > 0 else 0.0

    # قرار الريّ حسب العتبات الموثّقة
    if rwc < _RWC_NEED:
        decision = "irrigate"
        decision_ar = "يحتاج ريّاً الآن"
        reason_ar = (
            f"المحتوى النسبي {rwc_pct}% دون عتبة {int(_RWC_NEED*100)}% — "
            "النبات يقترب من الإجهاد المائي."
        )
    elif rwc < _RWC_SAFE:
        decision = "monitor"
        decision_ar = "إجهاد خفيف — راقب"
        reason_ar = (
            f"المحتوى النسبي {rwc_pct}% في نطاق الإجهاد الخفيف "
            f"({int(_RWC_NEED*100)}-{int(_RWC_SAFE*100)}%) — جهّز للريّ قريباً."
        )
    else:
        decision = "safe"
        decision_ar = "آمن — لا حاجة للريّ"
        reason_ar = (
            f"المحتوى النسبي {rwc_pct}% فوق {int(_RWC_SAFE*100)}% — "
            "قرب السعة الحقليّة. ريّ زائد يتسرّب ويُهدر."
        )

    return {
        "ok": True,
        "vwc": round(vwc, 3),
        "vwc_pct": round(vwc * 100, 1),
        "rwc": round(rwc, 3),
        "rwc_pct": rwc_pct,
        "fc_ratio_pct": fc_ratio_pct,
        "fc_ratio_note_ar": (
            f"نسبة عمليّة مبسّطة (θ/سعة حقليّة) = {fc_ratio_pct}% — "
            "يستخدمها بعض المزارعين كتقدير سريع؛ القرار أعلاه على RWC الأدقّ."
        ),
        "soil_type_ar": st["name_ar"],
        "theta_fc": round(fc, 3),
        "theta_wp": round(wp, 3),
        "calibrated": calibrated,
        "decision": decision,
        "decision_ar": decision_ar,
        "reason_ar": reason_ar,
        "disclaimer_ar": (
            "القرار مبنيّ على عتبات نوعيّة. "
            + ("القيم مُعايَرة ميدانيّاً (دقّة أعلى)."
               if calibrated else
               "للدقّة، عايِر السعة الحقليّة لحقلك ميدانيّاً.")
            + " في الدفيئات عالية التسميد، راقب أيضاً EC وجهد الماء."
        ),
    }


def irrigation_amount_mm(
    vwc: float,
    soil_type: str = "loam",
    crop: Optional[str] = None,
    root_depth_m: Optional[float] = None,
    theta_fc: Optional[float] = None,
) -> Dict:
    """يحسب كمّيّة الريّ اللازمة (ملّيمتر) لإعادة التربة للسعة الحقليّة.

    المعادلة الفيزيائيّة القياسيّة (FAO-56):
      كمّيّة الريّ (مم) = (θFC − θ) × عمق منطقة الجذور (مم)
    ليست تخميناً — معادلة حجميّة مباشرة. تُرجع 0 إن كانت التربة عند/فوق
    السعة الحقليّة (لا حاجة للريّ).
    """
    st = _SOIL_PARAMS.get(soil_type.lower(), _SOIL_PARAMS["loam"])
    fc = theta_fc if theta_fc is not None else st["theta_fc"]

    if root_depth_m is not None:
        depth_m = root_depth_m
    elif crop and (crop.lower() in _ROOT_DEPTH_M or crop in _ROOT_DEPTH_M):
        depth_m = _ROOT_DEPTH_M.get(crop.lower()) or _ROOT_DEPTH_M.get(crop)
    else:
        depth_m = _DEFAULT_ROOT_DEPTH_M

    deficit = max(0.0, fc - vwc)
    amount_mm = round(deficit * depth_m * 1000.0, 1)

    return {
        "irrigation_mm": amount_mm,
        "root_depth_m": round(depth_m, 2),
        "deficit_vwc": round(deficit, 3),
        "theta_fc": round(fc, 3),
        "formula_ar": "كمّيّة الريّ = (السعة الحقليّة − الرطوبة الحاليّة) × عمق الجذور",
        "note_ar": (
            f"لإعادة التربة للسعة الحقليّة في منطقة جذور بعمق {depth_m} م، "
            f"يلزم نحو {amount_mm} مم ماء."
            if amount_mm > 0 else
            "التربة عند السعة الحقليّة أو فوقها — لا حاجة للريّ."
        ),
        "root_depth_source_ar": (
            "مُدخَل يدويّاً" if root_depth_m is not None
            else "جدول المحصول (FAO-56)"
            if (crop and (crop.lower() in _ROOT_DEPTH_M or crop in _ROOT_DEPTH_M))
            else "افتراضي محافظ (المحصول غير محدّد)"
        ),
    }


def irrigation_guidance(
    vwc: float,
    soil_type: str = "loam",
    crop: Optional[str] = None,
    growth_stage: Optional[str] = None,
    theta_fc: Optional[float] = None,
    theta_wp: Optional[float] = None,
    root_depth_m: Optional[float] = None,
) -> Dict:
    """إرشاد ريّ متكامل: RWC + سياق المحصول/المرحلة + كمّيّة الريّ (إن لزم)."""
    base = compute_rwc(vwc, soil_type, theta_fc, theta_wp)
    if not base.get("ok"):
        return base

    # تنبيه حسّاسيّة المرحلة (المستند يذكر أنّ مرحلة سحب الذكور في الذرة حرجة)
    stage_note_ar = None
    if growth_stage and base["decision"] != "safe":
        sensitive = any(k in growth_stage for k in
                        ["إزهار", "flower", "سحب", "tassel", "عقد", "fruit_set", "ذروة", "mid"])
        if sensitive:
            stage_note_ar = (
                "⚠ المرحلة الحاليّة حرجة لاستهلاك الماء — تأخّر الريّ قد يخفض "
                "الإنتاج بشكل ملحوظ. أعطِ الريّ أولويّة."
            )

    base["crop_ar"] = crop
    base["growth_stage_ar"] = growth_stage
    base["stage_sensitivity_note_ar"] = stage_note_ar
    # كمّيّة الريّ (حين الحاجة) — معادلة حجميّة FAO-56
    if base["decision"] in ("irrigate", "monitor"):
        amt = irrigation_amount_mm(vwc, soil_type, crop, root_depth_m, theta_fc)
        base["irrigation_amount"] = amt
    base["method_ar"] = (
        "المنهجيّة: قراءة المستشعر (VWC) → المحتوى النسبي RWC → قرار الريّ. "
        "ننظر لما يمتصّه النبات لا لكمّ الماء الخام."
    )
    return base
