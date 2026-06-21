"""
api/recommendations_hub.py — مُجمِّع التوصيات الموحَّد لكلّ حقل (Sprint — recommendations).

# DECISION-PATH: legacy — مُجمِّع توصيات heuristic للعرض (ريّ/تسميد/أمراض/غلّة).
# استشاريّ فقط: لا يُوزَّع للتنفيذ ولا يمرّ ببوّابة الحَوكمة. التنفيذ يمرّ بالمسار
# القانونيّ (canonical) core.field_intelligence_coordinator.run_field_intelligence.

الهدف: عمود توصيات موحَّد لكلّ حقل يجمع في مكان واحد:
  • الريّ (irrigation) — من api.weather_advice.irrigation_advice (FAO-56).
  • التسميد (fertilizer) — إرشاد N/P/K مبسّط بحسب محصول الموسم النشط ومرحلته.
  • الأمراض (disease) — من api.weather_advice.disease_risk (agro-met).
  • الحصاد/الإنتاج (yield) — نافذة حصاد تقديريّة من تاريخ البذار + طول دورة المحصول.

المبدأ (نفس فلسفة weather_advice):
  • المنطق هنا **نقيّ** بالكامل (لا شبكة، لا قاعدة) — يُختبَر offline.
  • النواة (main.py) تجمع السياق (الطقس من Open-Meteo، الموسم من القاعدة) ثمّ
    تمرّره هنا. عند غياب جزء من السياق (طقس متعذّر مثلاً) نتخطّى التوصيات التي
    تحتاجه ولا نلفّق — صدق: لا رقم وهميّ.
  • كلّ heuristic موسوم بمصدره في الحقل source. معاملات تقديريّة تحتاج معايرة محليّة.

⚠ هذه heuristics زراعيّة مبسّطة (ليست نموذجاً مُعايَراً). راجِعها مع مهندس زراعي
قبل الاعتماد عليها في قرارات حقيقيّة.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from api.crop_cycle import cycle_days_to_maturity
from api.weather_advice import disease_risk, irrigation_advice

# ─── نموذج التوصية الموحَّد ────────────────────────────────────────

# ترتيب الأولويّة للفرز (الأعلى أولاً).
PRIORITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

# الفئات المعروفة (للواجهة: أيقونة لكلّ فئة).
CATEGORIES = ("irrigation", "fertilizer", "disease", "yield")


@dataclass
class Recommendation:
    """توصية واحدة موحَّدة عبر الفئات. كلّها نصوص عربيّة جاهزة للعرض."""

    category: str  # irrigation|fertilizer|disease|yield
    priority: str  # high|medium|low
    title_ar: str
    detail_ar: str
    source: str  # مرجع/أصل التوصية (heuristic موسوم — لا تلفيق)
    safety: bool = False  # تنبيه سلامة من الحالة الموحّدة — يتصدّر عند تعادل الأولويّة

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "priority": self.priority,
            "title_ar": self.title_ar,
            "detail_ar": self.detail_ar,
            "source": self.source,
            "safety": self.safety,
        }


@dataclass
class RecommendationContext:
    """السياق الذي تجمعه النواة وتمرّره للمُجمِّع (كلّه اختياريّ — تدهور رشيق).

    أيّ جزء غائب (None) يعني أنّ مصدره غير متاح؛ نتخطّى توصيته بدل التلفيق.
    """

    field_id: str
    crop: str | None = None
    stage: str = "mid"
    today: date | None = None  # لحساب نافذة الحصاد (افتراضيّاً اليوم الفعليّ)
    sowing_date: date | None = None
    # سياق الطقس (من Open-Meteo) — None ⇒ غير متاح، نتخطّى توصيات الطقس.
    et0_mm: float | None = None
    rain_recent_mm: float = 0.0
    forecast_rain_mm: float = 0.0
    soil_moisture_pct: float | None = None
    temp_c: float | None = None
    humidity_pct: float | None = None
    rain_mm_3d: float = 0.0
    # Stage F (تغذية آمنة): مرجعيّة من الحالة القانونيّة الموحّدة (النواة الزراعيّة)
    # — تُستخدَم للتصعيد/التنبيه فقط، لا تُغيّر أرقام التوصيات الأخرى.
    salinity_class: str | None = None  # critical|moderate|low (compose_field_state)
    crop_vigor: float | None = None  # 0..1 (مرجعيّة فقط)


# ─── التسميد: إرشاد N/P/K مبسّط بحسب المرحلة ───────────────────────
# المرجع: مبادئ تغذية النبات العامّة (FAO Fertilizer & Plant Nutrition Bulletin) —
# الاحتياج النيتروجينيّ يبلغ ذروته في النموّ الخضريّ (development/mid)، والفوسفور
# مهمّ مبكّراً لتأسيس الجذور (initial)، والبوتاسيوم يدعم الامتلاء/الجودة متأخّراً
# (late). هذه توقيتات إرشاديّة عامّة لا كمّيّات — الكمّيّة تحتاج تحليل تربة (انظر
# nutrient_4r مع بيانات مختبر). موسومة كتقدير يحتاج معايرة.
_FERT_STAGE_GUIDANCE: dict[str, tuple[str, str, str]] = {
    # stage -> (priority, title_ar, detail_ar)
    "initial": (
        "medium",
        "تسميد التأسيس: ركّز على الفوسفور (P)",
        "في مرحلة التأسيس المبكّر يدعم الفوسفور نموّ الجذور. "
        "طبّق سماداً فوسفاتيّاً عند/قرب البذار، ونيتروجيناً ابتدائيّاً خفيفاً.",
    ),
    "development": (
        "high",
        "تسميد النموّ الخضريّ: ركّز على النيتروجين (N)",
        "النموّ الخضريّ النشط يستهلك أكبر قدر من النيتروجين. "
        "طبّق دفعة نيتروجين مقسّمة لدعم تكوين المجموع الخضريّ.",
    ),
    "mid": (
        "high",
        "تسميد منتصف الموسم: نيتروجين + بوتاسيوم متوازن",
        "في منتصف الموسم استمرّ بالنيتروجين مع بدء البوتاسيوم (K) لدعم "
        "التزهير/العقد. وازِن الدفعات وتجنّب الإفراط النيتروجينيّ المتأخّر.",
    ),
    "late": (
        "low",
        "تسميد متأخّر: ركّز على البوتاسيوم (K)، خفّف النيتروجين",
        "قرب النضج يدعم البوتاسيوم امتلاء الحبّة/الثمرة والجودة. "
        "قلّل النيتروجين لتفادي تأخير النضج وزيادة الإصابة المرضيّة.",
    ),
}

_FERT_SOURCE = (
    "إرشاد تسميد مبسّط بحسب المرحلة — مبادئ تغذية النبات (FAO). "
    "توقيتات عامّة لا كمّيّات؛ الكمّيّة تحتاج تحليل تربة. تقدير يحتاج معايرة محليّة."
)


# ─── الحصاد: نافذة حصاد تقديريّة من طول دورة المحصول ───────────────
# طول دورة المحصول (أيّام من البذار للنضج) صار يُحلّ عبر api.crop_cycle
# (resolver طبقيّ: مستأجِر ← منطقة افتراضيّة ← بطاقة محصول محايدة ← None)، فلم
# يَعُد هنا قاموس مُصلَّب. ملاحظة: yield_heuristics.CROP_TYPICAL_GROWING_DAYS
# مقياس مختلف (أيّام النموّ الخضريّ ≈ مجموع المراحل الثلاث الأولى) سيُشتقّ من
# البطاقة في تتبُّع لاحق — موثَّق هنا ولا يُمسّ في هذه المرحلة.

# نافذة الحصاد: ±هامش حول يوم النضج التقديريّ.
_HARVEST_WINDOW_MARGIN_DAYS = 10


def _normalize_crop(crop: str | None) -> str | None:
    if not crop:
        return None
    return crop.strip().lower() or None


# ─── بنّاء كلّ فئة (دوالّ نقيّة صغيرة قابلة للاختبار) ────────────────


def _irrigation_rec(ctx: RecommendationContext) -> Recommendation | None:
    """توصية ريّ من irrigation_advice — تتطلّب ET₀ (الطقس). None إن غاب."""
    if ctx.et0_mm is None:
        return None
    advice = irrigation_advice(
        et0_mm=ctx.et0_mm,
        crop=ctx.crop,
        stage=ctx.stage,
        rain_recent_mm=ctx.rain_recent_mm,
        forecast_rain_mm=ctx.forecast_rain_mm,
        soil_moisture_pct=ctx.soil_moisture_pct,
    )
    # تعيين urgency (none/low/moderate/high) → priority (low/medium/high).
    urgency = advice["urgency"]
    priority = {"none": "low", "low": "low", "moderate": "medium", "high": "high"}.get(
        urgency, "medium"
    )
    mm = advice["recommended_mm"]
    if mm > 0:
        title = f"ريّ مُوصى به: {mm:.1f} مم — {advice['timing_ar']}"
    else:
        title = f"لا حاجة للريّ الآن — {advice['timing_ar']}"
    return Recommendation(
        category="irrigation",
        priority=priority,
        title_ar=title,
        detail_ar=advice["rationale_ar"],
        source="api.weather_advice.irrigation_advice (FAO-56، نقيّ ومُختبَر)",
    )


def _fertilizer_rec(ctx: RecommendationContext) -> Recommendation | None:
    """إرشاد تسميد مبسّط بحسب المرحلة. يتطلّب مرحلة معروفة (افتراضيّاً mid)."""
    stage = ctx.stage if ctx.stage in _FERT_STAGE_GUIDANCE else "mid"
    priority, title, detail = _FERT_STAGE_GUIDANCE[stage]
    crop = _normalize_crop(ctx.crop)
    if crop:
        detail = f"المحصول: {crop}. " + detail
    return Recommendation(
        category="fertilizer",
        priority=priority,
        title_ar=title,
        detail_ar=detail,
        source=_FERT_SOURCE,
    )


def _disease_rec(ctx: RecommendationContext) -> Recommendation | None:
    """توصية أمراض من disease_risk — تتطلّب حرارة + رطوبة (الطقس). None إن غاب."""
    if ctx.temp_c is None or ctx.humidity_pct is None:
        return None
    risk = disease_risk(
        temp_c=ctx.temp_c,
        humidity_pct=ctx.humidity_pct,
        rain_mm_3d=ctx.rain_mm_3d,
        crop=ctx.crop,
    )
    level = risk["risk_level"]
    priority = {"low": "low", "moderate": "medium", "high": "high"}.get(level, "medium")
    level_ar = {"low": "منخفض", "moderate": "متوسّط", "high": "مرتفع"}.get(level, level)
    diseases = risk["diseases_ar"]
    if diseases:
        title = f"خطر أمراض {level_ar}: " + "، ".join(diseases[:2])
    else:
        title = f"خطر الأمراض الفطريّة: {level_ar}"
    return Recommendation(
        category="disease",
        priority=priority,
        title_ar=title,
        detail_ar=risk["advice_ar"],
        source="api.weather_advice.disease_risk (agro-met، نقيّ ومُختبَر)",
    )


def _yield_rec(ctx: RecommendationContext) -> Recommendation | None:
    """نافذة حصاد تقديريّة من تاريخ البذار + طول دورة المحصول. None إن غاب أحدهما."""
    crop = _normalize_crop(ctx.crop)
    if ctx.sowing_date is None or crop is None:
        return None
    cycle = cycle_days_to_maturity(crop)
    if cycle is None:
        return None
    today = ctx.today or date.today()
    maturity = ctx.sowing_date.fromordinal(ctx.sowing_date.toordinal() + cycle)
    days_to_maturity = (maturity - today).days
    win_start = maturity.fromordinal(maturity.toordinal() - _HARVEST_WINDOW_MARGIN_DAYS)
    win_end = maturity.fromordinal(maturity.toordinal() + _HARVEST_WINDOW_MARGIN_DAYS)
    window_ar = f"النافذة التقديريّة للحصاد: {win_start.isoformat()} إلى {win_end.isoformat()}"

    if days_to_maturity < -_HARVEST_WINDOW_MARGIN_DAYS:
        priority = "high"
        title = f"تأخّر الحصاد: مرّ النضج التقديريّ ({-days_to_maturity} يوماً)"
        detail = (
            f"بحسب البذار ({ctx.sowing_date.isoformat()}) ودورة {crop} (~{cycle} يوماً)، "
            f"تجاوز المحصول نافذة النضج. افحص الحقل وحُصُّ لتفادي تدهور الجودة. {window_ar}."
        )
    elif days_to_maturity <= _HARVEST_WINDOW_MARGIN_DAYS:
        priority = "high"
        title = f"اقتراب الحصاد: ~{max(0, days_to_maturity)} يوماً للنضج التقديريّ"
        detail = (
            f"بحسب البذار ({ctx.sowing_date.isoformat()}) ودورة {crop} (~{cycle} يوماً)، "
            f"الحقل يقترب من النضج. جهّز الحصاد وراقب مؤشّرات النضج. {window_ar}."
        )
    elif days_to_maturity <= 30:
        priority = "medium"
        title = f"الحصاد بعد ~{days_to_maturity} يوماً (تقديريّ)"
        detail = (
            f"بحسب البذار ({ctx.sowing_date.isoformat()}) ودورة {crop} (~{cycle} يوماً)، "
            f"اقترب موعد الحصاد. خطّط للعمالة والمعدّات والتسويق. {window_ar}."
        )
    else:
        priority = "low"
        title = f"الحصاد بعد ~{days_to_maturity} يوماً (تقديريّ)"
        detail = (
            f"بحسب البذار ({ctx.sowing_date.isoformat()}) ودورة {crop} (~{cycle} يوماً)، "
            f"لا يزال أمام المحصول وقت قبل النضج. تابِع الإدارة المعتادة. {window_ar}."
        )
    return Recommendation(
        category="yield",
        priority=priority,
        title_ar=title,
        detail_ar=detail,
        source=(
            "تقدير نافذة الحصاد من تاريخ البذار + طول دورة المحصول — "
            "أطوال تقديريّة تحتاج معايرة بحسب الصنف/الموسم/الارتفاع."
        ),
    )


def _salinity_caution_rec(ctx: RecommendationContext) -> Recommendation | None:
    """Stage F (تغذية آمنة): تصعيد مرجعيّ من الحالة القانونيّة الموحّدة.

    حين تحكم النواة الزراعيّة بملوحة تربة حرجة (salinity_class=critical عبر تحكيم
    Salinity>Vigor)، نُضيف تنبيهاً عالي الأولويّة يربط التوصيات بحالة الحقل الموحّدة:
    ريّ بماء هامشيّ قد يفاقم الملوحة؛ يُراجَع كسر التملّح (leaching fraction)/الصرف
    واختيار أصناف متحمّلة — إرشاد عامّ (FAO 29) لا كمّيّة مخترعة. لا يغيّر أرقام
    التوصيات الأخرى — يُضيف تصعيد سلامة فقط (يحترم قيد عدم تغيير الأرقام).
    """
    if ctx.salinity_class != "critical":
        return None
    return Recommendation(
        category="irrigation",
        priority="high",
        title_ar="تنبيه ملوحة تربة حرجة — راجِع الريّ والصرف",
        detail_ar=(
            "الحالة الموحّدة للحقل تشير إلى ملوحة تربة حرجة (تحكُم رغم خُضرة المؤشّر "
            "الطيفيّ). الريّ بماء هامشيّ قد يزيد تراكم الأملاح — راجِع كسر التملّح "
            "(leaching) وكفاءة الصرف، وفضّل أصنافاً متحمّلة للملوحة. استشِر المهندس "
            "الزراعيّ قبل زيادة الريّ."
        ),
        source="canonical_field_state:arbitration(salinity>vigor) — إرشاد FAO 29 عامّ",
        safety=True,
    )


# ─── سجلّ المحرّكات (Recommendation Engine Registry) ───────────────
# نمط السجلّ: بدل قائمة بنّائين مُصلَّبة (hardcoded)، نَصِف كلّ بنّاء بـ«محرّك»
# يحمل metadata قابلة للاستبطان: مُعرّف ثابت (id)، اسم عربيّ، فئة، المدخلات التي
# يحتاجها فعليّاً (required_inputs)، وعلَم تفعيل افتراضيّ (default_enabled). الفائدة:
#   • «سجّل محرّكاً ⇐ يشارك تلقائيّاً» دون تعديل حلقة البناء.
#   • تفعيل/تعطيل لكلّ محرّك بالمُعرّف (enabled_ids) — أساس سياسة لكلّ مستأجر لاحقاً.
#   • استبطان نقيّ (list_engines) لكتالوج/واجهة دون قاعدة.
# ملاحظة توافق خلفيّ: required_inputs هي metadata فقط (للاستبطان والسياسة المستقبليّة)
# ولا تُستخدَم للبوّابة (gating) — البنّاء نفسه يبوّب ذاتيّاً ويُرجع None عند غياب
# مدخلاته، فيبقى السلوك مطابقاً تماماً حين تُفعَّل كلّ المحرّكات (enabled_ids=None).
# الخطوة التالية المُخطَّطة (ليست في هذا الـPR — نُبقيه منطقاً نقيّاً): قراءة سياسة
# التفعيل/التعطيل لكلّ مستأجر من جدول settings وتمريرها كـ enabled_ids — لا قاعدة هنا.


@dataclass(frozen=True)
class RecommendationEngine:
    """وصف محرّك توصية واحد ضمن السجلّ (metadata قابلة للاستبطان).

    required_inputs: أسماء حقول RecommendationContext التي يحتاجها المحرّك فعليّاً
    (مُشتَقّة بصدق من بوّابة كلّ بنّاء). metadata فقط — لا تُستخدَم للبوّابة كي يبقى
    السلوك مطابقاً؛ البنّاء يبوّب ذاتيّاً. عند عدم اليقين استخدِم () فيعمل دائماً.
    """

    id: str
    name_ar: str
    category: str
    builder: Callable[[RecommendationContext], Recommendation | None]
    required_inputs: tuple[str, ...] = ()
    default_enabled: bool = True


# السجلّ — يحفظ نفس ترتيب تشغيل البنّائين السابق (قبل الفرز) كي لا يتغيّر الإخراج.
_REGISTRY: list[RecommendationEngine] = [
    RecommendationEngine(
        id="irrigation",
        name_ar="الريّ",
        category="irrigation",
        builder=_irrigation_rec,
        # يبوّب على ET₀ (الطقس) فقط؛ بقيّة المدخلات لها قيم افتراضيّة/اختياريّة.
        required_inputs=("et0_mm",),
    ),
    RecommendationEngine(
        id="fertilizer",
        name_ar="التسميد",
        category="fertilizer",
        builder=_fertilizer_rec,
        # لا بوّابة — يعمل دائماً (المرحلة افتراضيّاً mid). لذا () بصدق.
        required_inputs=(),
    ),
    RecommendationEngine(
        id="disease",
        name_ar="الأمراض",
        category="disease",
        builder=_disease_rec,
        # يبوّب على الحرارة والرطوبة (الطقس).
        required_inputs=("temp_c", "humidity_pct"),
    ),
    RecommendationEngine(
        id="yield",
        name_ar="الحصاد/الإنتاج",
        category="yield",
        builder=_yield_rec,
        # يبوّب على تاريخ البذار والمحصول (ثمّ توفّر دورة المحصول).
        required_inputs=("sowing_date", "crop"),
    ),
    RecommendationEngine(
        id="salinity_caution",
        name_ar="تنبيه الملوحة",
        category="irrigation",
        builder=_salinity_caution_rec,
        # يبوّب على صنف الملوحة (critical) من الحالة الموحّدة.
        required_inputs=("salinity_class",),
    ),
]

# اسم متوارَث مُشتَقّ من السجلّ (لمن قد يستورده) — نفس ترتيب البنّائين السابق.
_BUILDERS = [e.builder for e in _REGISTRY]


def list_engines() -> list[dict]:
    """استبطان نقيّ لكلّ محرّكات السجلّ (metadata فقط — لا قاعدة، لا أثر جانبيّ).

    يُرجع لكلّ محرّك: id, name_ar, category, required_inputs, default_enabled —
    لكتالوج/واجهة مستقبليّة أو سياسة تفعيل لكلّ مستأجر.
    """
    return [
        {
            "id": e.id,
            "name_ar": e.name_ar,
            "category": e.category,
            "required_inputs": list(e.required_inputs),
            "default_enabled": e.default_enabled,
        }
        for e in _REGISTRY
    ]


def build_recommendations(
    ctx: RecommendationContext, *, enabled_ids: set[str] | None = None
) -> list[Recommendation]:
    """يبني قائمة التوصيات الموحَّدة من السياق، مفروزة بالأولويّة (الأعلى أولاً).

    دالّة نقيّة (لا شبكة، لا قاعدة) — تُختبَر offline. تمرّ على السجلّ بنفس ترتيب
    البنّائين السابق، وتشغّل كلّ محرّك مُفعَّل فيُرجع توصيته أو None إن غاب مصدرها
    (تدهور رشيق بلا تلفيق). الفرز ثابت: الأولويّة ثمّ السلامة ثمّ ترتيب الفئة.

    enabled_ids: سياسة التفعيل لكلّ مُعرّف.
      • None  ⇒ تُفعَّل المحرّكات بحسب default_enabled (السلوك الافتراضيّ الأصليّ).
      • set() ⇒ لا محرّك يعمل (قائمة فارغة).
      • مجموعة مُعرّفات ⇒ تعمل المحرّكات الموجودة فيها فقط.
    لا نبوّب على required_inputs (metadata فقط) كي يبقى السلوك مطابقاً تماماً حين
    enabled_ids=None — البنّاء يبوّب ذاتيّاً.
    """
    recs: list[Recommendation] = []
    for engine in _REGISTRY:
        if enabled_ids is not None:
            if engine.id not in enabled_ids:
                continue
        elif not engine.default_enabled:
            continue
        rec = engine.builder(ctx)
        if rec is not None:
            recs.append(rec)
    cat_order = {c: i for i, c in enumerate(CATEGORIES)}
    # الفرز: الأولويّة، ثمّ تنبيهات السلامة (من الحالة الموحّدة) أوّلاً عند التعادل،
    # ثمّ ترتيب الفئة — كي لا يُدفَن تنبيه السلامة تحت توصية ريّ بنفس الأولويّة.
    recs.sort(
        key=lambda r: (
            PRIORITY_ORDER.get(r.priority, 99),
            0 if r.safety else 1,
            cat_order.get(r.category, 99),
        )
    )
    return recs
