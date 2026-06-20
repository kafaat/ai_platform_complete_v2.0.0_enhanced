"""api/nl_gis_intent.py — مُحلّل نيّة لاستعلامات GIS باللغة الطبيعيّة (read-only، #9)

**لا توليد SQL ولا نموذج لُغويّ حُرّ.** هذه طبقة تصنيف حتميّة نقيّة تحوّل نصّ المستخدم
العربيّ إلى **نيّة من قائمة مغلقة** (whitelist) + خانات (slots) مُستخلَصة بحُرّاس صريحة.
أيّ نصّ لا يطابق نيّة معروفة ⇒ ``unsupported`` (لا تخمين، لا استدعاء عشوائيّ). النيّة
المعروفة يُترجمها الموجِّه لاحقاً إلى **استدعاء قراءة فقط لمصدر موجود** — لا إنشاء/تعديل/
حذف، لا أوامر، لا SQL حُرّ.

النيّات المدعومة (المرحلة الأولى — 3 فقط):
  • ``ndvi_drop``     — حقول انخفض مؤشّر NDVI فيها أكثر من عتبة٪ (من ndvi_timeseries).
  • ``alert_filter`` — حقول (محصول/منطقة) لديها تنبيه نشط من نوع‑ما (من alerts ⋈ fields).
  • ``irrigation_gap`` — حقول لم تُروَ منذ N يوم (من irrigation_schedules.last_run_at).

**الصدق**: الخانات مُستخلَصة من النصّ فقط (لا قيم مُختلقة)؛ غياب خانة ⇒ افتراض مُوثَّق
أو طلب توضيح. الثقة المنخفضة ⇒ ``unsupported`` مع سبب صريح — لا تنفيذ ظنّيّ.

نقيّ حتميّ (لا قاعدة، لا I/O، لا شبكة) — قابل للاختبار offline؛ يستهلكه ``routers/nl_gis``.
"""

from __future__ import annotations

import re

# عتبة NDVI الافتراضيّة (٪) إن لم يذكرها المستخدم — مُوثَّقة لا مُختلقة.
_DEFAULT_NDVI_DROP_PCT = 15.0
# فجوة الريّ الافتراضيّة (أيّام) إن لم تُذكر.
_DEFAULT_IRRIGATION_GAP_DAYS = 5

# خرائط مفردات عربيّة → قيم مجال القاعدة (CHECK constraints الفعليّة).
_ALERT_TYPE_TERMS: dict[str, tuple[str, ...]] = {
    "heat_stress": ("حرار", "حر ", "إجهاد حراري", "اجهاد حراري", "موجة حر"),
    "low_moisture": ("رطوب", "جفاف", "عطش", "نقص ماء", "نقص الماء"),
    "heavy_rain": ("مطر", "أمطار", "امطار", "سيول", "غزير"),
    "disease_risk": ("مرض", "أمراض", "امراض", "إصابة", "اصابة", "فطر", "آفة", "افة"),
    "frost_risk": ("صقيع", "تجمّد", "تجمد", "برد قارس"),
}

# محاصيل معروفة (تُطابَق كنصّ LIKE على fields.crop — لا تلفيق، النصّ كما ورد).
_CROP_TERMS: tuple[str, ...] = (
    "قمح",
    "شعير",
    "ذرة",
    "طماطم",
    "بطاطس",
    "بطاطا",
    "خضروات",
    "خضار",
    "بصل",
    "بن",
    "عنب",
    "رمان",
    "مانجو",
)

# مناطق/محافظات معروفة (تُطابَق على fields.gov).
_REGION_TERMS: tuple[str, ...] = (
    "الجوف",
    "البيضاء",
    "رداع",
    "صنعاء",
    "مأرب",
    "مارب",
    "ذمار",
    "إب",
    "اب",
    "تعز",
    "الحديدة",
    "حضرموت",
    "عتمة",
    "ذي السفال",
    "الرياشية",
)

# كلمات دالّة على كلّ نيّة (لكشف النيّة).
_NDVI_TERMS = ("ndvi", "إن دي في", "الغطاء النبات", "الغطاء الأخضر", "الإخضرار", "الاخضرار")
_DROP_TERMS = ("انخفض", "انخفاض", "تراجع", "تراجعت", "نقص", "هبط", "هبوط", "تدهور")
_IRRIGATION_TERMS = ("ريّ", "ري", "تُروَ", "تروى", "تُسقَ", "تسقى", "سقي", "روي")
_GAP_TERMS = ("لم", "منذ", "متأخّر", "متأخر", "تأخّر", "تأخر", "فجوة")
_ALERT_TERMS = ("تنبيه", "تنبيهات", "إنذار", "انذار", "تحذير", "إشعار", "اشعار")


def _normalize(text: str) -> str:
    """تطبيع خفيف: تصغير لاتينيّ + ضغط الفراغات (يبقي العربيّة كما هي)."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _find_number(text: str, unit_pattern: str) -> float | None:
    """يستخرج رقماً يلي/يسبق وحدةً (يوم/٪) — None إن غاب (لا تلفيق)."""
    # رقم قبل الوحدة: «5 أيّام»، «15 %»
    m = re.search(r"(\d+(?:\.\d+)?)\s*" + unit_pattern, text)
    if m:
        return float(m.group(1))
    return None


def _detect_alert_type(text: str) -> str | None:
    """يطابق نوع التنبيه العربيّ → قيمة CHECK الفعليّة، أو None إن لم يُذكر نوع."""
    for db_value, terms in _ALERT_TYPE_TERMS.items():
        if any(t in text for t in terms):
            return db_value
    return None


def _detect_term(text: str, terms: tuple[str, ...]) -> str | None:
    """يعيد أوّل مصطلح من القائمة ظهر في النصّ (كما ورد) — أو None."""
    for t in terms:
        if t in text:
            return t
    return None


def parse_nl_intent(text: str) -> dict:
    """يصنّف نصّاً عربيّاً إلى نيّة GIS مغلقة + خانات — حتميّ نقيّ، read-only.

    يعيد قاموساً: ``intent`` (ndvi_drop|alert_filter|irrigation_gap|unsupported)،
    ``slots`` (خانات مُستخلَصة)، ``confidence`` (0..1)، ``supported`` (bool)،
    و``reason_ar`` عند عدم الدعم. لا يستدعي شيئاً ولا يلمس قاعدة — مجرّد تصنيف.

    قواعد الصدق: الخانات من النصّ فقط؛ غيابها ⇒ افتراض مُوثَّق (عتبة 15٪/فجوة 5 أيّام)
    لا قيمة مُختلقة. النصّ بلا نيّة معروفة ⇒ unsupported (لا تخمين، لا SQL حُرّ).
    """
    raw = text or ""
    t = _normalize(raw)
    if not t:
        return {
            "intent": "unsupported",
            "slots": {},
            "confidence": 0.0,
            "supported": False,
            "reason_ar": "استعلام فارغ — اكتب طلباً مثل «اعرض حقول القمح التي لديها تنبيه حرارة».",
        }

    has_ndvi = any(term in t for term in _NDVI_TERMS)
    has_drop = any(term in t for term in _DROP_TERMS)
    has_irrigation = any(term in t for term in _IRRIGATION_TERMS)
    has_gap = any(term in t for term in _GAP_TERMS)
    has_alert = any(term in t for term in _ALERT_TERMS)

    crop = _detect_term(t, _CROP_TERMS)
    region = _detect_term(t, _REGION_TERMS)

    # ١) NDVI drop — أقوى إشارة (مصطلح NDVI صريح) مع كلمة انخفاض.
    if has_ndvi and has_drop:
        pct = _find_number(t, r"%") or _find_number(t, r"(?:بالمئة|بالمائة|في المئة)")
        slots = {
            "threshold_pct": pct if pct is not None else _DEFAULT_NDVI_DROP_PCT,
            "threshold_is_default": pct is None,
            "crop": crop,
            "region": region,
        }
        return {
            "intent": "ndvi_drop",
            "slots": slots,
            "confidence": 0.9,
            "supported": True,
        }

    # ٢) فجوة ريّ — كلمات الريّ + (لم/منذ + رقم أيّام).
    if has_irrigation and (has_gap or _find_number(t, r"(?:يوم|أيّام|أيام|يوماً|يومًا)")):
        days = _find_number(t, r"(?:يوم|أيّام|أيام|يوماً|يومًا)")
        slots = {
            "days": int(days) if days is not None else _DEFAULT_IRRIGATION_GAP_DAYS,
            "days_is_default": days is None,
            "crop": crop,
            "region": region,
        }
        return {
            "intent": "irrigation_gap",
            "slots": slots,
            "confidence": 0.85 if days is not None else 0.7,
            "supported": True,
        }

    # ٣) تصفية تنبيهات — كلمة تنبيه (+ نوع/محصول/منطقة اختياريّة).
    if has_alert:
        alert_type = _detect_alert_type(t)
        slots = {
            "alert_type": alert_type,  # None ⇒ كلّ الأنواع النشطة
            "crop": crop,
            "region": region,
        }
        # ثقة أعلى كلّما توفّر مُرشِّح (نوع/محصول/منطقة).
        filled = sum(1 for v in (alert_type, crop, region) if v)
        return {
            "intent": "alert_filter",
            "slots": slots,
            "confidence": min(0.95, 0.6 + 0.12 * filled),
            "supported": True,
        }

    # غير مدعوم: لا نيّة معروفة ⇒ نرفض صراحةً (لا تخمين، لا تنفيذ).
    return {
        "intent": "unsupported",
        "slots": {"crop": crop, "region": region},
        "confidence": 0.0,
        "supported": False,
        "reason_ar": (
            "لم أتعرّف على طلب مدعوم. النيّات المتاحة (قراءة فقط): انخفاض NDVI بنسبة، "
            "تصفية الحقول بتنبيه نشط، أو حقول لم تُروَ منذ مدّة. أعد الصياغة بإحداها."
        ),
    }


# قائمة النيّات المدعومة (whitelist) — يستعملها الموجِّه للتحقّق قبل أيّ تنفيذ.
SUPPORTED_INTENTS: frozenset[str] = frozenset({"ndvi_drop", "alert_filter", "irrigation_gap"})
