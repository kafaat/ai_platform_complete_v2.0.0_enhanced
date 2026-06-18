"""core/soil_feedback_proxy.py — محرّك تقدير التغذية الراجعة نبات-تربة (PSFI) (نقيّ، حتميّ).

مستوحى من مراجعة Science «توجيه التغذية الراجعة نبات-تربة لزراعة مستدامة»
(Steering plant-soil feedback for sustainable agriculture). الفكرة المحوريّة في
المقال: تحويل التغذية الراجعة **السالبة** (تراكم الممرضات/تدهور الميكروبيوم) إلى
تغذية راجعة **موجبة** (إثراء الفطريّات الجذريّة AMF والرايزوبيا وبنية التربة).

القيد التصميميّ الحاسم: أغلب المزارعين **لا يملكون** تسلسلاً جينيّاً (DNA) ولا مختبر
ميكروبيوم. لذا يقدّر هذا المحرّك التغذية الراجعة من **مؤشّرات إدارة الحقل (proxies)**
فقط — لا بيانات جينيّة. يحوّل مفهوم المقال إلى **درجة تشغيليّة** قابلة للتبرير.

اتّجاهات المقال (الأوزان أدناه تتبعها حتميّاً):
  • روافع موجبة (ترفع `positive_feedback_score`): تنوّع الدورة الزراعيّة، نسبة
    البقوليات (تثبيت نيتروجين)، محاصيل التغطية، إضافات المادّة العضويّة (كومبوست/سماد
    عضويّ/قشّ)، انخفاض الحراثة (no-till)، الكربون العضويّ في التربة SOC.
  • روافع سالبة (ترفع `negative_feedback_risk`/`pathogen_accumulation_risk`): تكرار
    العائل نفسه (تراكم الممرضات)، الملوحة (إجهاد ميكروبيّ)، تاريخ الأمراض الحديث،
    الإفراط في الأسمدة المعدنيّة (يقلّل AMF/الرايزوبيا)، الحراثة المكثّفة.

كلّ درجة فرعيّة مزيج مرجَّح حتميّ للمؤشّرات ذات الصلة، مقصوص إلى حدوده. المدخلات
الناقصة (None) تُستبعد من مزيجها (تُعاد معايرة الأوزان على المعروف فقط) ولا تُعامَل
أبداً كصفر. الثقة (confidence) تتناسب مع نسبة المدخلات المعروفة. مدخلات كلّها None ⇒
سِجلّ محايد بثقة ~0 دون أيّ انهيار. كلّ قسمة محروسة.

نقيّ تماماً: لا I/O، لا شبكة، لا قاعدة بيانات، لا عشوائيّة، لا numpy. stdlib +
dataclasses فقط. مفصول تماماً عن وحدات الدورة الزراعيّة (يُمرَّر تنوّع الدورة كقيمة
عشريّة عاديّة — التركيب يحدث في موقع الاستدعاء لا عبر import).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

# ── عتبات الاتّجاه (من net_feedback في [-100,100]) ──
_POSITIVE_THRESHOLD = 8.0  # net ≥ هذا ⇒ اتّجاه موجب
_NEGATIVE_THRESHOLD = -8.0  # net ≤ هذا ⇒ اتّجاه سالب (وإلّا محايد)

# أدنى ثقة لاعتبار الاتّجاه ذا معنى — تحتها يُفرَض «محايد».
_MIN_CONFIDENCE_FOR_DIRECTION = 0.12

# عتبة «درجة مرتفعة» لإدراج عامل في أدلّة (drivers) — على مقياس [0,100].
_DRIVER_STRENGTH = 55.0

# المعايرة المرجعيّة للمدخلات غير [0,1] (لتطبيعها إلى [0,1]).
_SOC_REF_PCT = 3.0  # SOC% ~3 يُعدّ ممتازاً (نطاق زراعيّ ~0.5–3)
_SALINITY_REF_DS_M = 8.0  # ECe ~8 dS/m يُعدّ إجهاداً ملحيّاً شديداً
_DISEASE_REF_COUNT = 4.0  # ~4 حوادث مرضيّة حديثة تُعدّ ضغطاً مرتفعاً
_ORGANIC_REF_COUNT = 4.0  # ~4 إضافات عضويّة/سنة تُعدّ كثافة مرتفعة


@dataclass(frozen=True)
class SoilFeedbackInputs:
    """مؤشّرات إدارة الحقل (proxies) — بلا بيانات جينيّة. كلّها بقيم افتراضيّة.

    كلّ حقل None يعني «إشارة غير معروفة» (تُستبعد من المزيج، لا تُعامَل كصفر). النطاقات
    [0,1] ما لم يُذكَر خلاف ذلك. القيم تُقصّ/تُطبَّع داخليّاً بأمان.
    """

    rotation_diversity: float | None = None  # [0,1] تنوّع الدورة (رافعة موجبة)
    legume_ratio: float | None = None  # [0,1] نسبة البقوليات (تثبيت نيتروجين، موجب)
    cover_crop_ratio: float | None = None  # [0,1] محاصيل التغطية (موجب)
    host_repeat_risk: float | None = None  # [0,1] تكرار العائل (تراكم ممرضات، سالب)
    organic_matter_additions_per_yr: float | None = None  # عدّ/كثافة إضافات عضويّة (موجب)
    tillage_intensity: float | None = None  # [0,1] 0=بلا حراثة .. 1=مكثّفة (مرتفع = سالب)
    soil_organic_carbon_pct: float | None = None  # SOC% (موجب؛ نطاق زراعيّ ~0.5–3)
    salinity_ds_m: float | None = None  # ECe dS/m (مرتفع = سالب/إجهاد ميكروبيّ)
    disease_incidents_recent: int | None = None  # تاريخ أمراض حديث (ضغط ممرضات، سالب)
    synthetic_fertilizer_intensity: float | None = None  # [0,1] (إفراط يقلّل AMF/الرايزوبيا)


@dataclass(frozen=True)
class PlantSoilFeedback:
    """سِجلّ التغذية الراجعة نبات-تربة المُهيكَل (مرآة JSON الهدف)."""

    positive_feedback_score: float  # [0,100]
    negative_feedback_risk: float  # [0,100]
    pathogen_accumulation_risk: float  # [0,100]
    microbial_diversity_proxy: float  # [0,100]
    soil_resilience_score: float  # [0,100]
    net_feedback: float  # positive - negative، في [-100,100]
    direction: str  # "positive" | "negative" | "neutral"
    confidence: float  # [0,1] بحسب عدد المدخلات المعروفة
    inputs_known: int  # عدد المدخلات غير None المستخدَمة
    drivers_positive_ar: tuple[str, ...]  # أدلّة عربيّة لرفع التغذية الموجبة
    drivers_negative_ar: tuple[str, ...]  # أدلّة عربيّة لرفع الخطر/التغذية السالبة
    verdict_ar: str  # حُكم عربيّ من سطر واحد


# ── أدوات مساعدة نقيّة ──
def _clamp(x: float, lo: float, hi: float) -> float:
    """يقصّ القيمة إلى [lo, hi]."""
    return lo if x < lo else (hi if x > hi else x)


def _clamp01(x: float) -> float:
    """يقصّ القيمة إلى [0,1]."""
    return _clamp(x, 0.0, 1.0)


def _norm_ref(value: float, ref: float) -> float:
    """يطبّع قيمة موجبة إلى [0,1] بنسبتها إلى مرجع (قسمة محروسة)، مقصوصاً."""
    if ref <= 0.0:
        return 0.0
    return _clamp01(value / ref)


def _blend(parts: list[tuple[float, float]]) -> float | None:
    """مزيج مرجَّح حتميّ: لائحة (signal[0,1], weight). None إن لا إشارات معروفة.

    تُعاد معايرة الأوزان على المعروف فقط (قسمة محروسة على مجموع الأوزان). الناتج [0,1].
    """
    total_w = 0.0
    acc = 0.0
    for signal, weight in parts:
        total_w += weight
        acc += _clamp01(signal) * weight
    if total_w <= 0.0:
        return None
    return _clamp01(acc / total_w)


def _to_100(x: float | None) -> float:
    """يحوّل مزيجاً في [0,1] (أو None) إلى درجة [0,100]؛ None ⇒ 0.0 (محايد)."""
    if x is None:
        return 0.0
    return round(_clamp01(x) * 100.0, 2)


def assess_plant_soil_feedback(inputs: SoilFeedbackInputs) -> PlantSoilFeedback:
    """يقدّر التغذية الراجعة نبات-تربة من مؤشّرات الإدارة فقط (نقيّ، حتميّ).

    الدرجات الفرعيّة (كلّها مزيج مرجَّح للمؤشّرات المعروفة، مقصوص إلى [0,100]):
      • `positive_feedback_score`: تنوّع الدورة (0.28) + البقوليات (0.22) + محاصيل
        التغطية (0.20) + الإضافات العضويّة (0.16) + SOC (0.14) + انعكاس الحراثة (1-till).
      • `negative_feedback_risk`: تكرار العائل + الإفراط بالأسمدة + الحراثة المكثّفة +
        الملوحة + تاريخ الأمراض.
      • `pathogen_accumulation_risk`: تكرار العائل (الأثقل) + تاريخ الأمراض + غياب
        التنوّع/محاصيل التغطية (تكسير دورة الممرض).
      • `microbial_diversity_proxy`: تنوّع الدورة + محاصيل التغطية + المادّة العضويّة +
        SOC + انعكاس الحراثة وانعكاس الإفراط بالأسمدة وانعكاس الملوحة.
      • `soil_resilience_score`: SOC + انعكاس الملوحة + المادّة العضويّة + انعكاس الحراثة.

    `net_feedback = positive_feedback_score - negative_feedback_risk` في [-100,100].
    `direction` من العتبات (±8) مع فرض «محايد» إذا كانت الثقة دون الحدّ الأدنى.
    `confidence = inputs_known / total_inputs`. المدخلات None تُستبعد ولا تُعامَل كصفر.
    مدخلات كلّها None ⇒ سِجلّ محايد بثقة ~0 وملاحظة عربيّة بعدم كفاية البيانات (لا انهيار).
    """
    # عدّ المدخلات المعروفة + الثقة.
    total_inputs = len(fields(SoilFeedbackInputs))
    inputs_known = sum(1 for f in fields(SoilFeedbackInputs) if getattr(inputs, f.name) is not None)
    confidence = round(inputs_known / total_inputs, 4) if total_inputs > 0 else 0.0

    # ── تطبيع كلّ مؤشّر معروف إلى [0,1] (None يبقى None) ──
    rot = (
        _clamp01(float(inputs.rotation_diversity))
        if inputs.rotation_diversity is not None
        else None
    )
    leg = _clamp01(float(inputs.legume_ratio)) if inputs.legume_ratio is not None else None
    cov = _clamp01(float(inputs.cover_crop_ratio)) if inputs.cover_crop_ratio is not None else None
    host = _clamp01(float(inputs.host_repeat_risk)) if inputs.host_repeat_risk is not None else None
    org = (
        _norm_ref(float(inputs.organic_matter_additions_per_yr), _ORGANIC_REF_COUNT)
        if inputs.organic_matter_additions_per_yr is not None
        else None
    )
    till = (
        _clamp01(float(inputs.tillage_intensity)) if inputs.tillage_intensity is not None else None
    )
    soc = (
        _norm_ref(float(inputs.soil_organic_carbon_pct), _SOC_REF_PCT)
        if inputs.soil_organic_carbon_pct is not None
        else None
    )
    sal = (
        _norm_ref(float(inputs.salinity_ds_m), _SALINITY_REF_DS_M)
        if inputs.salinity_ds_m is not None
        else None
    )
    dis = (
        _norm_ref(float(inputs.disease_incidents_recent), _DISEASE_REF_COUNT)
        if inputs.disease_incidents_recent is not None
        else None
    )
    fert = (
        _clamp01(float(inputs.synthetic_fertilizer_intensity))
        if inputs.synthetic_fertilizer_intensity is not None
        else None
    )

    # انعكاسات الإشارات السالبة (لاستخدامها كروافع موجبة محايدة في بعض المزائج).
    till_inv = (1.0 - till) if till is not None else None
    sal_inv = (1.0 - sal) if sal is not None else None
    fert_inv = (1.0 - fert) if fert is not None else None

    def _part(signal: float | None, weight: float) -> list[tuple[float, float]]:
        """يبني جزءاً واحداً للمزيج إن كانت الإشارة معروفة، وإلّا لا شيء (استبعاد)."""
        return [(signal, weight)] if signal is not None else []

    # ── positive_feedback_score ──
    positive = _to_100(
        _blend(
            _part(rot, 0.28)
            + _part(leg, 0.22)
            + _part(cov, 0.20)
            + _part(org, 0.16)
            + _part(soc, 0.14)
            + _part(till_inv, 0.18)
        )
    )

    # ── negative_feedback_risk ──
    negative = _to_100(
        _blend(
            _part(host, 0.30)
            + _part(fert, 0.22)
            + _part(till, 0.18)
            + _part(sal, 0.16)
            + _part(dis, 0.14)
        )
    )

    # ── pathogen_accumulation_risk ──
    # تكرار العائل وتاريخ الأمراض يرفعان؛ غياب التنوّع/التغطية يرفع (تكسير دورة الممرض).
    no_rotation = (1.0 - rot) if rot is not None else None
    no_cover = (1.0 - cov) if cov is not None else None
    pathogen = _to_100(
        _blend(
            _part(host, 0.40) + _part(dis, 0.26) + _part(no_rotation, 0.18) + _part(no_cover, 0.16)
        )
    )

    # ── microbial_diversity_proxy ──
    microbial = _to_100(
        _blend(
            _part(rot, 0.20)
            + _part(cov, 0.18)
            + _part(org, 0.18)
            + _part(soc, 0.16)
            + _part(till_inv, 0.14)
            + _part(fert_inv, 0.08)
            + _part(sal_inv, 0.06)
        )
    )

    # ── soil_resilience_score ──
    resilience = _to_100(
        _blend(_part(soc, 0.34) + _part(sal_inv, 0.26) + _part(org, 0.22) + _part(till_inv, 0.18))
    )

    net = round(_clamp(positive - negative, -100.0, 100.0), 2)

    # ── الاتّجاه (مع فرض المحايد عند ثقة منخفضة جدّاً) ──
    if confidence < _MIN_CONFIDENCE_FOR_DIRECTION:
        direction = "neutral"
    elif net >= _POSITIVE_THRESHOLD:
        direction = "positive"
    elif net <= _NEGATIVE_THRESHOLD:
        direction = "negative"
    else:
        direction = "neutral"

    # ── أدلّة عربيّة من أقوى المؤشّرات الفعليّة المساهِمة ──
    drivers_pos: list[str] = []
    if rot is not None and rot * 100.0 >= _DRIVER_STRENGTH:
        drivers_pos.append("تنوّع دورة زراعيّة مرتفع يكسر دورة الممرضات ويُثري الميكروبيوم")
    if leg is not None and leg * 100.0 >= _DRIVER_STRENGTH:
        drivers_pos.append("نسبة بقوليات عالية تثبّت النيتروجين وتُنشّط الرايزوبيا")
    if cov is not None and cov * 100.0 >= _DRIVER_STRENGTH:
        drivers_pos.append("محاصيل تغطية تحمي التربة وتغذّي الميكروبات")
    if org is not None and org * 100.0 >= _DRIVER_STRENGTH:
        drivers_pos.append("إضافات مادّة عضويّة وفيرة تعزّز الكربون والنشاط الحيويّ")
    if soc is not None and soc * 100.0 >= _DRIVER_STRENGTH:
        drivers_pos.append("كربون عضويّ مرتفع في التربة يدعم المرونة والخصوبة")
    if till_inv is not None and till_inv * 100.0 >= _DRIVER_STRENGTH:
        drivers_pos.append("حراثة منخفضة تحافظ على بنية التربة والفطريّات الجذريّة AMF")

    drivers_neg: list[str] = []
    if host is not None and host * 100.0 >= _DRIVER_STRENGTH:
        drivers_neg.append("تكرار العائل نفسه يراكم الممرضات في التربة")
    if dis is not None and dis * 100.0 >= _DRIVER_STRENGTH:
        drivers_neg.append("تاريخ أمراض حديث يشير إلى ضغط ممرضات قائم")
    if fert is not None and fert * 100.0 >= _DRIVER_STRENGTH:
        drivers_neg.append("إفراط الأسمدة المعدنيّة يقلّل الفطريّات الجذريّة AMF والرايزوبيا")
    if till is not None and till * 100.0 >= _DRIVER_STRENGTH:
        drivers_neg.append("حراثة مكثّفة تُضعف بنية التربة والميكروبيوم")
    if sal is not None and sal * 100.0 >= _DRIVER_STRENGTH:
        drivers_neg.append("ملوحة مرتفعة تُجهد الميكروبات وتثبّط نشاطها")

    # ── الحُكم العربيّ ──
    if inputs_known == 0:
        verdict = "بيانات غير كافية: لا مؤشّرات إدارة متاحة لتقدير التغذية الراجعة نبات-تربة."
    elif confidence < _MIN_CONFIDENCE_FOR_DIRECTION:
        verdict = "بيانات شحيحة: التقدير محايد ومنخفض الثقة — أضِف مؤشّرات إدارة أكثر."
    elif direction == "positive":
        verdict = "تغذية راجعة موجبة: الإدارة الحاليّة تميل لإثراء التربة وكسر دورة الممرضات."
    elif direction == "negative":
        verdict = "تغذية راجعة سالبة: مخاطر تراكم الممرضات وتدهور الميكروبيوم مرتفعة — تدخّل مطلوب."
    else:
        verdict = "تغذية راجعة محايدة: الروافع الموجبة والسالبة متوازنة تقريباً."

    return PlantSoilFeedback(
        positive_feedback_score=positive,
        negative_feedback_risk=negative,
        pathogen_accumulation_risk=pathogen,
        microbial_diversity_proxy=microbial,
        soil_resilience_score=resilience,
        net_feedback=net,
        direction=direction,
        confidence=confidence,
        inputs_known=inputs_known,
        drivers_positive_ar=tuple(drivers_pos),
        drivers_negative_ar=tuple(drivers_neg),
        verdict_ar=verdict,
    )
