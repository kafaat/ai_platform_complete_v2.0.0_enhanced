"""SAHOOL agriai-engine — aquacrop_adapter.py (وحدة صرفة، بلا FastAPI) — WATER-SALT-02.

المحرّك الثالث (المسار الملحيّ): يعكس نمط ``wofost_adapter`` لكن للإجهاد الملحيّ.
``simulate(crop, weather, soil, water_salt, agromanagement)`` يُرجع نفس المخطّط الموحّد
+ ``salt_profile`` (جديد مقابل PCSE): ``{ec_e, ks_salt, leaching_fraction}``.

**التنفيذ المعتمد (§5-2، اعتماد المالك 2026-07-20): Maas-Hoffman الداخليّ فقط** — لا حزمة
``aquacrop``/numba (مؤجَّلة إلى شريحة لاحقة تُبرَّر بالحاجة). Ks,salt من عتبة/ميل المحصول
(FAO-56 Eq.81، Ayers & Westcot 1985) + كسر غسيل (FAO-56 Eq.82، مسقوف 0.5).

**قاعدة التوجيه (عتبة ECe صريحة، §5-1) — مصدر حقيقة واحد:** المحرّك الملحيّ يُستدعى **فقط**
عند ``ec_e >= AQUACROP_ECE_THRESHOLD`` (افتراض 2.0 dS/m — تحته الأثر الملحيّ مهمَل، فيبقى
PCSE المرجع). لا «مجرّد وجود مدخل ملحيّ». العتبة معلَنة في عقد القدرة.

**صدق (§5-3 + ملاحظة الجلسة):** provenance دائماً ``aquacrop_uncalibrated`` (المعايرة حكر
SIM-GOLDEN-01). **حدّ «لا نقل ملح زمنيّ» يبقى في limits** — Maas-Hoffman ثابت (steady-state)
لا ديناميكيّ؛ النقل الزمنيّ ينتظر حزمة aquacrop الحقيقيّة. راية ``AQUACROP_ENABLED`` مطفأة
افتراضاً؛ وضع الإنتاج بلا الحزمة = فشل مُغلَق مُصنَّف (البديل الداخليّ تطويريّ).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("agriai-engine")

# ── حارس استيراد الحزمة الرسميّة (مؤجَّلة — ليست تبعيّة صلبة الآن) ──
try:  # pragma: no cover — الحزمة غير مُثبَّتة (مؤجَّلة §5-2)
    import aquacrop  # type: ignore  # noqa: F401

    _AQUACROP_PKG_AVAILABLE = True
except Exception:  # noqa: BLE001
    _AQUACROP_PKG_AVAILABLE = False

# عتبة تفعيل المحرّك الملحيّ (dS/m). تحتها: أثر ملحيّ مهمَل ⇒ PCSE المرجع (مصدر حقيقة واحد).
AQUACROP_ECE_THRESHOLD = float(os.getenv("AQUACROP_ECE_THRESHOLD", "2.0"))

# عتبات/ميول الملوحة المرجعيّة (FAO-56 Table / Maas-Hoffman) — **غير مُعايَرة يمنيّاً**.
# (a=عتبة ECe dS/m فوقها يبدأ الخفض، b=ميل الخفض ٪ لكلّ dS/m).
_SALT_TOLERANCE: dict[str, tuple[float, float]] = {
    "wheat": (6.0, 7.1),
    "barley": (8.0, 5.0),
    "potato": (1.7, 12.0),
}
_DEFAULT_TOLERANCE = (2.0, 10.0)  # محافظ لمحصول غير مُعرَّف (لا يُدّعى دقّة)


def aquacrop_enabled() -> bool:
    """الراية الحاكمة (default-off): بلا الراية لا يُشغَّل المحرّك الملحيّ أبداً."""
    return os.getenv("AQUACROP_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def salt_engine_applies(
    water_salt: dict[str, Any] | None, ece_threshold: float | None = None
) -> bool:
    """قاعدة التوجيه (§5-1): المحرّك الملحيّ يُستدعى فقط عند ec_e >= العتبة — لا مجرّد وجود مدخل.

    غياب ``water_salt`` أو ``ec_e`` كلّيّاً، أو ec_e تحت العتبة ⇒ ``False`` (PCSE المرجع).
    """
    thr = AQUACROP_ECE_THRESHOLD if ece_threshold is None else float(ece_threshold)
    if not water_salt:
        return False
    ec_e = water_salt.get("ec_e_initial")
    if ec_e is None:
        ec_e = water_salt.get("ece") or water_salt.get("ec_e")
    try:
        return ec_e is not None and float(ec_e) >= thr
    except (TypeError, ValueError):
        return False


def _salt_tolerance(crop: dict[str, Any] | None) -> tuple[float, float]:
    name = ((crop or {}).get("name") or (crop or {}).get("crop") or "").strip().lower()
    return _SALT_TOLERANCE.get(name, _DEFAULT_TOLERANCE)


def maas_hoffman_ks(ec_e: float, threshold_a: float, slope_b: float) -> float:
    """Ks,salt (FAO-56 Eq.81، Maas-Hoffman): 1 فوق العتبة يهبط خطّيّاً، مقصوص [0,1].

    رتابة مضمونة: ec_e أعلى ⇒ Ks أقلّ (حتّى القاع 0). ثابت (steady-state) لا زمنيّ.
    """
    if ec_e <= threshold_a:
        return 1.0
    ks = 1.0 - (slope_b / 100.0) * (ec_e - threshold_a)
    return max(0.0, min(1.0, ks))


def leaching_fraction(ec_irrigation: float | None, threshold_a: float) -> float:
    """كسر الغسيل (FAO-56 Eq.82): LR = ECw / (5·ECe_threshold − ECw)، مسقوف 0.5، ≥0.

    بلا ECw ⇒ 0.0 (لا يُحسَب دون ملوحة ماء الريّ — نفس حدّ WATER-SALT-01)."""
    if ec_irrigation is None or ec_irrigation <= 0 or threshold_a <= 0:
        return 0.0
    denom = 5.0 * threshold_a - ec_irrigation
    if denom <= 0:
        return 0.5
    return max(0.0, min(0.5, ec_irrigation / denom))


def _base_yield(crop: dict[str, Any] | None, soil: dict[str, Any] | None) -> float:
    """سقف الغلّة قبل الإجهاد الملحيّ (kg/ha) — من المحصول أو افتراض محافظ."""
    c = crop or {}
    for k in ("max_yield_kg_ha", "potential_yield_kg_ha", "yield_ceiling_kg_ha"):
        v = c.get(k)
        if v is not None:
            try:
                return max(0.0, float(v))
            except (TypeError, ValueError):
                # SILENT-EXCEPTION-HANDLERS-11-01: السقوط للافتراض المحافظ مقصود
                # وموثَّق أدناه، لكنّ ابتلاعه صامتاً كان يجعل **بيانات محصول تالفة**
                # ("4500 kg") لا تُميَّز عن «لا سقف غلّة مُسجَّل» — كلاهما 4000.0.
                # السلوك يبقى؛ يُضاف المفتاح وقيمته كي يُرى الفساد.
                logger.debug(
                    "قيمة سقف غلّة غير قابلة للتحويل: %s=%r — تجاهُلها ومتابعة البحث",
                    k,
                    v,
                )
    return 4000.0  # افتراض محافظ (uncalibrated؛ لا يُدّعى دقّة)


def simulate(
    crop: dict[str, Any] | None,
    weather: dict[str, Any] | None,
    soil: dict[str, Any] | None,
    water_salt: dict[str, Any] | None,
    agromanagement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """محاكاة المسار الملحيّ (Maas-Hoffman ثابت). المخطّط الموحّد + salt_profile.

    وضع الإنتاج (``AGRIAI_PRODUCTION_MODE``): الحزمة الرسميّة مطلوبة (البديل الداخليّ تطويريّ)
    ⇒ غيابها فشل مُغلَق مُصنَّف ``aquacrop_production_unavailable``. الراية مطفأة ⇒ فشل مُصنَّف.
    """
    production_mode = os.getenv("AGRIAI_PRODUCTION_MODE", "0").lower() in {"1", "true", "yes", "on"}
    if not aquacrop_enabled():
        if production_mode:
            raise RuntimeError("aquacrop_production_unavailable:aquacrop_disabled")
        # تطوير/اختبار: نُكمِل بالبديل الداخليّ الموسوم.
    elif production_mode and not _AQUACROP_PKG_AVAILABLE:
        # الراية مشعلة إنتاجاً لكن الحزمة الرسميّة (النقل الديناميكيّ) مؤجَّلة ⇒ لا تلفيق دقّة.
        raise RuntimeError("aquacrop_production_unavailable:package_deferred")

    ec_e = 0.0
    if water_salt:
        raw = water_salt.get("ec_e_initial", water_salt.get("ece", water_salt.get("ec_e")))
        try:
            ec_e = max(0.0, float(raw)) if raw is not None else 0.0
        except (TypeError, ValueError):
            ec_e = 0.0
    ec_w = None
    if water_salt and water_salt.get("ec_irrigation_dS_m") is not None:
        try:
            ec_w = float(water_salt["ec_irrigation_dS_m"])
        except (TypeError, ValueError):
            ec_w = None

    a, b = _salt_tolerance(crop)
    ks_salt = maas_hoffman_ks(ec_e, a, b)
    lr = leaching_fraction(ec_w, a)
    ceiling = _base_yield(crop, soil)
    yield_kg_ha = ceiling * ks_salt

    # كتلة حيويّة/استهلاك ماء تقديريّان (نسبة مع الغلّة) — مؤشّر لا قياس، uncalibrated.
    harvest_index = 0.45
    biomass = yield_kg_ha / harvest_index if harvest_index else yield_kg_ha
    wue = 1.2  # kg/m3 تقديريّ
    water_use = yield_kg_ha / wue if wue else 0.0

    return {
        "yield_kg_ha": round(yield_kg_ha, 1),
        "biomass": round(biomass, 1),
        "water_use": round(water_use, 1),
        "stages": [],  # المسار الملحيّ الثابت لا يُخرِج فينولوجيا زمنيّة (لا تلفيق مراحل)
        "salt_profile": {
            "ec_e": round(ec_e, 3),
            "ks_salt": round(ks_salt, 4),
            "leaching_fraction": round(lr, 4),
            "tolerance_threshold_a": a,
            "tolerance_slope_b": b,
        },
        "provenance": "aquacrop_uncalibrated",
        "engine": "maas_hoffman_internal",  # ليست الحزمة الرسميّة (مؤجَّلة §5-2)
    }


# ════════════════════════════════════════════════════════════════════════════
# عقد القدرة المُعلَن (بمعيار capability-contract-standard / A5)
# ════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class CapabilityClaim:
    claim: str
    ref: str


@dataclass(frozen=True)
class SaltEngineCapability:
    supported: bool
    model: str
    references: tuple[str, ...]
    covers: tuple[CapabilityClaim, ...]
    limits: tuple[str, ...]
    status_enum: tuple[str, ...]
    routing_rule: str
    calibration_status: str
    flag: str

    def to_dict(self) -> dict:
        return {
            "supported": self.supported,
            "model": self.model,
            "references": list(self.references),
            "covers": [{"claim": c.claim, "ref": c.ref} for c in self.covers],
            "limits": list(self.limits),
            "status_enum": list(self.status_enum),
            "routing_rule": self.routing_rule,
            "calibration_status": self.calibration_status,
            "flag": self.flag,
        }


AQUACROP_SALT_CAPABILITY = SaltEngineCapability(
    supported=True,
    model="maas_hoffman_static_ks + fao56_leaching_eq82",
    references=(
        "services/agriai-engine/aquacrop_adapter.py:maas_hoffman_ks",
        "services/agriai-engine/aquacrop_adapter.py:leaching_fraction",
        "services/agriai-engine/aquacrop_adapter.py:salt_engine_applies",
    ),
    covers=(
        CapabilityClaim(
            "Ks,salt ثابت لخفض الغلّة من ملوحة التربة (Maas-Hoffman، FAO-56 Eq.81) — رتابة مضمونة",
            "services/agriai-engine/aquacrop_adapter.py:maas_hoffman_ks",
        ),
        CapabilityClaim(
            "كسر الغسيل من ملوحة ماء الريّ (FAO-56 Eq.82، مسقوف 0.5)",
            "services/agriai-engine/aquacrop_adapter.py:leaching_fraction",
        ),
        CapabilityClaim(
            "توجيه بعتبة ECe صريحة: المحرّك الملحيّ فوق العتبة فقط، وإلّا PCSE (مصدر حقيقة واحد)",
            "services/agriai-engine/aquacrop_adapter.py:salt_engine_applies",
        ),
    ),
    limits=(
        # صدق حاسم: Maas-Hoffman ثابت ⇒ حدّ النقل الزمنيّ يبقى (لا يُنقَل إلى covers قبل حزمة aquacrop).
        "لا نقل ملح زمنيّ ولا تراكم ملح في منطقة الجذر (Maas-Hoffman ثابت steady-state؛ النقل ينتظر حزمة aquacrop).",
        "ملوحة رأسيّة/كتليّة فقط — لا انتشار جانبيّ بين الحقول.",
        "لا تفاعل ملوحة×صودية (sodicity/ESP خارج النطاق).",
        "معاملات تحمّل المحاصيل افتراضيّة FAO — غير مُعايَرة يمنيّاً.",
        "جودة مياه الريّ ثابتة موسميّاً ما لم تُمرَّر سلسلة زمنيّة (شريحة منفصلة).",
        "حقل واحد معزول — لا أحواض/آبار مشتركة.",
        "المعايرة غير مُثبَتة حتى SIM-GOLDEN-01؛ المخرَج aquacrop_uncalibrated.",
        "مطفأة افتراضاً (AQUACROP_ENABLED=off)؛ الإنتاج بلا الحزمة الرسميّة = فشل مُغلَق مُصنَّف.",
    ),
    status_enum=(
        "aquacrop_uncalibrated",  # Maas-Hoffman الداخليّ فعليّ لكن غير مُعايَر
        "aquacrop_production_unavailable",  # فشل مُغلَق مُصنَّف (إنتاج/الحزمة مؤجَّلة)
        "not_applicable_pcse_reference",  # ECe تحت العتبة ⇒ لم يُستدعَ (PCSE المرجع)
    ),
    routing_rule="ec_e >= AQUACROP_ECE_THRESHOLD (default 2.0 dS/m) ⇒ salt engine; else PCSE",
    calibration_status="uncalibrated_pending_golden",
    flag="AQUACROP_ENABLED",
)


def aquacrop_salt_capability_report() -> dict:
    return AQUACROP_SALT_CAPABILITY.to_dict()
