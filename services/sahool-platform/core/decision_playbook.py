"""core/decision_playbook.py — محرّك «دليل القرار» (Decision Playbook) (نقيّ، حتميّ).

ذكاء اصطناعيّ قابل للتفسير ⇐ «إغلاق القرار» (decision closure): يحوّل الإشارات المبعثرة
في المنصّة (إشارات الطقس القراريّة + مخاطر المحصول + التغذية الراجعة نبات-تربة + توصية
علويّة اختياريّة) إلى **توصية واحدة مُهيكَلة قابلة للتنفيذ** بدل جملة غامضة واحدة.

شكل الناتج (حدّده مالك المنتج حرفيّاً):
  {main_judgement, confidence, evidence[], do_today[], avoid_now[], review_after, escalate_if[]}

التركيب من النوى النقيّة القائمة (تُمرَّر نتائجها المحسوبة مسبقاً عبر `PlaybookContext`
كي يكون الدليل قابلاً للاختبار بلا إعادة بناء المنصّة كاملةً):
  • `weather_signals.WeatherSignal` ⇐ `.signal_type` (spray_window_open | disease_risk_high
    | frost_imminent | heat_stress | trafficability_poor)، `.confidence_score`، `.payload`.
  • `crop_risk.CropRisk` ⇐ `.risk_type` (fungal_disease | heat_stress | frost_damage)،
    `.crop`، `.severity`، `.score` [0,1]، `.reason_ar`.
  • `soil_feedback_proxy.PlantSoilFeedback` ⇐ `.direction` (positive|negative|neutral)،
    `.pathogen_accumulation_risk`، `.confidence`، `.verdict_ar`، `.drivers_*_ar`.

── قواعد القرار الحتميّة (العتبات موثّقة، والأدلّة تستشهد بالإشارات) ──
ترتيب الأولويّة لاختيار الحُكم الرئيسيّ (الأكثر إلحاحاً يفوز، حتميّاً):
  صقيع > مرض > إجهاد حراريّ > سوء صلاحيّة المرور > تغذية راجعة سالبة > فرصة رشّ > روتين.

  • صقيع: إشارة `frost_imminent` أو خطر `frost_damage` بدرجة عالية (score ≥ 0.66) ⇒
    do_today: حماية من الصقيع (ريّ وقائيّ/تغطية)؛ avoid_now: لا رشّ ولا تسميد ورقيّ
    الليلة؛ review_after قصير (خلال ٢٤ ساعة)؛ escalate_if: استمرار الصقيع أو هبوط الحرارة.
  • مرض: إشارة `disease_risk_high` أو خطر `fungal_disease` عالٍ ⇒ do_today: فحص حقليّ +
    رشّ وقائيّ مناسب؛ avoid_now: ريّ غمر مسائيّ يرفع الرطوبة؛ escalate_if: ظهور بؤر إصابة.
  • إجهاد حراريّ: إشارة/خطر `heat_stress` ⇒ do_today: تعديل جدولة الريّ لتخفيف الإجهاد؛
    avoid_now: عمليّات تحت ذروة الحرّ.
  • صلاحيّة مرور: إشارة `trafficability_poor` ⇒ avoid_now: دخول الآليّات الثقيلة (انضغاط).
  • تغذية راجعة سالبة: `soil_feedback.direction == "negative"` (خطر تراكم ممرضات عالٍ) ⇒
    الأدلّة تستشهد بها؛ do_today/review حول تنويع الدورة/مادّة عضويّة؛ escalate_if: تكرار
    تدهور المؤشّر موسماً آخر. وإن كانت `positive` ⇒ تعزيز (لا إنذار): القاعدة الترابيّة سليمة.
  • فرصة رشّ: إشارة `spray_window_open` ودون حاجب (صقيع/مرض) ⇒ do_today: نفّذ الرشّ ضمن
    النافذة؛ الأدلّة تستشهد بالنافذة المفتوحة.
  • لا شيء لافت ⇒ حُكم هادئ «الوضع مستقرّ».

`confidence`: مزيج ثقات المدخلات المساهِمة مع عامل تغطية (حضور سياق أكثر ⇒ ثقة أعلى)،
مقصوص إلى [0,1]. سياق فارغ ⇒ ثقة منخفضة + حُكم محايد «بيانات غير كافية» (لا انهيار أبداً).
`review_after` غير فارغ دائماً. `do_today`/`avoid_now`/`escalate_if` قد تكون فارغة عند
عدم الانطباق، لكن الأدلّة تُفسّر السبب. كلّ قسمة محروسة. نقيّ حتميّ — لا I/O، لا numpy.
stdlib + dataclasses فقط. نفس السياق ⇒ نفس الدليل تماماً.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── عتبات القرار (قابلة للمعايرة) ──
_HIGH_RISK_SCORE = 0.66  # درجة CropRisk ≥ هذا ⇒ شدّة عالية محفِّزة للحُكم
_HIGH_PATHOGEN_RISK = 55.0  # pathogen_accumulation_risk على [0,100] فوقه ⇒ تحذير صريح
_MIN_SOIL_CONFIDENCE = 0.12  # أدنى ثقة تربة لاعتبار اتّجاهها ذا معنى

# آفاق المراجعة بحسب الإلحاح.
_HORIZON_URGENT = "خلال ٢٤ ساعة"
_HORIZON_SOON = "خلال ٤٨ ساعة"
_HORIZON_ROUTINE = "بعد ٣ أيّام"
_HORIZON_SEASONAL = "بمراجعة موسميّة"

# سقف عدد الأدلّة المعروضة (إبقاء الناتج قابلاً للتنفيذ لا مُغرِقاً).
_MAX_EVIDENCE = 8

_VALID_SIGNALS = frozenset(
    {
        "spray_window_open",
        "disease_risk_high",
        "frost_imminent",
        "heat_stress",
        "trafficability_poor",
    }
)


@dataclass(frozen=True)
class PlaybookContext:
    """سياق الدليل: مدخلات محسوبة مسبقاً واختياريّة (كلّها بقيم افتراضيّة).

    حضور جزئيّ للسياق لا يُسبّب انهياراً أبداً. تُمرَّر كائنات النوى الحقيقيّة
    (WeatherSignal / CropRisk / PlantSoilFeedback) أو أيّ كائن يعرض الحقول نفسها (تنميط
    رخو متعمَّد كي يبقى الدليل قابلاً للاختبار بمعزل عن باقي المنصّة).
    """

    crop: str | None = None
    weather_signals: tuple = ()  # عناصر تعرض .signal_type / .confidence_score
    crop_risks: tuple = ()  # عناصر CropRisk
    soil_feedback: object | None = None  # PlantSoilFeedback أو None
    recommendation_ar: str | None = None  # توصية علويّة اختياريّة للإثراء


@dataclass(frozen=True)
class DecisionPlaybook:
    """دليل القرار المُهيكَل (مرآة JSON الهدف، عربيّ قابل للتنفيذ)."""

    main_judgement: str  # جملة حاسمة واحدة بالعربيّة
    confidence: float  # [0,1] مزيج ثقات المدخلات + عامل التغطية
    evidence: tuple[str, ...]  # الإشارات/المخاطر/التغذية التي تبرّر الحُكم
    do_today: tuple[str, ...]  # إجراءات تُتّخذ الآن
    avoid_now: tuple[str, ...]  # ما يُتجنَّب فعله الآن
    review_after: str  # أفق المراجعة (غير فارغ دائماً)
    escalate_if: tuple[str, ...]  # شروط التصعيد/الانتباه البشريّ


# ── أدوات مساعدة نقيّة ──
def _clamp01(x: float) -> float:
    """يقصّ القيمة إلى [0,1]."""
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _signal_map(signals: tuple) -> dict:
    """يبني خريطة signal_type ⇐ أعلى ثقة لكلّ نوع معروف (تجاهل غير المعروف برفق)."""
    out: dict[str, float] = {}
    for s in signals:
        stype = getattr(s, "signal_type", None)
        if stype not in _VALID_SIGNALS:
            continue
        try:
            conf = _clamp01(float(getattr(s, "confidence_score", 0.0)))
        except (TypeError, ValueError):
            conf = 0.0
        if stype not in out or conf > out[stype]:
            out[stype] = conf
    return out


def _high_risk_of(risks: tuple, risk_type: str) -> object | None:
    """يُرجِع أعلى خطر CropRisk من نوع مُعيَّن بدرجة عالية، أو None."""
    best = None
    best_score = _HIGH_RISK_SCORE
    for r in risks:
        if getattr(r, "risk_type", None) != risk_type:
            continue
        try:
            score = float(getattr(r, "score", 0.0))
        except (TypeError, ValueError):
            continue
        if score >= best_score:
            best, best_score = r, score
    return best


def _any_risk_of(risks: tuple, risk_type: str) -> object | None:
    """يُرجِع أوّل خطر CropRisk من نوع مُعيَّن (بأيّ شدّة)، أو None."""
    for r in risks:
        if getattr(r, "risk_type", None) == risk_type:
            return r
    return None


def _aggregate_confidence(
    signal_conf: list[float], soil_conf: float | None, coverage_sources: int
) -> float:
    """يمزج ثقات المدخلات مع عامل تغطية حتميّ، مقصوصاً إلى [0,1] (قسمة محروسة).

    متوسّط ثقات الإشارات/التربة المعروفة (إن وُجدت) يُرفَع بعامل تغطية يتناسب مع عدد
    مصادر السياق الحاضرة (إشارات/مخاطر/تربة/توصية)، بسقف عند ٤ مصادر. غياب كلّ ثقة
    صريحة ⇒ يُعتمَد على التغطية وحدها (ثقة متواضعة لا صفر إن وُجد سياق).
    """
    confs = [c for c in signal_conf if c is not None]
    if soil_conf is not None:
        confs.append(_clamp01(soil_conf))

    coverage = _clamp01(coverage_sources / 4.0)  # ٤ مصادر ممكنة ⇒ تغطية كاملة
    if confs:
        base = sum(confs) / len(confs)
        # التغطية ترفع الأرضيّة: مزيج وزنه ٠٫٧ للثقة الفعليّة و٠٫٣ للتغطية.
        blended = 0.7 * base + 0.3 * coverage
    else:
        # لا ثقة صريحة: التغطية وحدها بسقف متواضع كي لا تتضخّم.
        blended = 0.5 * coverage
    return round(_clamp01(blended), 4)


def build_playbook(ctx: PlaybookContext) -> DecisionPlaybook:
    """يبني دليل القرار المُهيكَل من سياق المنصّة المُجمَّع (نقيّ، حتميّ).

    يختار الحُكم الرئيسيّ بترتيب أولويّة ثابت (صقيع > مرض > إجهاد حراريّ > سوء مرور >
    تغذية راجعة سالبة > فرصة رشّ > روتين)، ويجمع الأدلّة والإجراءات من كلّ الإشارات
    المنطبقة (لا الحُكم الفائز فقط). سياق فارغ ⇒ حُكم محايد منخفض الثقة دون انهيار.
    نفس السياق ⇒ نفس الدليل تماماً. كلّ قسمة محروسة.
    """
    signals = tuple(ctx.weather_signals or ())
    risks = tuple(ctx.crop_risks or ())
    soil = ctx.soil_feedback

    smap = _signal_map(signals)
    signal_confs = list(smap.values())

    # ── كشف الإشارات/المخاطر المنطبقة (حتميّ) ──
    frost_signal = "frost_imminent" in smap
    frost_risk = _high_risk_of(risks, "frost_damage")
    frost = frost_signal or frost_risk is not None

    disease_signal = "disease_risk_high" in smap
    disease_risk = _high_risk_of(risks, "fungal_disease")
    disease = disease_signal or disease_risk is not None

    heat_signal = "heat_stress" in smap
    heat_risk = _any_risk_of(risks, "heat_stress")
    heat = heat_signal or heat_risk is not None

    traffic = "trafficability_poor" in smap
    spray = "spray_window_open" in smap

    # ── التغذية الراجعة نبات-تربة ──
    soil_dir = getattr(soil, "direction", None) if soil is not None else None
    raw_conf = getattr(soil, "confidence", None) if soil is not None else None
    try:
        soil_conf = float(raw_conf) if raw_conf is not None else None
    except (TypeError, ValueError):
        soil_conf = None
    soil_meaningful = soil_conf is not None and soil_conf >= _MIN_SOIL_CONFIDENCE
    soil_negative = soil_meaningful and soil_dir == "negative"
    soil_positive = soil_meaningful and soil_dir == "positive"

    evidence: list[str] = []
    do_today: list[str] = []
    avoid_now: list[str] = []
    escalate_if: list[str] = []

    crop_tag = f" على {ctx.crop}" if ctx.crop else ""

    # ── بناء الأدلّة/الإجراءات لكلّ موضوع منطبق (مستقلّ عن الحُكم الفائز) ──
    if frost:
        if frost_signal:
            hours = ""
            payload = next(
                (
                    getattr(s, "payload", {})
                    for s in signals
                    if getattr(s, "signal_type", None) == "frost_imminent"
                ),
                {},
            )
            fh = payload.get("frost_hours") if isinstance(payload, dict) else None
            if fh:
                hours = f" ({fh} ساعة تحت الحرج)"
            evidence.append(f"إشارة صقيع وشيك{hours}.")
        if frost_risk is not None:
            evidence.append(getattr(frost_risk, "reason_ar", "خطر ضرر صقيع عالٍ."))
        do_today.append("نفّذ حماية من الصقيع: ريّ وقائيّ مسائيّ و/أو تغطية النبات.")
        avoid_now.append("لا رشّ ولا تسميد ورقيّ الليلة (يفاقم ضرر الصقيع).")
        escalate_if.append("استمرّ الصقيع ليلة أخرى أو هبطت الحرارة أكثر من المتوقّع.")

    if disease:
        if disease_signal:
            evidence.append("إشارة خطر مرض فطريّ مرتفع من تراكب الطقس.")
        if disease_risk is not None:
            evidence.append(getattr(disease_risk, "reason_ar", "خطر مرض فطريّ عالٍ."))
        do_today.append(f"نفّذ فحصاً حقليّاً{crop_tag} ورشّاً وقائيّاً مناسباً للمرض الفطريّ.")
        avoid_now.append("تجنّب ريّ الغمر المسائيّ الذي يرفع الرطوبة ويُفضّل العدوى.")
        escalate_if.append("ظهرت بؤر إصابة فعليّة أو اتّسعت رقعة الأعراض.")

    if heat:
        if heat_signal:
            evidence.append("إشارة إجهاد حراريّ من تراكب الطقس.")
        if heat_risk is not None:
            evidence.append(getattr(heat_risk, "reason_ar", "إجهاد حراريّ على المحصول."))
        do_today.append("عدّل جدولة الريّ لتخفيف الإجهاد الحراريّ (ريّ مبكّر/مسائيّ).")
        avoid_now.append("تجنّب العمليّات الحقليّة تحت ذروة الحرّ.")

    if traffic:
        evidence.append("صلاحيّة مرور التربة ضعيفة (رطوبة/تشبُّع).")
        avoid_now.append("تجنّب دخول الآليّات الثقيلة الآن (خطر انضغاط التربة).")

    if soil_negative:
        evidence.append(
            getattr(soil, "verdict_ar", "تغذية راجعة نبات-تربة سالبة: مخاطر تراكم ممرضات.")
        )
        if float(getattr(soil, "pathogen_accumulation_risk", 0.0)) >= _HIGH_PATHOGEN_RISK:
            evidence.append("مؤشّر تراكم الممرضات في التربة مرتفع.")
        do_today.append("خطّط لتنويع الدورة الزراعيّة وإضافة مادّة عضويّة لكسر دورة الممرضات.")
        escalate_if.append("تكرّر تدهور مؤشّر التربة موسماً آخر رغم التدخّل.")
    elif soil_positive:
        evidence.append(
            getattr(soil, "verdict_ar", "تغذية راجعة نبات-تربة موجبة: القاعدة الترابيّة سليمة.")
        )

    if spray:
        spray_conf = smap.get("spray_window_open", 0.0)
        evidence.append(f"نافذة رشّ مفتوحة (ثقة {spray_conf:.2f}).")
        if not (frost or disease):
            do_today.append("نفّذ الرشّ المخطّط ضمن النافذة المفتوحة الآن.")
        else:
            avoid_now.append("أجّل الرشّ المخطّط: حاجب أهمّ (صقيع/مرض) يسبق فرصة الرشّ.")

    if ctx.recommendation_ar:
        evidence.append(f"توصية علويّة: {ctx.recommendation_ar}")

    # ── اختيار الحُكم الرئيسيّ + أفق المراجعة بترتيب الأولويّة الثابت ──
    has_any_context = bool(signals or risks or soil is not None or ctx.recommendation_ar)

    if frost:
        main_judgement = f"خطر صقيع وشيك{crop_tag}: الأولويّة حماية فوريّة من الصقيع."
        review_after = _HORIZON_URGENT
    elif disease:
        main_judgement = f"خطر مرض فطريّ مرتفع{crop_tag}: فحص ورشّ وقائيّ عاجل."
        review_after = _HORIZON_SOON
    elif heat:
        main_judgement = f"إجهاد حراريّ{crop_tag}: عدّل الريّ لتخفيف الإجهاد."
        review_after = _HORIZON_SOON
    elif traffic:
        main_judgement = "صلاحيّة مرور التربة ضعيفة: أجّل العمليّات الآليّة الثقيلة."
        review_after = _HORIZON_SOON
    elif soil_negative:
        main_judgement = "تغذية راجعة نبات-تربة سالبة: تدخّل لكسر تراكم الممرضات."
        review_after = _HORIZON_SEASONAL
    elif spray:
        main_judgement = "نافذة رشّ مفتوحة: نفّذ الرشّ المخطّط ضمن النافذة."
        review_after = _HORIZON_ROUTINE
    elif not has_any_context:
        main_judgement = "بيانات غير كافية: لا إشارات متاحة لإصدار توصية حاسمة."
        review_after = _HORIZON_ROUTINE
        if not evidence:
            evidence.append("لا توجد إشارات طقس أو مخاطر أو تغذية راجعة في السياق الحاليّ.")
    else:
        # يوجد سياق لكن لا موضوع لافت (مثلاً تربة موجبة/توصية هادئة فقط).
        if soil_positive:
            main_judgement = "الوضع مستقرّ والقاعدة الترابيّة سليمة: واصل الإدارة الحاليّة."
        else:
            main_judgement = "الوضع مستقرّ: لا مخاطر لافتة الآن، استمرّ بالمتابعة المعتادة."
        review_after = _HORIZON_ROUTINE
        if not evidence:
            evidence.append("فُحِص السياق المتاح ولم تُطلَق إشارات مخاطر مُلحّة.")

    # ── عدّ مصادر السياق الحاضرة لعامل التغطية ──
    coverage_sources = sum(
        [bool(signals), bool(risks), soil is not None, bool(ctx.recommendation_ar)]
    )
    confidence = _aggregate_confidence(signal_confs, soil_conf, coverage_sources)

    # سقف الأدلّة (إبقاء الناتج قابلاً للتنفيذ) مع الحفاظ على الترتيب الحتميّ.
    evidence = evidence[:_MAX_EVIDENCE]

    return DecisionPlaybook(
        main_judgement=main_judgement,
        confidence=confidence,
        evidence=tuple(evidence),
        do_today=tuple(do_today),
        avoid_now=tuple(avoid_now),
        review_after=review_after,
        escalate_if=tuple(escalate_if),
    )
