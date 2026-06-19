"""core/kc_to_fao56_bridge.py — جسر نقيّ: Kc المُشتقّ (WOFOST) ⇐ CropKcProfile (FAO-56).

الفجوة المسدودة: `kc_extraction_engine` يشتقّ معاملات Kc من محاكاة WOFOST (مع تصحيح
CFET وتنعيم متحرّك) لكنّها تبقى **وصفيّة** — لا تُغذّي حساب الريّ. هذا الجسر يحوّل
`FaoStageKc` المُشتقّ إلى `CropKcProfile` الذي يستهلكه `fao56.compute_irrigation`، فيحلّ
Kc الخاصّ بالحقل/الموسم محلّ قيم FAO الجدوليّة العامّة — مع الحفاظ على خصائص بطاقة
المحصول غير-Kc (أطوال المراحل، عتبة الملوحة وميلها) التي لا تُشتقّ من Kc.

نقيّ حتميّ: لا I/O، لا numpy. تركيبٌ لا تعديل — لا يلمس `kc_extraction_engine` ولا
`engines/fao56` (يستورد منهما فقط). دالّتان:
  • `apply_derived_kc(card, stage_kc)` — دمج آمن: يُبدِل قيم Kc في بطاقة موجودة، والمراحل
    الناقصة (None) تُبقي قيمة البطاقة (لا اختلاق).
  • `stage_kc_to_crop_profile(...)` — بناء كامل من Kc المُشتقّ + خصائص بطاقة مُمرَّرة؛
    يرفع ValueError إن كانت أيّ مرحلة Kc ناقصة (لا نختلق قيمة).
"""

from __future__ import annotations

from core.engines.fao56 import CropKcProfile
from core.kc_extraction_engine import FaoStageKc

_DERIVED_TAG = "Kc مُشتقّ من محاكاة WOFOST (CFET+تنعيم)"


def apply_derived_kc(card: CropKcProfile, stage_kc: FaoStageKc) -> CropKcProfile:
    """يُرجِع نسخة من بطاقة المحصول بقيم Kc المُشتقّة، حافظاً أطوال المراحل والملوحة.

    دمج آمن: كلّ مرحلة Kc مُشتقّة موجودة (غير None) تُبدِل قيمة البطاقة؛ المرحلة الناقصة
    تُبقي قيمة البطاقة (لا اختلاق). `crop_id`/`stage_days`/معاملات الملوحة من البطاقة دائماً.
    """
    return CropKcProfile(
        crop_id=card.crop_id,
        kc_initial=card.kc_initial if stage_kc.kc_ini is None else float(stage_kc.kc_ini),
        kc_mid=card.kc_mid if stage_kc.kc_mid is None else float(stage_kc.kc_mid),
        kc_end=card.kc_end if stage_kc.kc_end is None else float(stage_kc.kc_end),
        stage_days=list(card.stage_days),
        salt_tolerance_ece=card.salt_tolerance_ece,
        salt_slope_pct=card.salt_slope_pct,
        source=f"{card.source} + {_DERIVED_TAG}",
    )


def stage_kc_to_crop_profile(
    stage_kc: FaoStageKc,
    *,
    crop_id: str,
    stage_days: list[int],
    salt_tolerance_ece: float,
    salt_slope_pct: float,
    source: str = _DERIVED_TAG,
) -> CropKcProfile:
    """يبني `CropKcProfile` كاملاً من Kc القياسيّ المُشتقّ (kc_ini/mid/end) + خصائص مُمرَّرة.

    خصائص البطاقة (أطوال المراحل، الملوحة) لا تُشتقّ من Kc فتُمرَّر صراحةً. يرفع
    `ValueError` إن كانت أيّ مرحلة Kc ناقصة (None) — لا نبني ملفّاً بقيمة مختلَقة.
    """
    missing = [
        name
        for name, value in (
            ("kc_ini", stage_kc.kc_ini),
            ("kc_mid", stage_kc.kc_mid),
            ("kc_end", stage_kc.kc_end),
        )
        if value is None
    ]
    if missing:
        raise ValueError(
            f"Kc المُشتقّ ناقص للمراحل: {', '.join(missing)} — لا يمكن بناء CropKcProfile"
        )
    return CropKcProfile(
        crop_id=crop_id,
        kc_initial=float(stage_kc.kc_ini),
        kc_mid=float(stage_kc.kc_mid),
        kc_end=float(stage_kc.kc_end),
        stage_days=list(stage_days),
        salt_tolerance_ece=salt_tolerance_ece,
        salt_slope_pct=salt_slope_pct,
        source=source,
    )
