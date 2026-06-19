"""api/calibration.py — طبقة المعايرة الإقليميّة اليمنيّة (Yemen Regional Calibration)

#382: أكبر خطر الآن ليس الكود بل «الافتراضات العامّة». هذه الطبقة تحوّل الثوابت
المبعثرة الموسومة (TAW، p، عمق الجذور، حدود Kc الديناميكيّ، ترشّح المطر، نِسَب
امتصاص العناصر، عدم اليقين الاقتصاديّ) إلى **مصدر واحد قابل للمعايرة لكلّ منطقة**:
الجوف / تهامة / مأرب / حضرموت / إب (+ افتراضيّ عامّ).

**بنية لا قيم:** القيم الإقليميّة الحقيقيّة بياناتك الميدانيّة — لا تُلفَّق هنا. لذا
الملفّ العامّ يستورد الثوابت الحاليّة نفسها (سلوك محفوظ بالبناء)، وكلّ منطقة يمنيّة
حاليّاً **ترث العامّ** وتُوسَم `validated=False` حتى تُزوَّد بقياسات منطقتها. عند توفّر
البيانات تُستبدَل قيم المنطقة فقط — دون لمس بقيّة الكود.

نقيّ حتميّ (لا I/O).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# المصدر الموحّد: الثوابت الحاليّة (الملفّ العامّ = سلوك اليوم بالبناء).
from api.economic_state import _DEFAULT_PRICE_UNCERTAINTY, _DEFAULT_YIELD_UNCERTAINTY
from api.nutrient_4r import _UPTAKE_FRACTIONS
from api.soil_water import _DEFAULT_RAW_FRACTION, _DEFAULT_ROOT_DEPTH_M
from api.water_balance import FORECAST_INFILTRATION_DEFAULT, KC_DYN_MAX, KC_DYN_MIN

# مناطق اليمن المستهدفة بالمعايرة (مفاتيح إنجليزيّة + أسماء عربيّة).
REGION_NAMES_AR: dict[str, str] = {
    "jawf": "الجوف",
    "tihama": "تهامة",
    "marib": "مأرب",
    "hadramout": "حضرموت",
    "ibb": "إب",
    "_generic": "عامّ (غير إقليميّ)",
}
# مرادفات عربيّة → مفتاح.
_REGION_ALIASES: dict[str, str] = {
    "الجوف": "jawf",
    "تهامة": "tihama",
    "مأرب": "marib",
    "حضرموت": "hadramout",
    "إب": "ibb",
    "اب": "ibb",
}


@dataclass
class CalibrationProfile:
    """ملفّ معايرة منطقة: الثوابت الزراعيّة القابلة للمعايرة + وسم التحقّق."""

    region: str
    region_ar: str
    validated: bool
    source_ar: str
    raw_fraction: float
    root_depth_m: float
    kc_dyn_min: float
    kc_dyn_max: float
    forecast_infiltration: float
    uptake_fractions: dict[str, float]
    yield_uncertainty: float
    price_uncertainty: float
    notes_ar: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "region": self.region,
            "region_ar": self.region_ar,
            "validated": self.validated,
            "source_ar": self.source_ar,
            "raw_fraction": self.raw_fraction,
            "root_depth_m": self.root_depth_m,
            "kc_dyn_min": self.kc_dyn_min,
            "kc_dyn_max": self.kc_dyn_max,
            "forecast_infiltration": self.forecast_infiltration,
            "uptake_fractions": dict(self.uptake_fractions),
            "yield_uncertainty": self.yield_uncertainty,
            "price_uncertainty": self.price_uncertainty,
            "notes_ar": self.notes_ar,
        }


def _generic_profile() -> CalibrationProfile:
    """الملفّ العامّ = الثوابت الحاليّة بالبناء (سلوك محفوظ). موسوم غير مُتحقَّق."""
    return CalibrationProfile(
        region="_generic",
        region_ar=REGION_NAMES_AR["_generic"],
        validated=False,
        source_ar="افتراضات عامّة (FAO-56/أدبيّات) — ليست مُعايَرة يمنيّاً",
        raw_fraction=_DEFAULT_RAW_FRACTION,
        root_depth_m=_DEFAULT_ROOT_DEPTH_M,
        kc_dyn_min=KC_DYN_MIN,
        kc_dyn_max=KC_DYN_MAX,
        forecast_infiltration=FORECAST_INFILTRATION_DEFAULT,
        uptake_fractions=dict(_UPTAKE_FRACTIONS),
        yield_uncertainty=_DEFAULT_YIELD_UNCERTAINTY,
        price_uncertainty=_DEFAULT_PRICE_UNCERTAINTY,
        notes_ar=["قيم عامّة — تحتاج معايرة ميدانيّة"],
    )


# تجاوزات لكلّ منطقة (region -> {field: value}). فارغة الآن: كلّ المناطق ترث العامّ
# حتى تتوفّر قياسات ميدانيّة. عند المعايرة: ضع قيم المنطقة هنا واضبط validated=True.
# ⚠ لا تَضع أرقاماً غير مُتحقَّقة هنا — يجب أن تكون من بيانات المنطقة الفعليّة.
_REGION_OVERRIDES: dict[str, dict] = {
    "jawf": {},
    "tihama": {},
    "marib": {},
    "hadramout": {},
    "ibb": {},
}


def normalize_region(region: str | None) -> tuple[str, bool]:
    """يُرجع (مفتاح المنطقة، هل هي معروفة). يطبّع العربيّة والحالة."""
    if not region:
        return "_generic", False
    key = region.strip().lower()
    key = _REGION_ALIASES.get(region.strip(), _REGION_ALIASES.get(key, key))
    if key in _REGION_OVERRIDES or key == "_generic":
        return key, key != "_generic"
    return "_generic", False


def get_calibration(region: str | None) -> CalibrationProfile:
    """ملفّ معايرة المنطقة — نقيّ حتميّ.

    منطقة معروفة بلا تجاوزات ⇒ ترث العامّ (validated=False، مع تنويه أنّها لم تُعايَر
    بعد). منطقة مجهولة ⇒ العامّ. أيّ تجاوز مُعايَر (مستقبلاً) يضبط القيمة وvalidated.
    """
    key, known = normalize_region(region)
    prof = _generic_profile()
    if not known:
        return prof

    overrides = _REGION_OVERRIDES.get(key, {})
    prof.region = key
    prof.region_ar = REGION_NAMES_AR.get(key, key)
    if not overrides:
        prof.validated = False
        prof.source_ar = f"منطقة {prof.region_ar}: ترث الافتراضات العامّة — لم تُعايَر ميدانيّاً بعد"
        prof.notes_ar = [
            f"لا تجاوزات مُعايَرة لـ{prof.region_ar} — زوّدنا بقياسات المنطقة (TAW/عمق/Kc/امتصاص)"
        ]
        return prof

    # عند توفّر تجاوزات مُعايَرة لاحقاً.
    for fld, val in overrides.items():
        if hasattr(prof, fld):
            setattr(prof, fld, val)
    prof.validated = True
    prof.source_ar = f"منطقة {prof.region_ar}: قيم مُعايَرة ميدانيّاً"
    prof.notes_ar = []
    return prof


def all_regions() -> list[str]:
    """مفاتيح المناطق اليمنيّة المستهدفة (دون العامّ)."""
    return list(_REGION_OVERRIDES.keys())
