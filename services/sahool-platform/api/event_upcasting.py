"""
event_upcasting.py — ترقية مخطّط الأحداث (سدّ فجوة: حماية إعادة التشغيل).

المشكلة (مراجعة #4): مخزن الأحداث append-only ثابت. حين يتغيّر شكل حدث
(إضافة/إعادة تسمية حقل)، تحتاج إعادة التشغيل لترقية (upcasting) الأحداث
القديمة لأحدث مخطّط — وإلّا تنكسر إعادة بناء الحالة.

الحلّ: سجلّ upcasters لكلّ (event_type, from_version) → دالّة تحوّل الـpayload
لأحدث نسخة. يُطبَّق عند القراءة (قبل reconstruct). لا يعدّل المخزن (يبقى
append-only)؛ الترقية في الذاكرة وقت إعادة التشغيل.

صدق: لا يخترع حقولاً بقيم وهميّة — يضيف افتراضات صريحة موثّقة، أو يترك None.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, Tuple

logger = logging.getLogger("sahool.event_upcasting")

# النسخة الحاليّة لكلّ نوع حدث (المرجع)
CURRENT_VERSIONS: Dict[str, str] = {
    "lifecycle.transitioned": "1.0",
    "operation.irrigation.completed": "1.0",
    "operation.fertilizer.applied": "1.0",
    "remote_sensing.ndvi.observed": "1.0",
    "trueup.applied": "1.0",
}

# سجلّ المرقّيات: (event_type, from_version) → دالّة(payload)->payload
_UPCASTERS: Dict[Tuple[str, str], Callable[[dict], dict]] = {}


def _vkey(v: str) -> tuple:
    """L2 FIX: مفتاح ترتيب عدديّ للنسخ. المقارنة النصّية تجعل "1.10" < "1.2"،
    فتختلّ سلسلة الترقية عند بلوغ النسخ الفرعيّة خانتين."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def register_upcaster(event_type: str, from_version: str):
    """ديكوريتر لتسجيل مرقّي. الدالّة تأخذ payload قديماً وتُرجِع أحدث."""
    def deco(fn: Callable[[dict], dict]):
        _UPCASTERS[(event_type, from_version)] = fn
        return fn
    return deco


def upcast(event_type: str, payload: dict, version: str) -> Tuple[dict, str]:
    """يرقّي payload لأحدث نسخة عبر سلسلة المرقّيات. يُرجِع (payload, version).

    يطبّق المرقّيات بالتسلسل (1.0→1.1→1.2...) حتّى الوصول للنسخة الحاليّة.
    حتميّ + idempotent: نفس المدخل = نفس المخرج؛ نسخة حاليّة = لا تغيير.
    إن انقطعت السلسلة (لا مرقّي لقفزة)، يتوقّف بصدق (لا يخترع تحويلاً).
    """
    current = CURRENT_VERSIONS.get(event_type)
    if current is None or version == current:
        return payload, version

    # سلسلة النسخ المتاحة للترقية، مرتّبة (للتطبيق بالتسلسل الحتمي)
    available = sorted((fv for (et, fv) in _UPCASTERS if et == event_type), key=_vkey)
    v = version
    guard = 0
    while v != current and guard < 20:
        fn = _UPCASTERS.get((event_type, v))
        if fn is None:
            # لا مرقّي لهذه النسخة — توقّف بصدق (لا تخترع)
            logger.warning("لا مرقّي لـ%s من %s — يُترك كما هو", event_type, v)
            break
        payload = fn(dict(payload))  # نسخة دفاعيّة (حتميّة)
        # انتقل للنسخة التالية في السلسلة المرتّبة بعد v
        nxt = None
        for fv in available:
            if _vkey(fv) > _vkey(v):
                nxt = fv
                break
        v = nxt if nxt is not None else current
        guard += 1
    return payload, v


# ─── مثال مرقٍّ (قالب للمستقبل) ──────────────────────────────────────
# عند تغيير شكل حدث مستقبلاً، سجّل مرقّياً هكذا:
#
# @register_upcaster("operation.irrigation.completed", "1.0")
# def _irrigation_1_0_to_1_1(p: dict) -> dict:
#     """1.0→1.1: water_m3 صار water_liters (×1000). صدق: تحويل صريح موثّق."""
#     if "water_m3" in p and "water_liters" not in p:
#         p["water_liters"] = p["water_m3"] * 1000
#     return p
#
# هذا يضمن أنّ إعادة تشغيل أحداث 1.0 القديمة تنتج حالة بمخطّط 1.1 الحالي.
