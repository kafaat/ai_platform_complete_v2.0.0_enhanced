"""سجلّ محاصيل محاكاة WOFOST (SIM-PCSE-01) — المحاصيل المدعومة **بالاسم** + مصدر معاملاتها.

**لا اختلاق معاملات:** هذا السجلّ يُعلن أيّ المحاصيل مدعومة وأين تأتي معاملاتها (parameter_source +
parameter_version)، لا يخترع أرقام WOFOST. المعاملات الفعليّة تُحمَّل وقت التشغيل من ملفّات PCSE الرسميّة
(``YAMLCropDataProvider``) حين تتوفّر التبعيّة — فالسجلّ يربط اسم SAHOOL بهويّة المحصول/الصنف في تلك الملفّات.

**قائمة v1 (قرار المالك):** تقاطع «PCSE يشحن معاملاتها» × «سوق المنصّة»: wheat · barley · potato. المحاصيل
اليمنيّة الحسّاسة (sorghum/onion/tomato) **لا تدخل v1** — لا ملفّات معاملات جاهزة؛ إدخالها بمعاملات مقترَضة
بلا معايرة = تسويق زائف. محصول خارج السجلّ ⇒ fail-closed (لا افتراض صامت).
"""

from __future__ import annotations

from dataclasses import dataclass

# مصدر معاملات WOFOST الرسميّ (نفس انضباط مرجعيّة المصادر المُطبَّق على الحدود/التربة).
_WOFOST_PARAM_SOURCE = "ajwdewit/WOFOST_crop_parameters (PCSE YAMLCropDataProvider)"
_WOFOST_PARAM_VERSION = "2020-07"  # وسم مجموعة الملفّات المرجعيّة (يُثبَّت عند تركيب pcse في التكامل)


@dataclass(frozen=True)
class SimCrop:
    """محصول محاكاة مدعوم — اسمه + هويّة معاملاته في ملفّات PCSE + مصدرها (لا أرقام مخترَعة)."""

    name: str  # اسم SAHOOL
    pcse_crop: str  # اسم المحصول في YAMLCropDataProvider
    pcse_variety: str  # الصنف الافتراضيّ (معاملاته الجاهزة)
    parameter_source: str
    parameter_version: str


# ── سجلّ v1 (بالاسم فقط؛ الأرقام من ملفّات PCSE وقت التشغيل) ──
_REGISTRY: dict[str, SimCrop] = {
    "wheat": SimCrop(
        "wheat", "wheat", "Winter_wheat_101", _WOFOST_PARAM_SOURCE, _WOFOST_PARAM_VERSION
    ),
    "barley": SimCrop(
        "barley", "barley", "Spring_barley_301", _WOFOST_PARAM_SOURCE, _WOFOST_PARAM_VERSION
    ),
    "potato": SimCrop(
        "potato", "potato", "Potato_701", _WOFOST_PARAM_SOURCE, _WOFOST_PARAM_VERSION
    ),
}

SUPPORTED_CROP_NAMES: tuple[str, ...] = tuple(sorted(_REGISTRY))


def _canonical(name: str | None) -> str:
    return (name or "").strip().lower()


def is_supported(name: str | None) -> bool:
    return _canonical(name) in _REGISTRY


def get(name: str | None) -> SimCrop | None:
    return _REGISTRY.get(_canonical(name))
