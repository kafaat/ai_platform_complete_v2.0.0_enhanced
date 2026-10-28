"""core/season_comparison.py — محلّل مقارنة المواسم (نقيّ، حتميّ، المرحلة P2).

يُكمّل محرّك اشتقاق Kc (kc_extraction_engine): بينما يستخرج ذاك معاملات موسم واحد،
تقارن هذه الوحدة موسمين (الحاليّ مقابل السابق) لنفس المحصول/الحقل وتُظهِر **الاتّجاه**:
هل تحسّنت الغلّة؟ هل تحسّنت كفاءة استخدام الماء؟ هل استُهلِك ماء أكثر لنفس الغلّة؟

لكلّ مقياس تُحسَب: القيمتان، الفرق المطلق، نسبة التغيّر (None إن كان السابق None/صفر
لتجنّب القسمة على صفر)، والاتّجاه ("up"/"down"/"flat"). تُتجاهَل المقاييس الناقصة على
أيّ جانب بأمان (لا انهيار). الحُكم الإجماليّ (verdict_ar) يُشتقّ حتميّاً من الغلّة وكفاءة
استخدام الماء (غلّة أعلى = أفضل؛ كفاءة ماء أعلى = أفضل).

حدود قابليّة المقارنة (صدق علميّ):
  • محصولان مختلفان (طماطم 40 ط/هـ مقابل قمح 4 ط/هـ) ليسا «+900% تحسّن» ⇒ نتيجة
    ``comparable=False`` بلا مقاييس ولا حكم أداء. التطابق بعد تطبيع حالة الأحرف/المسافات
    فقط (بلا جدول مرادفات — «قمح» و«wheat» يُعامَلان مختلفَين: رفضٌ محافظ لا تخمين).
  • الغلّة بالطنّ/هكتار لكنّ ``water_used_m3`` حجم كلّيّ: مضاعفته قد تعني مضاعفة المساحة
    لا هدراً. لذا يُوصَف الماء الكلّيّ بلا حكم (better=None)، ولا يدخل الحكم إلّا
    ``water_m3_per_ha`` المُطبَّع حين تتوفّر ``area_ha`` على الجانبين.

نقيّ تماماً: لا I/O، لا عشوائيّة، stdlib + dataclasses فقط (بلا numpy).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

# المقاييس التي تُقارَن، مع اتّجاه «الأفضل» لكلٍّ (هل زيادته تحسّن أم تراجع).
# True ⇒ الأعلى أفضل، False ⇒ الأعلى أسوأ.
_HIGHER_IS_BETTER = {
    "kc_mid": None,  # محايد (وصفيّ، لا يُحكَم به)
    "yield_t_ha": True,  # غلّة أعلى أفضل
    # حجم كلّيّ (م³) يتبع المساحة المزروعة ⇒ وصفيّ لا يُحكَم به (انظر water_m3_per_ha).
    "water_used_m3": None,
    "ndvi_peak": True,  # خضرة ذروة أعلى أفضل
    "et0_total_mm": None,  # محايد (طقس، خارج التحكّم)
    "water_use_efficiency": True,  # كفاءة ماء أعلى أفضل
    # مُشتقّ: الماء للهكتار (م³/هـ) — يُحسَب فقط حين تتوفّر area_ha على الجانبين.
    "water_m3_per_ha": False,  # ماء أكثر للهكتار أسوأ (لنفس الغلّة)
}

# حقول ليست مقاييس تُقارَن مباشرةً (هويّة الموسم + المساحة المُستعمَلة للتطبيع).
_NON_METRIC_FIELDS = ("season_id", "crop_id", "area_ha")

# عتبة اعتبار التغيّر «ثابتاً» (flat) — تجنّب ضجيج الفاصلة العائمة.
_FLAT_EPS = 1e-9


@dataclass(frozen=True)
class SeasonMetrics:
    """مقاييس موسم واحد (كلّها اختياريّة — تُملأ بقدر المتاح من القياس/المحاكاة)."""

    season_id: str
    crop_id: str
    kc_mid: float | None = None
    yield_t_ha: float | None = None
    water_used_m3: float | None = None
    ndvi_peak: float | None = None
    et0_total_mm: float | None = None
    water_use_efficiency: float | None = None
    area_ha: float | None = None  # المساحة المزروعة (هـ) — لتطبيع الماء الكلّيّ إلى م³/هـ


def _crop_key(crop_id: str | None) -> str:
    """مفتاح مقارنة المحصول: تطبيع المسافات وحالة الأحرف فقط (لا مرادفات مُخمَّنة)."""
    return " ".join(str(crop_id or "").split()).casefold()


def _water_per_ha(m: SeasonMetrics) -> float | None:
    """الماء للهكتار (م³/هـ) إن توفّر الماء الكلّيّ ومساحة موجبة؛ وإلّا None (لا تلفيق)."""
    if m.water_used_m3 is None or m.area_ha is None or m.area_ha <= 0:
        return None
    return round(float(m.water_used_m3) / float(m.area_ha), 6)


def _direction(delta: float) -> str:
    """اتّجاه الفرق: up/down/flat (مع عتبة لتجنّب ضجيج العائمة)."""
    if delta > _FLAT_EPS:
        return "up"
    if delta < -_FLAT_EPS:
        return "down"
    return "flat"


def _percent_change(current: float, previous: float) -> float | None:
    """نسبة التغيّر المئويّة؛ None إن كان السابق صفراً (لا قسمة على صفر)."""
    if previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100.0, 2)


def _compare_metric(name: str, cur: float, prev: float) -> dict:
    """مقارنة مقياس واحد: القيمتان + الفرق المطلق + النسبة + الاتّجاه."""
    delta = round(cur - prev, 6)
    return {
        "current": cur,
        "previous": prev,
        "delta": delta,
        "percent_change": _percent_change(cur, prev),
        "direction": _direction(delta),
    }


def _verdict(metrics: dict) -> str:
    """يشتقّ حُكماً إجماليّاً حتميّاً من الغلّة وكفاءة استخدام الماء واستهلاك الماء.

    المنطق: غلّة أعلى = تحسّن؛ كفاءة ماء أعلى = تحسّن؛ ماء أكثر = تراجع. تُجمَع الإشارات
    وتُرجَّح كلمة الحكم. إن غابت كلّ المقاييس الحاكمة ⇒ حكم محايد (بيانات غير كافية).
    """
    signals: list[str] = []  # عبارات وصفيّة للأسباب
    score = 0  # موجب = تحسّن، سالب = تراجع

    y = metrics.get("yield_t_ha")
    if y is not None and y["direction"] != "flat":
        if y["direction"] == "up":
            score += 1
            signals.append("غلّة أعلى")
        else:
            score -= 1
            signals.append("غلّة أقلّ")

    wue = metrics.get("water_use_efficiency")
    if wue is not None and wue["direction"] != "flat":
        if wue["direction"] == "up":
            score += 1
            signals.append("كفاءة ماء أفضل")
        else:
            score -= 1
            signals.append("كفاءة ماء أسوأ")

    # ماء أكثر **للهكتار** إشارة تراجع فقط إن لم تتحسّن الغلّة (أكثر ماء لنفس/أقلّ غلّة).
    # الحجم الكلّيّ (water_used_m3) لا يُحكَم به: مضاعفته قد تعكس مضاعفة المساحة فقط.
    w = metrics.get("water_m3_per_ha")
    if w is not None and w["direction"] == "up" and (y is None or y["direction"] != "up"):
        score -= 1
        signals.append("استهلاك ماء أعلى للهكتار دون زيادة غلّة")

    if not signals:
        return "غير حاسم: لا تتوفّر مقاييس كافية للحكم (الغلّة/الكفاءة)."

    reasons = "، ".join(signals)
    if score > 0:
        return f"تحسّن: {reasons}."
    if score < 0:
        return f"تراجع: {reasons}."
    return f"مختلط: {reasons}."


def compare_seasons(current: SeasonMetrics, previous: SeasonMetrics) -> dict:
    """يقارن موسمين ويُرجِع قاموس مقارنة لكلّ مقياس + حُكماً إجماليّاً (نقيّ).

    لكلّ مقياس عدديّ متوفّر على **الجانبين**: القيمتان والفرق المطلق ونسبة التغيّر
    (None إن كان السابق None/صفر) والاتّجاه (up/down/flat). تُتجاهَل المقاييس الناقصة
    على أيّ جانب بأمان. الحكم (verdict_ar) يُشتقّ حتميّاً من الغلّة + كفاءة استخدام الماء.

    محصولان مختلفان ⇒ ``comparable=False`` (reason=crop_mismatch) بلا مقاييس ولا حكم أداء.
    """
    base = {
        "current_season_id": current.season_id,
        "previous_season_id": previous.season_id,
        "crop_id": current.crop_id,
        "previous_crop_id": previous.crop_id,
    }
    if _crop_key(current.crop_id) != _crop_key(previous.crop_id):
        return {
            **base,
            "comparable": False,
            "not_comparable_reason": "crop_mismatch",
            "metrics": {},
            "skipped_metrics": list(_HIGHER_IS_BETTER),
            "verdict_ar": (
                f"غير قابل للمقارنة: محصولان مختلفان ({current.crop_id} مقابل "
                f"{previous.crop_id}) — الغلّة والماء لا يُقارَنان عبر محاصيل مختلفة؛ "
                "قارن موسمين لنفس المحصول."
            ),
        }

    metrics: dict = {}
    skipped: list[str] = []

    # القيم الخام (كما وُرِدت) + المُشتقّ المُطبَّع بالمساحة (م³/هـ) حين يتوفّر.
    pairs: list[tuple[str, float | None, float | None]] = [
        (f.name, getattr(current, f.name), getattr(previous, f.name))
        for f in fields(SeasonMetrics)
        if f.name not in _NON_METRIC_FIELDS
    ]
    pairs.append(("water_m3_per_ha", _water_per_ha(current), _water_per_ha(previous)))

    for name, cur, prev in pairs:
        if cur is None or prev is None:
            skipped.append(name)
            continue
        entry = _compare_metric(name, float(cur), float(prev))
        higher = _HIGHER_IS_BETTER.get(name)
        if higher is None:
            entry["better"] = None  # مقياس محايد/وصفيّ
        elif entry["direction"] == "flat":
            entry["better"] = None
        else:
            improved = (entry["direction"] == "up") == higher
            entry["better"] = improved
        metrics[name] = entry

    return {
        **base,
        "comparable": True,
        "not_comparable_reason": None,
        "metrics": metrics,
        "skipped_metrics": skipped,
        "verdict_ar": _verdict(metrics),
    }
