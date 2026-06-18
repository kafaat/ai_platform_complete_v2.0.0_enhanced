"""core/crop_rotation_intelligence.py — ذكاء التناوب الزراعيّ (نقيّ، حتميّ).

مُستوحى من مراجعة Science «توجيه التغذية الراجعة نبات-تربة لزراعة مستدامة»
(Steering plant-soil feedback for sustainable agriculture). المبدأ الزراعيّ:

  • الزراعة الأحاديّة (monoculture) — تكرار نفس المحصول أو نفس العائلة النباتيّة
    موسماً بعد موسم — تُراكِم ممرضات خاصّة بالعائل (host-specific pathogens) ⇒
    تغذية راجعة **سالبة** نبات-تربة (negative plant-soil feedback).
  • تنوّع التناوب، والبقوليّات (تثبيت النيتروجين)، ومحاصيل الغطاء (cover crops)،
    والتحميل البينيّ (intercropping) ⇒ تغذية راجعة **موجبة** (positive feedback).

تأخذ هذه الوحدة سجلّ مواسم زمنيّاً (الأقدم→الأحدث) وتُخرِج تقييماً قابلاً للتبرير
(Explainable) بمؤشّرات [0,1] ودرجة تناوب [0,100] واتّجاه التغذية الراجعة وأدلّة عربيّة.

— تعريف المؤشّرات (موثّقة وحتميّة) —
  • `rotation_diversity_index`: نسبة المفاتيح المميّزة (العائلة إن وُجدت وإلّا المحصول)
    إلى عدد المواسم، مقصوصة إلى [0,1]. 1.0 ⇒ كلّ موسم مختلف؛ قِيَم أدنى ⇒ تكرار.
  • `legume_ratio` / `cover_crop_ratio` / `intercropping_ratio`: كسر المواسم التي
    تحتوي السمة (البقوليّ يُحتسب من المحصول الرئيس أو أحد المحمّلين البينيّين).
  • `host_repeat_risk`: مقدار التكرار المتتالي لنفس المفتاح = (عدد المواقع التي ساوى
    فيها المفتاحُ سابقَه المباشر) ÷ (عدد المواسم−1)، مقصوص إلى [0,1]. 0 ⇒ لا تكرار
    متتالٍ؛ 1 ⇒ زراعة أحاديّة صرفة. `max_consecutive_same` = أطول جريّة متتالية للمفتاح.

— درجة التناوب (rotation_score ∈ [0,100]) —
  مزيج مرجَّح: التنوّع (٤٠٪) + البقوليّات (٢٠٪) + الغطاء (١٠٪) + التحميل البينيّ (١٠٪)
  + (١−خطر التكرار) (٢٠٪)، الكلّ ×100. أعلى = تنوّع/بقوليّات/غطاء أكثر وتكرار أقلّ.

— الاتّجاه (direction) —
  يُشتقّ حتميّاً: `host_repeat_risk ≥ 0.5` يفرض «negative» (تراكم ممرضات غالب) بصرف
  النظر عن الدرجة. وإلّا: درجة ≥ 60 ⇒ «positive»، درجة ≤ 35 ⇒ «negative»، بينهما
  ⇒ «neutral». السجلّ الفارغ ⇒ «neutral» (بيانات غير كافية، لا انهيار).

نقيّ تماماً: لا I/O، لا شبكة، لا قاعدة، لا عشوائيّة، بلا numpy — stdlib + dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── أوزان درجة التناوب (تُجمَع إلى 1.0) ──
_W_DIVERSITY = 0.40  # التنوّع هو المحرّك الأكبر للتغذية الراجعة الموجبة
_W_LEGUME = 0.20  # تثبيت النيتروجين عبر البقوليّات
_W_COVER = 0.10  # محاصيل الغطاء
_W_INTERCROP = 0.10  # التحميل البينيّ
_W_LOW_REPEAT = 0.20  # غياب التكرار المتتالي (مقلوب خطر العائل)

# ── عتبات الاتّجاه (موثّقة في docstring الوحدة) ──
_REPEAT_FORCE_NEGATIVE = 0.5  # خطر تكرار ≥ هذا ⇒ negative قسراً
_POSITIVE_SCORE = 60.0  # درجة ≥ هذا ⇒ positive
_NEGATIVE_SCORE = 35.0  # درجة ≤ هذا ⇒ negative

# معرّفات محاصيل بقوليّة معروفة — تُستخدم لرصد البقوليّ في التحميل البينيّ (حيث لا
# يحمل المحمَّل البينيّ علَماً مستقلّاً). القائمة إرشاديّة قابلة للتوسعة محلّيّاً.
_LEGUME_CROP_IDS = frozenset(
    {
        "bean",
        "beans",
        "faba_bean",
        "broad_bean",
        "chickpea",
        "lentil",
        "pea",
        "peas",
        "cowpea",
        "soybean",
        "soy",
        "alfalfa",
        "clover",
        "peanut",
        "groundnut",
        "lupin",
        "vetch",
        "mung_bean",
        "lablab",
        "fenugreek",
    }
)


@dataclass(frozen=True)
class SeasonCrop:
    """زراعة موسم واحد: المعرّفات + سمات التغذية الراجعة (بقوليّ/غطاء/تحميل بينيّ)."""

    season_id: str
    crop_id: str
    crop_family: str | None = None  # العائلة النباتيّة (تُفضّل للتكرار/التنوّع إن وُجدت)
    is_legume: bool = False  # بقوليّ (مثبِّت نيتروجين)
    is_cover_crop: bool = False  # محصول غطاء
    intercropped_with: tuple[str, ...] = ()  # محاصيل محمّلة بينيّاً مع الرئيس


@dataclass(frozen=True)
class RotationAssessment:
    """تقييم تناوب قابل للتبرير: مؤشّرات [0,1] + درجة [0,100] + اتّجاه + أدلّة عربيّة."""

    seasons_analyzed: int
    rotation_diversity_index: float  # [0,1]
    legume_ratio: float  # [0,1]
    cover_crop_ratio: float  # [0,1]
    intercropping_ratio: float  # [0,1]
    host_repeat_risk: float  # [0,1] — أعلى = تكرار متتالٍ أكثر (تراكم ممرضات)
    max_consecutive_same: int  # أطول جريّة لنفس المحصول/العائلة متتالية
    rotation_score: float  # [0,100] جودة التناوب الإجماليّة
    direction: str  # positive | negative | neutral
    evidence_ar: tuple[str, ...] = ()  # عبارات تفسير المحرّكات الرئيسة
    verdict_ar: str = ""  # حُكم عربيّ من سطر واحد


def _clamp01(x: float) -> float:
    """يقصّ القيمة إلى [0,1]."""
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _key(season: SeasonCrop) -> str:
    """مفتاح التكرار/التنوّع: العائلة إن وُجدت، وإلّا المحصول (تراجُع آمن)."""
    return season.crop_family if season.crop_family else season.crop_id


def _has_legume(season: SeasonCrop) -> bool:
    """هل يحتوي الموسم بقوليّاً؟ (المحصول الرئيس أو أحد المحمّلين البينيّين).

    يُحتسب الموسم بقوليّاً إذا رُفِع علَم `is_legume`، أو كان `crop_id` الرئيس بقوليّاً
    معروفاً، أو احتوى التحميل البينيّ على معرّف بقوليّ معروف (تثبيت نيتروجين بينيّ).
    """
    if season.is_legume:
        return True
    if season.crop_id in _LEGUME_CROP_IDS:
        return True
    return any(c in _LEGUME_CROP_IDS for c in season.intercropped_with)


def _empty_assessment() -> RotationAssessment:
    """تقييم السجلّ الفارغ: محايد، أصفار، دليل عربيّ على عدم كفاية البيانات."""
    return RotationAssessment(
        seasons_analyzed=0,
        rotation_diversity_index=0.0,
        legume_ratio=0.0,
        cover_crop_ratio=0.0,
        intercropping_ratio=0.0,
        host_repeat_risk=0.0,
        max_consecutive_same=0,
        rotation_score=0.0,
        direction="neutral",
        evidence_ar=("سجلّ المواسم فارغ — بيانات غير كافية لتقييم التناوب.",),
        verdict_ar="غير حاسم: لا سجلّ مواسم لتقييم التغذية الراجعة نبات-تربة.",
    )


def _max_consecutive_run(keys: list[str]) -> int:
    """أطول جريّة متتالية لنفس المفتاح. مثال: [A,A,A,B] ⇒ 3؛ [A,B,A,B] ⇒ 1."""
    if not keys:
        return 0
    max_run = 1
    run = 1
    for i in range(1, len(keys)):
        if keys[i] == keys[i - 1]:
            run += 1
            max_run = run if run > max_run else max_run
        else:
            run = 1
    return max_run


def _direction_for(score: float, host_repeat_risk: float) -> str:
    """يشتقّ اتّجاه التغذية الراجعة حتميّاً (التكرار الثقيل يفرض negative)."""
    if host_repeat_risk >= _REPEAT_FORCE_NEGATIVE:
        return "negative"
    if score >= _POSITIVE_SCORE:
        return "positive"
    if score <= _NEGATIVE_SCORE:
        return "negative"
    return "neutral"


def assess_rotation(history: list[SeasonCrop]) -> RotationAssessment:
    """يُقيّم سجلّ تناوب المواسم ويُعيد تقييماً قابلاً للتبرير (نقيّ، حتميّ).

    `history` مُرتَّب زمنيّاً (الأقدم→الأحدث)؛ يُستخدم الترتيب لكشف التكرار المتتالي.
    يُستخدم `crop_family` للتكرار/التنوّع متى توفّر، وإلّا يُتراجَع إلى `crop_id`.

    المنطق الزراعيّ: تنوّع/بقوليّات/غطاء/تحميل بينيّ ⇒ تغذية راجعة موجبة؛ تكرار نفس
    العائل متتالياً ⇒ تراكم ممرضات ⇒ تغذية راجعة سالبة. درجة التناوب مزيج مرجَّح
    (تنوّع ٤٠٪ + بقوليّات ٢٠٪ + غطاء ١٠٪ + تحميل ١٠٪ + غياب تكرار ٢٠٪) ×100.

    الاتّجاه: `host_repeat_risk ≥ 0.5` ⇒ «negative» قسراً؛ وإلّا درجة ≥ 60 ⇒ «positive»،
    ≤ 35 ⇒ «negative»، بينهما ⇒ «neutral». السجلّ الفارغ ⇒ تقييم محايد بلا انهيار،
    وكلّ القسمة محروسة (لا قسمة على صفر).
    """
    n = len(history)
    if n == 0:
        return _empty_assessment()

    keys = [_key(s) for s in history]

    # ── التنوّع: نسبة المفاتيح المميّزة إلى عدد المواسم ──
    distinct = len(set(keys))
    diversity = _clamp01(distinct / n)

    # ── النِسَب السمتيّة (محروسة بـ n ≥ 1) ──
    legume_ratio = _clamp01(sum(1 for s in history if _has_legume(s)) / n)
    cover_ratio = _clamp01(sum(1 for s in history if s.is_cover_crop) / n)
    intercrop_ratio = _clamp01(sum(1 for s in history if s.intercropped_with) / n)

    # ── خطر تكرار العائل ──
    # `max_run` = أطول جريّة متتالية لنفس المفتاح. خطر التكرار = عدد المواقع التي
    # ساوى فيها المفتاحُ سابقَه ÷ (n−1) = أقصى تكرار متتالٍ ممكن. n=1 ⇒ لا خطر.
    max_run = _max_consecutive_run(keys)
    denom = n - 1
    if denom <= 0:
        host_repeat_risk = 0.0  # موسم واحد: لا تكرار متتالٍ مُمكن
    else:
        consecutive_repeats = sum(1 for i in range(1, n) if keys[i] == keys[i - 1])
        host_repeat_risk = _clamp01(consecutive_repeats / denom)

    # ── درجة التناوب [0,100] ──
    score01 = (
        _W_DIVERSITY * diversity
        + _W_LEGUME * legume_ratio
        + _W_COVER * cover_ratio
        + _W_INTERCROP * intercrop_ratio
        + _W_LOW_REPEAT * (1.0 - host_repeat_risk)
    )
    rotation_score = round(_clamp01(score01) * 100.0, 2)

    direction = _direction_for(rotation_score, host_repeat_risk)

    # ── الأدلّة العربيّة (تستشهد بالمحرّكات الفعليّة) ──
    evidence: list[str] = []
    evidence.append(f"تنوّع التناوب: {distinct} مفتاح مميّز عبر {n} موسم (مؤشّر {diversity:.2f}).")
    if legume_ratio > 0.0:
        evidence.append(
            f"وجود بقوليّات يثبّت النيتروجين في {legume_ratio:.0%} من المواسم → تغذية راجعة موجبة."
        )
    else:
        evidence.append("لا بقوليّات في السجلّ — فرصة ضائعة لتثبيت النيتروجين.")
    if cover_ratio > 0.0:
        evidence.append(
            f"محاصيل غطاء في {cover_ratio:.0%} من المواسم تحمي التربة وتغذّي الميكروبيوم."
        )
    if intercrop_ratio > 0.0:
        evidence.append(f"تحميل بينيّ في {intercrop_ratio:.0%} من المواسم يزيد التنوّع الحيويّ.")
    if max_run > 1:
        evidence.append(
            f"تكرار نفس المحصول/العائلة {max_run} مواسم متتالية "
            "→ تراكم ممرضات خاصّة بالعائل (تغذية راجعة سالبة)."
        )
    else:
        evidence.append("لا تكرار متتالٍ لنفس العائل — خطر تراكم الممرضات منخفض.")

    # ── الحكم العربيّ من سطر واحد ──
    if direction == "positive":
        verdict = (
            f"تناوب جيّد (درجة {rotation_score:.0f}/100): تنوّع/بقوليّات تدفع "
            "تغذية راجعة موجبة نبات-تربة."
        )
    elif direction == "negative":
        verdict = (
            f"تناوب ضعيف (درجة {rotation_score:.0f}/100): تكرار العائل يدفع "
            "تغذية راجعة سالبة — نوّع المحاصيل وأدخِل بقوليّات/غطاء."
        )
    else:
        verdict = (
            f"تناوب متوسّط (درجة {rotation_score:.0f}/100): حسّن التنوّع والبقوليّات "
            "لترجيح التغذية الراجعة الموجبة."
        )

    return RotationAssessment(
        seasons_analyzed=n,
        rotation_diversity_index=round(diversity, 4),
        legume_ratio=round(legume_ratio, 4),
        cover_crop_ratio=round(cover_ratio, 4),
        intercropping_ratio=round(intercrop_ratio, 4),
        host_repeat_risk=round(host_repeat_risk, 4),
        max_consecutive_same=max_run,
        rotation_score=rotation_score,
        direction=direction,
        evidence_ar=tuple(evidence),
        verdict_ar=verdict,
    )
