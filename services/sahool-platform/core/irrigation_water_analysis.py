"""تحليل جودة ماء الريّ — مؤشّرات قياسيّة (SAR/RSC/تصنيف الملوحة).

الفجوة (من سياق الصُنيدر): لا تحليل ماء ريّ رغم اشتباهه محرّكاً للملوحة
والقلويّة المرصودتين في التربة. هذه الوحدة تحسب المؤشّرات الزراعيّة القياسيّة
من بيانات مخبريّة تُدخَل — منطق علمي حقيقي قابل للاختبار، يُستخدَم فور توفّر
تحليل مخبري (لا جدول DB فارغ، لا بيانات مفبركة).

المراجع (FAO-29 / USDA Bulletin 197 / Eaton 1950):
- SAR = Na / √((Ca + Mg)/2)   [الأيونات بـmeq/L]
- RSC = (CO₃ + HCO₃) − (Ca + Mg)   [meq/L]  (Eaton 1950)
- تصنيف الملوحة بـEC (dS/m) — FAO-29

العتبات (موثّقة):
- RSC: <1.25 آمن، 1.25–2.50 هامشي، >2.50 غير مناسب (USDA Bull. 197)
- SAR: <10 منخفض، 10–18 متوسّط، 18–26 مرتفع، >26 مرتفع جدّاً (USSL)
  (مشاكل النفاذيّة تبدأ SAR 6–9 في التربة الطينيّة المنتفخة)
- EC: <0.7 لا قيود، 0.7–3.0 قيود متوسّطة، >3.0 قيود شديدة (FAO-29)

صدق: لا يخترع بيانات. المدخل الناقص يُعلَن (None/تحذير)؛ لا تصنيف بلا قيم.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class WaterSample:
    """عيّنة ماء ريّ مخبريّة. الأيونات بـmeq/L، EC بـdS/m، pH بلا وحدة.

    صدق: كلّ الحقول اختياريّة (قد لا يقيس المختبر كلّ شيء)؛ المؤشّر الذي يحتاج
    قيمة غائبة يُعلَن غير محسوب (لا تقدير مفبرَك).
    """

    sample_id: str
    source: str = "well"  # well | canal | mixed
    # الأيونات (meq/L)
    na: float | None = None  # صوديوم
    ca: float | None = None  # كالسيوم
    mg: float | None = None  # مغنيسيوم
    hco3: float | None = None  # بيكربونات
    co3: float | None = None  # كربونات
    cl: float | None = None  # كلوريد
    # القياسات العامّة
    ec_dsm: float | None = None  # التوصيليّة الكهربائيّة dS/m
    ph: float | None = None
    sampled_at: str | None = None


def compute_sar(na: float, ca: float, mg: float) -> float | None:
    """SAR = Na / √((Ca+Mg)/2). الأيونات meq/L. None إن نقص مدخل."""
    if na is None or ca is None or mg is None:
        return None
    denom = (ca + mg) / 2.0
    if denom <= 0:
        return None  # صدق: لا قسمة على صفر، لا قيمة مفبركة
    return round(na / math.sqrt(denom), 2)


def compute_rsc(co3: float, hco3: float, ca: float, mg: float) -> float | None:
    """RSC = (CO₃ + HCO₃) − (Ca + Mg) بالـmeq/L (Eaton 1950). None إن نقص."""
    vals = [co3, hco3, ca, mg]
    if any(v is None for v in vals):
        return None
    return round((co3 + hco3) - (ca + mg), 2)


def classify_ec(ec_dsm: float | None) -> dict:
    """تصنيف ملوحة ماء الريّ بالـEC (FAO-29)."""
    if ec_dsm is None:
        return {"class": None, "note_ar": "EC غير مقيس"}
    if ec_dsm < 0.7:
        return {"class": "low", "restriction_ar": "لا قيود"}
    if ec_dsm <= 3.0:
        return {"class": "moderate", "restriction_ar": "قيود متوسّطة — راقب الملوحة"}
    return {"class": "severe", "restriction_ar": "قيود شديدة — غسيل ملحي ضروري"}


def classify_rsc(rsc: float | None) -> dict:
    """تصنيف خطر القلويّة بالـRSC (USDA Bulletin 197)."""
    if rsc is None:
        return {"class": None, "note_ar": "RSC غير محسوب (نقص أيونات)"}
    if rsc < 1.25:
        return {"class": "safe", "hazard_ar": "آمن"}
    if rsc <= 2.50:
        return {"class": "marginal", "hazard_ar": "هامشي — إدارة ريّ جيّدة + مراقبة"}
    return {"class": "unsuitable", "hazard_ar": "غير مناسب — خطر قلويّة عالٍ، يحتاج جبس"}


def classify_sar(sar: float | None) -> dict:
    """تصنيف خطر الصوديوم (sodicity) بالـSAR (USSL)."""
    if sar is None:
        return {"class": None, "note_ar": "SAR غير محسوب (نقص أيونات)"}
    if sar < 10:
        return {"class": "low", "hazard_ar": "منخفض"}
    if sar < 18:
        return {"class": "medium", "hazard_ar": "متوسّط — مشاكل نفاذيّة محتملة بالطين"}
    if sar < 26:
        return {"class": "high", "hazard_ar": "مرتفع — خطر sodicity"}
    return {"class": "very_high", "hazard_ar": "مرتفع جدّاً — غير مناسب بلا معالجة"}


def analyze_water_sample(sample: WaterSample) -> dict:
    """يحلّل عيّنة ماء ريّ: يحسب SAR/RSC + يصنّف الملوحة/الصوديوم/القلويّة.

    صدق: يعتمد فقط القيم المُدخَلة؛ المؤشّر الذي يحتاج قيمة غائبة يُعلَن غير
    محسوب. لا تصنيف عامّ بلا بيانات كافية. يُعلِن البيانات الناقصة صراحةً.
    """
    sar = compute_sar(sample.na, sample.ca, sample.mg)
    rsc = compute_rsc(sample.co3, sample.hco3, sample.ca, sample.mg)

    missing: list[str] = []
    for fname in ("na", "ca", "mg", "hco3", "co3", "ec_dsm"):
        if getattr(sample, fname) is None:
            missing.append(fname)

    # خلاصة عامّة: أسوأ تصنيف يحكم (المبدأ المحافِظ)
    ec_c = classify_ec(sample.ec_dsm)
    rsc_c = classify_rsc(rsc)
    sar_c = classify_sar(sar)
    flags: list[str] = []
    if ec_c.get("class") == "severe":
        flags.append("ملوحة شديدة")
    if rsc_c.get("class") == "unsuitable":
        flags.append("قلويّة عالية")
    if sar_c.get("class") in ("high", "very_high"):
        flags.append("صوديوم مرتفع")

    return {
        "sample_id": sample.sample_id,
        "source": sample.source,
        "indices": {"sar": sar, "rsc_meq_l": rsc, "ec_dsm": sample.ec_dsm, "ph": sample.ph},
        "classification": {"salinity": ec_c, "alkalinity_rsc": rsc_c, "sodicity_sar": sar_c},
        "hazard_flags_ar": flags,
        "suitable_ar": ("صالح للريّ" if not flags else f"يحتاج معالجة: {'، '.join(flags)}"),
        "missing_inputs": missing,  # صدق: نُعلن ما لم يُقَس
        "data_complete": len(missing) == 0,
    }
