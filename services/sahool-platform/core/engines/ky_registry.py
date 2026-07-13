"""core/engines/ky_registry.py — سجلّ معاملات استجابة الغلّة للماء (Ky) الكنسيّ

مصدر Ky الوحيد الموثَّق للمنصّة: **FAO Irrigation and Drainage Paper 33** (Doorenbos &
Kassam, 1979) — «Yield Response to Water»، الجدول 24 (معاملات استجابة الغلّة الموسميّة
وبمراحل النموّ). **لا تُختلَق قيم Ky**: كلّ مدخل يحمل مصدره (`ky_source`)، ونسخته
(`version`)، وتاريخ سريانه (`effective_from`)، وعدم يقينه (`uncertainty`).

معادلة الاستجابة (تُطبَّق في `lexicographic_irrigation_mpc`):
    Ya/Ym = 1 − Ky · (1 − ETa/ETm)

القرارات الصادقة:
- **Ky حسب المحصول والمرحلة** أوّلاً (`ky_basis="crop_stage"`)؛ فإن غاب المحصول من السجلّ
  يُرجَع صفّ FAO-33 **العامّ حسب المرحلة** (`ky_basis="generic_stage"`) — مُعلَّم صراحةً
  بمصدره وبثقة أدنى، **لا استبدال صامت**.
- **مرحلة مجهولة/غير مُعرَّفة ⇒ لا قيمة** (`None`) ⇒ يعامله المتحكّم كـ`insufficient_data`.
- قيم Ky > 1 (مثل إزهار الذرة 1.5) تعني حساسيّة عالية؛ النموذج الخطّيّ يفقد صلاحيّته عند
  عجز شديد (relative_yield سالب) — يعالجه المتحكّم كـ«خارج حدود النموذج».

⚠ هذه معاملات تقديريّة (`calibrated_for_region=False`) — قيم أدبيّة FAO-33 لا معايرة يمنيّة.
"""

from __future__ import annotations

from dataclasses import dataclass

KY_REGISTRY_VERSION = "fao33-1979.v1"
_FAO33 = "FAO-33 (Doorenbos & Kassam, 1979), Table 24 — growth-stage yield response factor"
_FAO33_GENERIC = "FAO-33 (Doorenbos & Kassam, 1979) — generic growth-stage sensitivity"
_EFFECTIVE_FROM = "1979-01-01"

# مفردات المراحل المعتمدة في المنصّة (نفس supplemental_irrigation): تُطبَّق تسمية
# FAO-33 عليها (grain_fill≈yield-formation، maturity≈ripening، germination≈establishment).
_STAGES = ("germination", "vegetative", "flowering", "grain_fill", "maturity")


@dataclass(frozen=True)
class KyEntry:
    crop: str | None  # None = صفّ عامّ حسب المرحلة (crop-agnostic)
    growth_stage: str
    ky: float
    ky_source: str
    effective_from: str
    version: str
    uncertainty: float  # ± نطاق تقريبيّ على Ky (FAO-33 يعطي مدَيات)


@dataclass(frozen=True)
class KyLookup:
    ky: float
    ky_source: str
    ky_basis: str  # "crop_stage" | "generic_stage"
    crop: str | None
    growth_stage: str
    version: str
    effective_from: str
    uncertainty: float


# ── صفوف FAO-33 العامّة حسب المرحلة (المصدر الموثَّق نفسه المستخدَم في المنصّة) ──
# germination 0.40 · vegetative 0.55 · flowering 1.10 · grain_fill 0.85 · maturity 0.30
_GENERIC: dict[str, KyEntry] = {
    "germination": KyEntry(
        None, "germination", 0.40, _FAO33_GENERIC, _EFFECTIVE_FROM, KY_REGISTRY_VERSION, 0.10
    ),
    "vegetative": KyEntry(
        None, "vegetative", 0.55, _FAO33_GENERIC, _EFFECTIVE_FROM, KY_REGISTRY_VERSION, 0.15
    ),
    "flowering": KyEntry(
        None, "flowering", 1.10, _FAO33_GENERIC, _EFFECTIVE_FROM, KY_REGISTRY_VERSION, 0.20
    ),
    "grain_fill": KyEntry(
        None, "grain_fill", 0.85, _FAO33_GENERIC, _EFFECTIVE_FROM, KY_REGISTRY_VERSION, 0.15
    ),
    "maturity": KyEntry(
        None, "maturity", 0.30, _FAO33_GENERIC, _EFFECTIVE_FROM, KY_REGISTRY_VERSION, 0.10
    ),
}


# ── صفوف FAO-33 حسب المحصول والمرحلة (قيم Table 24 الموثَّقة فقط، محاصيل يمنيّة رئيسة) ──
# التعيين: vegetative=مرحلة النموّ الخضريّ · flowering=التزهير · grain_fill=تكوين الغلّة
# (yield formation) · maturity=النضج (ripening). germination يُترَك للعامّ (FAO-33 لا يفصله).
def _crop(crop: str, stage: str, ky: float, unc: float) -> KyEntry:
    return KyEntry(crop, stage, ky, _FAO33, _EFFECTIVE_FROM, KY_REGISTRY_VERSION, unc)


_CROP_SPECIFIC: tuple[KyEntry, ...] = (
    # Maize (الذرة الشاميّة) — FAO-33 Table 24: veg 0.4 · flowering 1.5 · yield-form 0.5 · ripening 0.2
    _crop("maize", "vegetative", 0.40, 0.10),
    _crop("maize", "flowering", 1.50, 0.20),
    _crop("maize", "grain_fill", 0.50, 0.15),
    _crop("maize", "maturity", 0.20, 0.10),
    # Sorghum (الذرة الرفيعة — محصول يمنيّ رئيس) — FAO-33: veg 0.2 · flowering 0.55 · yield-form 0.45 · ripening 0.2
    _crop("sorghum", "vegetative", 0.20, 0.10),
    _crop("sorghum", "flowering", 0.55, 0.15),
    _crop("sorghum", "grain_fill", 0.45, 0.15),
    _crop("sorghum", "maturity", 0.20, 0.10),
    # Wheat (القمح) — FAO-33 winter wheat: veg 0.2 · flowering 0.6 · yield-form 0.5 · ripening 0.0
    _crop("wheat", "vegetative", 0.20, 0.10),
    _crop("wheat", "flowering", 0.60, 0.15),
    _crop("wheat", "grain_fill", 0.50, 0.15),
    _crop("wheat", "maturity", 0.00, 0.05),
    # Tomato (الطماطم) — FAO-33 Table 24: veg 0.4 · flowering 1.1 · yield-form 0.8 · ripening 0.4
    _crop("tomato", "vegetative", 0.40, 0.10),
    _crop("tomato", "flowering", 1.10, 0.20),
    _crop("tomato", "grain_fill", 0.80, 0.15),
    _crop("tomato", "maturity", 0.40, 0.10),
    # Potato (البطاطس) — FAO-33: veg 0.45 · yield-form 0.7 · ripening 0.2 (لا تزهير مُنفصِل في الجدول)
    _crop("potato", "vegetative", 0.45, 0.10),
    _crop("potato", "grain_fill", 0.70, 0.15),
    _crop("potato", "maturity", 0.20, 0.10),
    # Onion (البصل) — FAO-33: veg 0.45 · yield-form 0.8
    _crop("onion", "vegetative", 0.45, 0.10),
    _crop("onion", "grain_fill", 0.80, 0.15),
)

_CROP_INDEX: dict[tuple[str, str], KyEntry] = {
    (e.crop, e.growth_stage): e for e in _CROP_SPECIFIC if e.crop is not None
}

# مرادفات أسماء المحاصيل الشائعة ⇒ المفتاح الكنسيّ في السجلّ.
_CROP_ALIASES: dict[str, str] = {
    "corn": "maize",
    "ذرة": "maize",
    "ذرة_شامية": "maize",
    "ذرة_رفيعة": "sorghum",
    "sorgum": "sorghum",
    "قمح": "wheat",
    "طماطم": "tomato",
    "بندورة": "tomato",
    "بطاطس": "potato",
    "بطاطا": "potato",
    "بصل": "onion",
}


def _norm(value: str | None) -> str:
    return str(value).strip().lower().replace(" ", "_") if value else ""


def lookup_ky(crop: str | None, growth_stage: str | None) -> KyLookup | None:
    """يعيد Ky الموثَّق لِـ(محصول، مرحلة)، أو None عند غياب المرحلة/عدم تعريفها.

    الترتيب: (محصول، مرحلة) خاصّ بالمحصول ⇒ الصفّ العامّ حسب المرحلة (مُعلَّم generic_stage)
    ⇒ None. **مرحلة مجهولة ⇒ None** (لا استبدال). لا استبدال صامت — الأساس مُصرَّح في الناتج.
    """
    stage = _norm(growth_stage)
    if stage not in _STAGES:
        return None  # مرحلة غائبة/غير مُعرَّفة ⇒ insufficient_data لدى المتحكّم

    crop_key = _norm(crop)
    crop_key = _CROP_ALIASES.get(crop_key, crop_key)
    entry = _CROP_INDEX.get((crop_key, stage))
    if entry is not None:
        return KyLookup(
            ky=entry.ky,
            ky_source=entry.ky_source,
            ky_basis="crop_stage",
            crop=entry.crop,
            growth_stage=entry.growth_stage,
            version=entry.version,
            effective_from=entry.effective_from,
            uncertainty=entry.uncertainty,
        )

    generic = _GENERIC.get(stage)
    if generic is not None:
        return KyLookup(
            ky=generic.ky,
            ky_source=generic.ky_source,
            ky_basis="generic_stage",
            crop=None,
            growth_stage=generic.growth_stage,
            version=generic.version,
            effective_from=generic.effective_from,
            uncertainty=generic.uncertainty,
        )
    return None
