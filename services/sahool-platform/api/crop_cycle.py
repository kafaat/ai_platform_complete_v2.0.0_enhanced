"""
api/crop_cycle.py — resolver طول دورة المحصول (أيّام من البذار للنضج).

يستبدل القاموس المُصلَّب `_CROP_CYCLE_DAYS` في recommendations_hub بـ resolver
طبقيّ يشتقّ القيمة من بطاقات المحاصيل المحايدة للموقع (core/crop_cards/) مع
طبقة تجاوز خاصّة بالمنطقة. نقيّ بالكامل (لا شبكة، لا قاعدة) — يُختبَر offline.

ترتيب الطبقات (من الأخصّ للأعمّ):
  (أ) overrides من المُستدعي  — خطّاف مستقبليّ لكلّ مستأجِر (tenant).
  (د) _REGION_DEFAULT_OVERRIDES — معايرة المنطقة الافتراضيّة (اليمن).
  (ج) card_cycle_days        — الأساس المحايد FAO-56 من بطاقة المحصول.
  (—) None                    — لا بطاقة ولا تجاوز.
"""

from __future__ import annotations


def _normalize_crop(crop: str | None) -> str | None:
    """يطابق تطبيع الـ hub: تجريد فراغات + خفض حالة الأحرف."""
    if not crop:
        return None
    return crop.strip().lower() or None


def card_cycle_days(crop: str | None) -> int | None:
    """الطبقة (ج): الأساس المحايد FAO-56 من بطاقة المحصول.

    يحمّل بطاقة المحصول؛ إن وُجد `kc.stage_days` قائمةً غير فارغة من أرقام،
    يُرجع مجموعها (طول الدورة من البذار للنضج). وإلّا None.
    لا يرفع استثناءً أبداً — أيّ خطأ (لا بطاقة / شكل غير صالح) ⇐ None."""
    name = _normalize_crop(crop)
    if name is None:
        return None
    try:
        from core.crop_cards.loader import load_crop_card

        card = load_crop_card(name)
        if not card:
            return None
        stage_days = card.get("kc", {}).get("stage_days")
        if not isinstance(stage_days, list) or not stage_days:
            return None
        if not all(isinstance(d, (int, float)) for d in stage_days):
            return None
        return int(sum(stage_days))
    except Exception:
        return None


# الطبقة (د): تقديرات خاصّة بالموقع (اليمن) = طبقة معايرة "المنطقة الافتراضيّة".
# منقولة حرفيّاً من _CROP_CYCLE_DAYS القديم في recommendations_hub — تتجاوز
# عمداً الأساس المحايد للبطاقة (مثلاً القمح 130 يوماً مقابل مجموع مراحل البطاقة 120).
_REGION_DEFAULT_OVERRIDES: dict[str, int] = {
    "wheat": 130,
    "barley": 110,
    "sorghum": 120,
    "maize": 110,
    "corn": 110,
    "millet": 90,
    "tomato": 110,
    "potato": 110,
    "onion": 150,
    "alfalfa": 60,  # دورة قصّ (متعدّد الحشّات) لا نضج نهائيّ
    "citrus": 240,
    "dates": 210,
}


def cycle_days_to_maturity(
    crop: str | None, *, overrides: dict[str, int] | None = None
) -> int | None:
    """طول دورة المحصول (أيّام من البذار للنضج) بحلّ طبقيّ.

    ترتيب الحلّ (من الأخصّ للأعمّ):
      1) overrides من المُستدعي  — طبقة المستأجِر (tenant، خطّاف مستقبليّ).
      2) _REGION_DEFAULT_OVERRIDES — طبقة المنطقة الافتراضيّة (اليمن).
      3) card_cycle_days(crop)    — الأساس المحايد FAO-56 من بطاقة المحصول.
      4) None                      — لا بطاقة ولا تجاوز.

    يُلغي القاموس المُصلَّب القديم مع البقاء مدفوعاً بالإعداد/البيانات الوصفيّة
    (Configuration/Metadata-driven) وقابلاً للامتداد: أيّ محصول له بطاقة يُحلّ
    تلقائيّاً دون تعديل الكود."""
    name = _normalize_crop(crop)
    if name is None:
        return None
    if overrides and name in overrides:
        return overrides[name]
    if name in _REGION_DEFAULT_OVERRIDES:
        return _REGION_DEFAULT_OVERRIDES[name]
    return card_cycle_days(name)
