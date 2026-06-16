"""core/policy_learning.py — حلقة تعلّم السياسة (Policy Learning) — منطق نقيّ.

يُغلق الحلقة بين **نتائج** التنبيهات/التوصيات المُسجَّلة واقتراح ضبط عتبات
التنبيه لكلّ مستأجِر. هذه الوحدة **نقيّة تماماً** (لا شبكة، لا قاعدة): تأخذ قائمة
نتائج كمدخل وتُرجع اقتراحات قابلة للتفسير — تُختبَر offline بالكامل.

────────────────────────────────────────────────────────────────────────
شكل بيانات النتيجة الحقيقيّ (الذي وجدناه) وكيف نُطابقه
────────────────────────────────────────────────────────────────────────
لا يوجد جدول مخصّص يحمل حقلاً صريحاً اسمه ``useful`` لكلّ تنبيه. الإشارة
الحقيقيّة المتوفّرة هي **حالة التنبيه** في جدول ``alerts``:

    api/alert_models.py: _ALERT_STATUSES = {"active", "acknowledged", "resolved"}

ودورة الحياة (api/routers/alerts.py): تنبيه يُنشأ ``active`` ⇒ يُقِرّه المستأجِر
``acknowledged`` ⇒ يُحلّ ``resolved``. لذا **التطابق الصادق** الذي يبنيه مُغذّي
الكتابة (نقطة النهاية) قبل استدعاء هذه الوحدة:

    status ∈ {"acknowledged", "resolved"}  ⇒  useful = True   (تفاعَل المستأجِر)
    status == "active" (بقي دون تفاعل)      ⇒  useful = False  (ضجيج محتمل)

أي أنّ تنبيهاً تفاعَل معه المستأجِر = إشارة نافعة، وتنبيهاً تُرك نشطاً دون إقرار
= إشارة سلبيّة محتملة (false-positive تشغيليّ). هذه الوحدة تستقبل الشكل المُسطَّح
``{alert_type, useful: bool}`` بعد هذا التطابق — تبقى نقيّةً لا تعرف مصدر الإشارة.

ملاحظة صدق: ``acknowledged/resolved`` تقريب لـ«نافع» وليس حُكماً صريحاً من
المستأجِر بأنّ التنبيه كان صحيحاً؛ نُسمّيه «تفاعُل» لا «صحّة». الاقتراحات أدناه
**اقتراحات** لإنسان/مستأجِر يُطبّقها يدويّاً عبر نقطة الإعدادات — لا تُطبَّق آليّاً.

────────────────────────────────────────────────────────────────────────
عقد ``derive_threshold_adjustments`` والقطوع (cutoffs)
────────────────────────────────────────────────────────────────────────
لكلّ ``alert_type`` نعدّ النافع مقابل غير النافع، ونحسب ``useful_rate``. ثمّ:
  • معدّل false-positive مرتفع (نسبة «غير نافع» ≥ FALSE_POSITIVE_RATE) فوق عيّنة
    كافية (n ≥ MIN_SAMPLES) ⇒ "loosen": اجعل القاعدة **أقلّ حسّاسيّة** (مثل خفض
    عتبة الرطوبة المنخفضة، أو رفع عتبة هبوط NDVI) لتقليل الضجيج.
  • مفيد دائماً تقريباً ونادر (useful_rate ≥ HIGH_USEFUL_RATE و n ≤ RARE_MAX) ⇒
    "tighten": اقتراح حسّاسيّة أعلى (قد نلتقط حالات مبكّرة أكثر).
  • غير ذلك ⇒ "keep".
  • تحت MIN_SAMPLES ⇒ "keep" دائماً + «بيانات غير كافية» (صدق: لا اقتراح بلا أساس).

خطوة الضبط نسبيّة ومحافِظة (ADJUST_FRACTION = 15٪ من القيمة الحاليّة)، باتّجاه
يقلّل/يزيد الحسّاسيّة حسب دلالة كلّ عتبة (موثَّقة في _DIRECTION أدناه).

────────────────────────────────────────────────────────────────────────
خريطة alert_type → مفتاح/مفاتيح عتبة AlertThresholds
────────────────────────────────────────────────────────────────────────
المفاتيح هي **أسماء حقول** ``api/alert_rules.AlertThresholds`` حرفيّاً (UPPERCASE)
لأنّ ``thresholds_from_policy`` يطابق على ``__dataclass_fields__`` — فالتجاوز
المُقترَح يصلح مباشرةً كقيمة ``settings`` (scope='platform', key='alert_thresholds').

    low_moisture       → LOW_MOISTURE_SOIL_PCT, LOW_MOISTURE_IRRIGATION_MM
    heavy_rain         → HEAVY_RAIN_MM
    heat_stress        → HEAT_STRESS_TMAX_C
    frost_risk         → FROST_RISK_TMIN_C
    vegetation_stress  → NDVI_DROP_WARN
    disease_risk       → (لا عتبة رقميّة قابلة للضبط في AlertThresholds) ⇒ لا تجاوز

⚠ هذه heuristics agro-met مبسّطة (راجع alert_rules) — العتبات تبقى
human-in-the-loop: نُصدِر اقتراحاً موثَّقاً ومبرّراً فقط، والمستأجِر يقرّر.
"""

from __future__ import annotations

# ─── القطوع الموثَّقة (constants) ─────────────────────────────────────
# أقلّ عدد نتائج قبل أن نسمح بأيّ اقتراح غير "keep" (تجنّب القفز على ضجيج).
MIN_SAMPLES = 5
# نسبة «غير نافع» (false-positive تشغيليّ) عندها نقترح تقليل الحسّاسيّة.
FALSE_POSITIVE_RATE = 0.60
# نسبة «نافع» مرتفعة جدّاً ⇒ مرشَّح لزيادة الحسّاسيّة (إن كان نادراً أيضاً).
HIGH_USEFUL_RATE = 0.90
# سقف العيّنة لاعتبار النوع «نادراً» (لا نُشدّد حسّاسيّة نوع شائع أصلاً).
RARE_MAX = 20
# نسبة الضبط المحافِظة على القيمة الحاليّة (15٪) عند اقتراح تجاوز.
ADJUST_FRACTION = 0.15

# الافتراضات الحاليّة للعتبات (مُطابِقة لثوابت api/alert_rules.AlertThresholds).
# نُعيد ذكرها هنا لإبقاء الوحدة **نقيّة** بلا استيراد من طبقة الـAPI (core لا
# يعتمد على api). أيّ انحراف عن تلك القيم يُكشَف باختبار التطابق.
_DEFAULT_THRESHOLDS: dict[str, float] = {
    "LOW_MOISTURE_SOIL_PCT": 30.0,
    "LOW_MOISTURE_IRRIGATION_MM": 8.0,
    "HEAVY_RAIN_MM": 20.0,
    "HEAT_STRESS_TMAX_C": 35.0,
    "FROST_RISK_TMIN_C": 2.0,
    "NDVI_DROP_WARN": 0.10,
}

# خريطة alert_type → (مفاتيح العتبة المتأثّرة). راجع docstring أعلاه للمبرّر.
_TYPE_TO_KEYS: dict[str, tuple[str, ...]] = {
    "low_moisture": ("LOW_MOISTURE_SOIL_PCT", "LOW_MOISTURE_IRRIGATION_MM"),
    "heavy_rain": ("HEAVY_RAIN_MM",),
    "heat_stress": ("HEAT_STRESS_TMAX_C",),
    "frost_risk": ("FROST_RISK_TMIN_C",),
    "vegetation_stress": ("NDVI_DROP_WARN",),
    "disease_risk": (),  # لا عتبة رقميّة قابلة للضبط في AlertThresholds.
}

# اتّجاه «تقليل الحسّاسيّة» (loosen) لكلّ مفتاح: +1 ⇒ نرفع القيمة لتقليل الإطلاق،
# -1 ⇒ نخفض القيمة لتقليل الإطلاق. (القاعدة تُطلِق عند تجاوز/قصور القيمة الحاليّة.)
#   • LOW_MOISTURE_SOIL_PCT: يُطلِق حين الرطوبة < العتبة ⇒ خفض العتبة (-1) يُقلّل.
#   • LOW_MOISTURE_IRRIGATION_MM: يُطلِق حين الحاجة ≥ العتبة ⇒ رفع العتبة (+1) يُقلّل.
#   • HEAVY_RAIN_MM: يُطلِق حين المطر ≥ العتبة ⇒ رفع (+1) يُقلّل.
#   • HEAT_STRESS_TMAX_C: يُطلِق حين الحرارة ≥ العتبة ⇒ رفع (+1) يُقلّل.
#   • FROST_RISK_TMIN_C: يُطلِق حين الحرارة ≤ العتبة ⇒ خفض (-1) يُقلّل.
#   • NDVI_DROP_WARN: يُطلِق حين الهبوط ≥ العتبة ⇒ رفع (+1) يُقلّل.
_LOOSEN_DIRECTION: dict[str, int] = {
    "LOW_MOISTURE_SOIL_PCT": -1,
    "LOW_MOISTURE_IRRIGATION_MM": +1,
    "HEAVY_RAIN_MM": +1,
    "HEAT_STRESS_TMAX_C": +1,
    "FROST_RISK_TMIN_C": -1,
    "NDVI_DROP_WARN": +1,
}


def _round_key(key: str, value: float) -> float:
    """تقريب محافِظ يحفظ دلالة العتبة: NDVI بمنزلتين، الباقي بمنزلة واحدة."""
    return round(value, 2) if key.startswith("NDVI") else round(value, 1)


def _suggested_overrides(alert_type: str, *, loosen: bool) -> dict[str, float]:
    """يبني تجاوزات العتبة المُقترَحة لنوع تنبيه باتّجاه تقليل/زيادة الحسّاسيّة.

    منطق نقيّ. ``loosen=True`` ⇒ أقلّ حسّاسيّة (يقلّل الإطلاق)؛ False ⇒ أكثر
    حسّاسيّة. النوع غير المعروف أو بلا عتبة (disease_risk) ⇒ قاموس فارغ.
    """
    out: dict[str, float] = {}
    for key in _TYPE_TO_KEYS.get(alert_type, ()):  # noqa: B007 — نتحقّق من المفتاح أدناه
        base = _DEFAULT_THRESHOLDS.get(key)
        direction = _LOOSEN_DIRECTION.get(key)
        if base is None or direction is None:
            continue
        sign = direction if loosen else -direction
        new_val = base * (1.0 + sign * ADJUST_FRACTION)
        # NDVI لا يتجاوز 1.0؛ والعتبات النسبيّة تبقى موجبة.
        if key.startswith("NDVI"):
            new_val = min(new_val, 1.0)
        new_val = max(new_val, 0.0)
        out[key] = _round_key(key, new_val)
    return out


def _classify(n: int, useful: int) -> tuple[str, bool, str]:
    """يصنّف نوع تنبيه ⇒ (suggestion, loosen, rationale_ar) من عدّاداته.

    منطق نقيّ. تحت MIN_SAMPLES ⇒ "keep" + «بيانات غير كافية» (صدق).
    """
    not_useful = n - useful
    useful_rate = (useful / n) if n else 0.0
    if n < MIN_SAMPLES:
        return (
            "keep",
            False,
            f"بيانات غير كافية ({n} نتيجة < {MIN_SAMPLES}) — لا اقتراح بلا أساس.",
        )
    fp_rate = not_useful / n
    if fp_rate >= FALSE_POSITIVE_RATE:
        return (
            "loosen",
            True,
            (
                f"معدّل عدم التفاعل مرتفع ({fp_rate:.0%} ≥ {FALSE_POSITIVE_RATE:.0%} "
                f"على {n} نتيجة) ⇒ ضجيج محتمل: نقترح تقليل حسّاسيّة القاعدة."
            ),
        )
    if useful_rate >= HIGH_USEFUL_RATE and n <= RARE_MAX:
        return (
            "tighten",
            False,
            (
                f"نافع دائماً تقريباً ({useful_rate:.0%}) ونادر ({n} ≤ {RARE_MAX}) ⇒ "
                "نقترح زيادة الحسّاسيّة لالتقاط حالات مبكّرة أكثر (اختياريّ)."
            ),
        )
    return (
        "keep",
        False,
        (f"معدّل التفاعل ({useful_rate:.0%}) ضمن النطاق المقبول على {n} نتيجة ⇒ أبقِ العتبة كما هي."),
    )


def derive_threshold_adjustments(outcomes: list[dict]) -> dict:
    """يشتقّ اقتراحات ضبط عتبات التنبيه من نتائج مُسجَّلة — منطق نقيّ.

    المدخل: قائمة قواميس نتائج، كلّ منها يحمل على الأقلّ ``alert_type`` (str)
    و``useful`` (bool). راجع docstring الوحدة لتطابق ``status`` الحقيقيّ ⇒ ``useful``.
    النتائج المُشوّهة (بلا ``alert_type`` نصّيّ) تُتجاهَل بهدوء (تدهور رشيق، لا رفع).

    المخرج (راجع العقد في docstring الوحدة):
        {
          "min_samples": int,
          "false_positive_rate": float,
          "per_type": {
             alert_type: {
                "n": int, "useful": int, "not_useful": int, "useful_rate": float,
                "suggestion": "loosen"|"tighten"|"keep",
                "suggested_overrides": {KEY: value, ...},
                "threshold_keys": [KEY, ...],
                "rationale_ar": str,
             }, ...
          },
          "note_ar": str,
        }

    ⚠ الاقتراحات human-in-the-loop: لا تُطبَّق آليّاً أبداً — يُطبّقها المستأجِر
    يدويّاً عبر نقطة الإعدادات (alert_thresholds). الوحدة لا تكتب شيئاً.
    """
    counts: dict[str, list[int]] = {}  # alert_type ⇒ [n, useful]
    for o in outcomes or []:
        if not isinstance(o, dict):
            continue
        at = o.get("alert_type")
        if not isinstance(at, str) or not at:
            continue
        entry = counts.setdefault(at, [0, 0])
        entry[0] += 1
        if bool(o.get("useful")):
            entry[1] += 1

    per_type: dict[str, dict] = {}
    for at in sorted(counts):
        n, useful = counts[at]
        not_useful = n - useful
        useful_rate = useful / n if n else 0.0
        suggestion, loosen, rationale = _classify(n, useful)
        overrides = (
            _suggested_overrides(at, loosen=loosen) if suggestion in ("loosen", "tighten") else {}
        )
        per_type[at] = {
            "n": n,
            "useful": useful,
            "not_useful": not_useful,
            "useful_rate": round(useful_rate, 3),
            "suggestion": suggestion,
            "suggested_overrides": overrides,
            "threshold_keys": list(_TYPE_TO_KEYS.get(at, ())),
            "rationale_ar": rationale,
        }

    if not per_type:
        note = "لا نتائج تنبيهات مُسجَّلة بعد — لا اقتراحات (نتيجة صادقة فارغة)."
    else:
        note = (
            "اقتراحات قابلة للتفسير لضبط عتبات التنبيه لكلّ مستأجِر. "
            "human-in-the-loop: لا تُطبَّق آليّاً — يُراجعها ويُطبّقها المستأجِر "
            "عبر إعدادات alert_thresholds. heuristics agro-met تحتاج معايرة ميدانيّة."
        )

    return {
        "min_samples": MIN_SAMPLES,
        "false_positive_rate": FALSE_POSITIVE_RATE,
        "per_type": per_type,
        "note_ar": note,
    }
