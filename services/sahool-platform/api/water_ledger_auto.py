"""api/water_ledger_auto.py — منطق نقيّ لأتمتة ميزان الماء اليوميّ (FAO-56 accumulation).

يحسب قيد دفتر المياه لليوم من قيد الأمس + مدخلات اليوم الحقيقيّة:

    Dr_t = clamp( Dr_{t-1} + ETc_t − P_eff_t − I_t , 0 , TAW )

الصدق قبل كلّ شيء:
  • لا اختلاق مدخلات: ET0 يأتي من محرّك الطقس (المصدر الوحيد)، المطر من التوقّع
    اليوميّ، والريّ من دفتر التشغيلات ``irrigation_runs`` — غياب أيّها يوقف حساب
    اليوم (skip مُعلَّل) ولا يُستبدَل بصفر مُختلَق.
  • bootstrap مُعلَن: أوّل يوم بلا قيد سابق يبدأ من Dr=0 (افتراض سعة حقليّة بعد
    ترطيب — التهيئة القياسيّة في FAO-56) مع خفض الثقة وذكر الافتراض في القرار.
  • تشغيلات ريّ بلا حجم mm تُحتسَب صفراً مع علمٍ مُعلَن ``irrigation_volume_untracked``
    (القيد يبقى أدنى تقدير للريّ لا أعلاه).
  • القيد اليدويّ سيّد: العامل لا يلمس قيد يومٍ أنشأه إنسان (يُقرَّر خارج هذه الدالّة).

نقيّ حتميّ (لا I/O) — كلّ المدخلات تُمرَّر صراحةً؛ يُختبَر بلا قاعدة.
"""

from __future__ import annotations

import math

from api.water_balance import _effective_rain

# هويّة الكاتب الآليّ في created_by — بها يُميَّز قيد العامل من القيد اليدويّ.
AUTO_CREATED_BY = "water-balance-auto"

# ثقة القيد الآليّ: مدخلات حقيقيّة لكن TAW/Kc قد يكونان fallback — أدنى من قيد ميدانيّ.
CONFIDENCE_AUTO = 0.7
# أوّل قيد (bootstrap من Dr=0) أدنى ثقة حتى تتراكم أيّام حقيقيّة فوقه.
CONFIDENCE_BOOTSTRAP = 0.4

#: افتراضاتٌ مُعلَنةٌ **تُحيّز** النتيجة — `UNRECORDED-IRRIGATION-READ-AS-ZERO-APPLIED-WATER-01`.
#:
#: **العطلُ مقيسٌ في هذا الملفّ نفسِه:** كانت الثقةُ دالّةً على `bootstrap` وحدَه، فيوماً
#: أقرّ فيه القيدُ صراحةً أنّ حدّاً من معادلة الميزان **مفترَضٌ لا مقيس** كان يخرج بـ
#: `CONFIDENCE_AUTO` — الثقةِ نفسِها ليومٍ قِيست مدخلاتُه كلُّها. الملاحظةُ تُكتب في
#: `notes` ولا يسمعها شيء: مَن يقرأ الصفَّ يرى رقمَ ثقةٍ كاملاً.
#:
#: **والاتّجاه واحدٌ وهو الأسوأ:** كلا الافتراضين يرفع `raw_depletion`
#: (`prev + etc − p_eff − irrigation_mm`) — ريٌّ غيرُ مُقاسٍ يُحتسَب أقلَّ ممّا وقع،
#: وهطولٌ مفقودٌ يُفترَض صفراً. فالنتيجةُ استنزافٌ مُبالَغٌ فيه ⇒ **توصيةُ ريٍّ فوق ريٍّ
#: حصل**، على خزّاناتٍ جوفيّةٍ متراجعة. حيازةٌ في اتّجاهٍ معروف، لا ضجيجٌ متماثل.
#:
#: **والسقفُ مُشتقٌّ لا مُختلَق:** يومٌ يقوم على حدٍّ مفترَضٍ لا يجوز أن يكون **أوثقَ**
#: من يومٍ افتُرِضت نقطةُ بدايته (`bootstrap`). فلا ثابتَ ثالثاً يُخترَع رقمُه.
#:
#: **ولا يشمل هذا «مقيسٌ = صفر»:** المُستدعي يفرّق (`_precip is None`)، فالعلَمُ لا
#: يُطلَق على يومٍ جافٍّ مقيس — وإلّا صارت أكثرُ الأيّام منخفضةَ الثقة بلا سبب.
#: **و`irrigation_unobserved` ثالثُها، وهو أوسعُها أثراً:** صفرُ صفوفٍ في
#: ``irrigation_runs`` كان يُقرأ «رُصد أنّه لم يُروَ» فيدخل الميزانَ ريّاً مقداره صفر.
#: والصادقُ «**لم يُرصَد له سجلُّ ريّ**» — عبارةٌ صحيحةٌ للحقل المطريّ وللمرويّ من بئرٍ
#: بلا تسجيل معاً. فلا يُخترَع تمييزٌ لا تسنده البيانات، ولا يُدَّعى قياسٌ لم يقع.
#:
#: ولا يُلغى حسابُ اليوم: الدفترُ يبقى **أدنى تقديرٍ للماء المضاف**، وتُخفَّض ثقتُه.
#: إلغاؤه كان سيحرم الحقلَ المطريَّ الصادقَ من ميزانه — عطلٌ معاكسُ الاتّجاه.
#:
#: **واثنان لا اتّجاهَ معروفاً لهما، ويدخلان بحجّة السقف نفسها لا بحجّة الاتّجاه:**
#: ``et0_reference_unavailable`` (ET0 بـHargreaves المتدهور لا Penman-Monteith) و
#: ``root_zone_texture_fallback`` (عمقٌ افتراضيّ من جدول قوام لا منطقةُ الجذور القانونيّة).
#: كلاهما حدٌّ مفترَضٌ في الميزان لا مقيس، فلا يكون يومٌ قام عليهما أوثقَ من التهيئة.
_BIASING_ASSUMPTIONS = frozenset(
    {
        "irrigation_volume_untracked",
        "precipitation_assumed_zero",
        "irrigation_unobserved",
        "et0_reference_unavailable",
        "root_zone_texture_fallback",
        "irrigation_unknown_inherited",
    }
)


#: حالةُ **الماء المضاف** في القيد — ما يقوله الدفترُ عن حدِّ ``irrigation_mm`` نفسِه.
#:
#: **العطلُ الذي بقي بعد #1070:** خُفِّضت الثقةُ رقماً (0.4) ولم يُسمَّ السبب لمن يستهلك
#: القيد. الجسرُ المحكوم يقرأ ``deficit_mm`` ويُنفِّذ ريّاً آليّاً بمقداره، وتوصيةُ الحقل
#: تقرأ ``depletion_mm`` — وكلاهما لا يرى أنّ الريَّ في المعادلة **صفرٌ لأنّه مجهول** لا
#: لأنّه قِيس صفراً. رقمُ ثقةٍ لا يُميِّز «مجهولُ الريّ» من «تربةٌ افتراضيّة»، والأوّلُ
#: وحدَه يجعل كمّيّةَ الريّ الموصى بها **فوق** ما يلزم (الاتّجاه معروف، لا ضجيج).
#:
#: ``recorded``         صفوفُ ريٍّ مكتملةٌ بأحجامٍ مقيسة (أو مجموعٌ صفريٌّ من صفوفٍ موجودة).
#: ``unrecorded``       لا صفَّ أصلاً — «لم يُرصَد سجلُّ ريّ»، لا «لم يُروَ».
#: ``volume_untracked`` صفٌّ موجودٌ بحجمٍ غائب — رُصد ريٌّ وجُهِل مقدارُه.
#:
#: **ولا يُخترَع تمييزٌ لا تسنده البيانات:** الحقلُ المطريّ والمرويُّ من بئرٍ بلا تسجيل
#: كلاهما ``unrecorded`` — والتمييزُ بينهما شرطُ الإغلاق (إعدادُ مصادر الماء لكلّ حقلٍ
#: وموسم)، لا استنتاجٌ من غياب الصفوف.
#: ``inherited_unknown`` ريُّ اليوم مقيس، لكنّ الاستنزافَ **الموروث** من قيدٍ سابقٍ ريُّه مجهول.
#:
#: **العطلُ الذي بقي بعد الخطوة الجزئيّة:** العلَمُ يوميٌّ لا يرث — يومٌ له ريّةٌ مسجّلة فوق
#: أيّامٍ بلا سجلّ كان يعود ``recorded`` واستنزافُه ``prev + …`` مبنيٌّ على ريٍّ مجهول.
#: **والحدُّ الأعلى رياضيٌّ لا تقدير:** الريُّ المجهول لا يُنقِص إلّا ``raw_depletion``،
#: والقصُّ إلى ``[0, TAW]`` رتيب، فالاستنزافُ المحسوبُ **حدٌّ أعلى** للحقيقيّ ما دام في
#: السلسلة ريٌّ مجهول. ولذا ينقطع الإرث عند استنزافٍ محسوبٍ **صفر**: حدٌّ أعلى صفرٌ ⇒ الحقيقيّ
#: صفرٌ بالضبط، والماضي لا يُحيّز ما بعده. وينقطع عند التهيئة وعند القيد اليدويّ (بدايةُ سلسلة).
APPLIED_WATER_RECORDED = "recorded"
APPLIED_WATER_UNRECORDED = "unrecorded"
APPLIED_WATER_VOLUME_UNTRACKED = "volume_untracked"
APPLIED_WATER_INHERITED_UNKNOWN = "inherited_unknown"

#: كلُّ حالةٍ لا يكون فيها حدُّ الريّ في الميزان مقيساً (اليومَ أو موروثاً).
_APPLIED_WATER_UNKNOWN = frozenset(
    {APPLIED_WATER_UNRECORDED, APPLIED_WATER_VOLUME_UNTRACKED, APPLIED_WATER_INHERITED_UNKNOWN}
)

#: نافذةُ السلسلة التي يمشيها المستهلك بحثاً عن مرساة (> موسمٍ كامل من القيود اليوميّة).
LEDGER_CHAIN_WINDOW = 400

_BOOTSTRAP_NOTE = "bootstrap_assumed_field_capacity"


def applied_water_status(notes) -> str:
    """حالةُ الماء المضاف من أعلام القيد — مشتقّةٌ من ``notes`` لا من قائمةٍ ثانية.

    حالةُ اليوم نفسِه تتقدّم على الموروثة: ريٌّ مجهولٌ اليوم يُسمّى باسمه.
    """
    if "irrigation_unobserved" in notes:
        return APPLIED_WATER_UNRECORDED
    if "irrigation_volume_untracked" in notes:
        return APPLIED_WATER_VOLUME_UNTRACKED
    if "irrigation_unknown_inherited" in notes:
        return APPLIED_WATER_INHERITED_UNKNOWN
    return APPLIED_WATER_RECORDED


def irrigation_known(status: str | None) -> bool | None:
    """هل حدُّ الريّ في الميزان مقيس؟ ``None`` = القيد لم يُعلِن (يدويّ/قديم) — لا يُفترَض."""
    if status is None:
        return None
    return status == APPLIED_WATER_RECORDED


def depletion_is_upper_bound(status: str | None, depletion_mm) -> bool:
    """الاستنزافُ حدٌّ أعلى لا تقدير: ريٌّ مجهولٌ في السلسلة واستنزافٌ محسوبٌ فوق الصفر.

    حدٌّ أعلى صفرٌ ليس حدّاً بل قيمةٌ مضبوطة (الحقيقيّ ∈ [0, 0]) — فلا يُسقَط.
    """
    if status not in _APPLIED_WATER_UNKNOWN or depletion_mm is None:
        return False
    return float(depletion_mm) > 0.0


def _carries_unknown_applied_water(prev_status: str | None, prev_depletion_mm: float) -> bool:
    """هل يُحيّز ريٌّ مجهولٌ في قيد الأمس استنزافَ اليوم؟ (المرساةُ الصفريّة تقطع الإرث)."""
    return prev_status in _APPLIED_WATER_UNKNOWN and prev_depletion_mm > 0.0


def ledger_chain_applied_water_status(rows) -> str | None:
    """حالةُ الماء المضاف **للسلسلة** التي يقوم عليها أحدثُ قيد — لا ليومه وحدَه.

    ``rows``: قيودُ الدفتر للحقل، الأحدثُ أوّلاً، كلٌّ بمفتاحَي ``decision`` و``depletion_mm``.
    يمشي إلى الخلف حتّى مرساة: قيدٌ يدويّ (الإنسان سيّد الدفتر) · استنزافٌ صفر (مضبوط) ·
    تهيئةٌ بريٍّ مقيس. قيدٌ ريُّه مجهولٌ قبل المرساة ⇒ ``inherited_unknown``. **ونفادُ النافذة
    بلا مرساة ⇒ ``inherited_unknown``**: لا دليلَ أنّ السلسلة بدأت من حالةٍ معلومة، والغيابُ
    لا يُقرأ «مُسجَّلاً».

    ``None`` حين لا قيد أو حين أحدثُ قيدٍ يدويّ/قديم — لا يُدَّعى عنه ما لم يُعلِنه.
    """
    if not rows:
        return None
    head = ledger_notes_from_decision(rows[0].get("decision"))
    if head is None:
        return None
    own = applied_water_status(head)
    if own != APPLIED_WATER_RECORDED:
        return own
    for row in rows:
        notes = ledger_notes_from_decision(row.get("decision"))
        depletion = row.get("depletion_mm")
        if notes is None or (depletion is not None and float(depletion) <= 0.0):
            return APPLIED_WATER_RECORDED
        if applied_water_status(notes) != APPLIED_WATER_RECORDED:
            return APPLIED_WATER_INHERITED_UNKNOWN
        if _BOOTSTRAP_NOTE in notes:
            return APPLIED_WATER_RECORDED
    return APPLIED_WATER_INHERITED_UNKNOWN


def ledger_notes_from_decision(decision: str | None) -> list[str] | None:
    """أعلامُ القيد الآليّ من عمود ``decision`` المخزَّن (``auto:a;b`` · ``auto:daily_balance``).

    ``None`` لقيدٍ لم يكتبه العامل (يدويّ أو قديم): لا يُدَّعى عنه ما لم يُعلِنه.
    """
    if not isinstance(decision, str) or not decision.startswith("auto:"):
        return None
    body = decision[len("auto:") :]
    if body == "daily_balance":
        return []
    return [note for note in body.split(";") if note]


def compute_daily_ledger_entry(
    *,
    prev_depletion_mm: float | None,
    taw_mm: float,
    raw_mm: float,
    et0_mm: float,
    kc: float,
    rain_mm: float,
    irrigation_mm: float,
    irrigation_volume_untracked: bool = False,
    irrigation_unobserved: bool = False,
    rain_assumed_zero: bool = False,
    et0_reference_unavailable: bool = False,
    root_zone_texture_fallback: bool = False,
    depletion_fraction_default: bool = False,
    prev_applied_water_status: str | None = None,
) -> dict:
    """قيد اليوم من قيد الأمس + مدخلات اليوم — نقيّ، مع افتراضات مُعلَنة لا صامتة.

    Returns dict بمفاتيح أعمدة ``water_ledger`` الحسابيّة + ``notes`` (قائمة أعلام
    الافتراضات) و``bootstrap`` و``confidence``، و``irrigation_known`` و
    ``depletion_is_upper_bound`` صريحَين: صفرُ صفوفِ ريٍّ «مجهول» لا «صفر».

    ``prev_applied_water_status``: حالةُ الماء المضاف في قيد الأمس. ريٌّ مجهولٌ هناك يُورَّث
    (``irrigation_unknown_inherited``) ما لم يكن استنزافُ الأمس صفراً. ``None`` = لم يُعلَن.
    """
    # D08 — **التناهي قبل أيّ مقارنة.**
    #
    # العطل: كلُّ مقارنةٍ مع ``NaN`` تُرجِع ``False``، فيمرّ من ``taw_mm <= 0`` ومن
    # ``et0_mm < 0`` معاً. المقيس: ``et0_mm=NaN`` أنتج نواتجَ ``NaN`` **بثقة 0.7**،
    # و``Infinity`` أنتج ``ETc`` غيرَ منتهٍ ثمّ قُصَّ الاستنزافُ عند ``TAW`` — برقم
    # الثقة نفسِه. و``taw_mm=NaN`` لم يُرفَض أصلاً.
    #
    # والأثرُ ليس رقماً قبيحاً بل **حالةً غيرَ معرَّفةٍ تُحوَّل إلى قيمةٍ تبدو صحيحة**:
    # القصُّ عند ``TAW`` يُخفي اللانهاية خلف رقمٍ معقول، والثقةُ تُصدَّر كما لو قِيس.
    #
    # و``bool`` يُرفَض مع العدديّ: ``True`` عددٌ في بايثون (``True + 1 == 2``)، فـ
    # ``kc=True`` كان يمرّ ويُحسَب ``ETc = et0 * 1`` بلا أن يُعلن أحدٌ أنّ المعامل راية.
    for _name, _value in (
        ("taw_mm", taw_mm),
        ("raw_mm", raw_mm),
        ("et0_mm", et0_mm),
        ("kc", kc),
        ("rain_mm", rain_mm),
        ("irrigation_mm", irrigation_mm),
    ):
        if isinstance(_value, bool) or not isinstance(_value, (int, float)):
            raise ValueError(f"{_name} يجب أن يكون عدداً (لا رايةً ولا نصّاً) — وصل {_value!r}")
        if not math.isfinite(_value):
            raise ValueError(
                f"{_name} غيرُ منتهٍ ({_value!r}) — حالةٌ غيرُ معرَّفةٍ تُرفَض ولا تُحوَّل "
                "إلى رقمٍ يبدو صحيحاً في دفتر الماء"
            )
    if prev_depletion_mm is not None:
        if isinstance(prev_depletion_mm, bool) or not isinstance(prev_depletion_mm, (int, float)):
            raise ValueError(f"prev_depletion_mm يجب أن يكون عدداً — وصل {prev_depletion_mm!r}")
        if not math.isfinite(prev_depletion_mm):
            raise ValueError(f"prev_depletion_mm غيرُ منتهٍ ({prev_depletion_mm!r})")

    if taw_mm <= 0:
        raise ValueError("TAW يجب أن يكون موجباً — لا يُحسب ميزان بلا سعة ماء متاح")
    if et0_mm < 0 or rain_mm < 0 or irrigation_mm < 0 or kc <= 0:
        raise ValueError("مدخلات سالبة/معدومة غير صالحة لميزان اليوم")
    if raw_mm > taw_mm:
        # RAW جزءٌ من TAW بالتعريف؛ انقلابُهما يجعل عتبةَ الريّ فوق السعة كلّها.
        raise ValueError(f"RAW ({raw_mm}) يتجاوز TAW ({taw_mm}) — علاقةُ سعاتٍ مقلوبة")

    notes: list[str] = []
    if rain_assumed_zero:
        # الطقس لم يُرجِع هطولاً لهذا اليوم ⇒ يُفترَض 0mm **صراحةً** (تقدير محافِظ: أعلى
        # استنزاف) لا تعبئة صامتة. p_eff=0 عندئذٍ. القيد يبقى أدنى تقدير للماء المتاح.
        notes.append("precipitation_assumed_zero")
    bootstrap = prev_depletion_mm is None
    if bootstrap:
        # التهيئة القياسيّة: بداية من السعة الحقليّة (Dr=0) — افتراض مُعلَن لا قياس.
        prev = 0.0
        notes.append("bootstrap_assumed_field_capacity")
    else:
        # قيد أمس قد يكون خارج المدى نظريّاً (إدخال يدويّ قديم) — يُقصّ بإعلان.
        prev = float(prev_depletion_mm)
        if prev < 0 or prev > taw_mm:
            notes.append("previous_depletion_clamped")
            prev = min(max(prev, 0.0), taw_mm)

    etc_mm = round(kc * et0_mm, 2)
    p_eff = _effective_rain(rain_mm)
    if irrigation_volume_untracked:
        notes.append("irrigation_volume_untracked")
    if et0_reference_unavailable:
        notes.append("et0_reference_unavailable")
    if root_zone_texture_fallback:
        notes.append("root_zone_texture_fallback")
    if depletion_fraction_default:
        # عتبةُ الريّ (RAW) لا الاستنزاف: p بلا قيمة جدول للمحصول — يُعلَن ولا يُخفِّض ثقة
        # الاستنزاف نفسه، لأنّه لا يدخل معادلة الميزان.
        notes.append("depletion_fraction_default")
    if irrigation_unobserved:
        # لا صفَّ ريٍّ لهذا اليوم: «لم يُرصَد سجلٌّ» لا «لم يُروَ». يبقى `irrigation_mm`
        # صفراً (لا بيانات تُضاف) والقيدُ أدنى تقدير — والثقةُ تهبط بإعلان.
        notes.append("irrigation_unobserved")
    if not bootstrap and _carries_unknown_applied_water(prev_applied_water_status, prev):
        # الاستنزافُ الموروث حدٌّ أعلى بُنِي على ريٍّ مجهول — يُسمّى ولا يُغسَل بريّةِ اليوم.
        notes.append("irrigation_unknown_inherited")

    raw_depletion = prev + etc_mm - p_eff - irrigation_mm
    depletion_mm = round(min(max(raw_depletion, 0.0), taw_mm), 2)
    if raw_depletion > taw_mm:
        # استنزاف محسوب فوق السعة = إجهاد فعليّ فوق المتاح — يُعلَن لا يُخفى بالقصّ.
        notes.append("depletion_capped_at_taw")

    # العجز عن عتبة الريّ (RAW): موجب ⇒ الريّ مستحقّ بهذا المقدار.
    deficit_mm = round(max(depletion_mm - raw_mm, 0.0), 2)

    return {
        "etc_mm": etc_mm,
        "effective_rain_mm": round(p_eff, 2),
        "depletion_mm": depletion_mm,
        "deficit_mm": deficit_mm,
        "bootstrap": bootstrap,
        # الثقةُ دالّةٌ على **ما افتُرِض**، لا على `bootstrap` وحدَه — شرحُه عند
        # `_BIASING_ASSUMPTIONS`. وتُشتقّ من `notes` لا من الوسائط: علَمٌ يُضاف لاحقاً
        # إلى المجموعة يُخفَّض أثرُه تلقائيّاً، ولا يُنسى سطرٌ ثانٍ يُحدَّث معه.
        "confidence": (
            CONFIDENCE_BOOTSTRAP
            if (bootstrap or _BIASING_ASSUMPTIONS.intersection(notes))
            else CONFIDENCE_AUTO
        ),
        "notes": notes,
        # إضافيّ: يُسمّي سببَ انخفاض الثقة حين يكون الريُّ نفسُه مجهولاً — يقرؤه الجسرُ
        # المحكوم فلا يُنفِّذ آليّاً عجزاً بُنِي على ريٍّ مجهول (``water_decision_bridge``).
        "applied_water_status": applied_water_status(notes),
        # صريحان لا مُستنتَجان: الريُّ مجهولٌ ≠ صفر، والاستنزافُ عندئذٍ حدٌّ أعلى لا قياس.
        "irrigation_known": irrigation_known(applied_water_status(notes)),
        "depletion_is_upper_bound": depletion_is_upper_bound(
            applied_water_status(notes), depletion_mm
        ),
        "decision": ("auto:" + (";".join(notes) if notes else "daily_balance")),
    }


def manual_entry_takes_precedence(existing_created_by: str | None) -> bool:
    """قيد اليوم الموجود يُحترَم إن لم يكن من العامل نفسه — الإنسان سيّد الدفتر."""
    return existing_created_by is not None and existing_created_by != AUTO_CREATED_BY
