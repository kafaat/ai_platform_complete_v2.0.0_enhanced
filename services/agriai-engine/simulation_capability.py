"""simulation_capability.py — عقد قدرة محاكاة المحصول المُعلَن (SIM-PCSE-01).

بمعيار ``capability-contract-standard`` المولود في A5: قدرة PCSE/WOFOST تُعلَن **بحدودها** قبل أن تُعلَن
بقدرتها. القيد الحاكم (لا يُتنازَل عنه): **عقد قدرة لا يُعلِن حدوده = fail-open مقنّع** — لذا ``limits`` و
``status_enum`` و``references`` إلزاميّة، وكلّ ادّعاء ``covers`` مقرون بمرجع ``file:line``؛ يفرض ذلك حارس
``tests_v9/test_simulation_capability_contract.py`` ببرهان سلبيّ (``supported:true`` بلا حدود يفشل).

وحدة صرفة (لا FastAPI/قاعدة/شبكة). مصدر الحقيقة الوحيد لمعنى «دعم المحاكاة» وحدوده.
"""

from __future__ import annotations

from dataclasses import dataclass

from sim_crop_registry import SUPPORTED_CROP_NAMES


@dataclass(frozen=True)
class CapabilityClaim:
    claim: str
    ref: str  # ``path.py:line``


@dataclass(frozen=True)
class SimulationCapability:
    """عقد قدرة المحاكاة — يصف المحرّك الحقيقيّ وحدوده، لا يخترع دقّة."""

    supported: bool
    model: str
    references: tuple[str, ...]
    covers: tuple[CapabilityClaim, ...]
    limits: tuple[str, ...]  # متى يتوقّف عن الثقة (الحدّ الصادق — يمنع fail-open)
    status_enum: tuple[str, ...]  # مفردات الحالة الحقيقيّة (provenance)
    supported_crops: tuple[str, ...]  # المحاصيل المدعومة **بالاسم** (سجلّ صريح)
    calibration_status: str  # حتى SIM-GOLDEN: uncalibrated
    flag: str  # الراية الحاكمة (default-off)

    def to_dict(self) -> dict:
        return {
            "supported": self.supported,
            "model": self.model,
            "references": list(self.references),
            "covers": [{"claim": c.claim, "ref": c.ref} for c in self.covers],
            "limits": list(self.limits),
            "status_enum": list(self.status_enum),
            "supported_crops": list(self.supported_crops),
            "calibration_status": self.calibration_status,
            "flag": self.flag,
        }


# ── العقد المُعلَن ────────────────────────────────────────────────
SIMULATION_CAPABILITY = SimulationCapability(
    supported=True,
    model="pcse_wofost72_wlp_fd",  # WOFOST 7.2، Water-Limited Production, Free Drainage
    references=(
        "services/agriai-engine/wofost_adapter.py:_pcse_run",  # التوصيل الصحيح لموفِّرات PCSE
        "services/agriai-engine/sim_crop_registry.py",  # المحاصيل المدعومة + مصدر معاملاتها
    ),
    covers=(
        CapabilityClaim(
            "الإنتاج المحدود بالمياه (WLP): غلّة/كتلة حيويّة/استهلاك ماء + مراحل نموّ",
            "services/agriai-engine/wofost_adapter.py:_pcse_run",
        ),
        CapabilityClaim(
            "المحاصيل المدعومة بالاسم من معاملات PCSE الرسميّة (لا معاملات مقترَضة)",
            "services/agriai-engine/sim_crop_registry.py:_REGISTRY",
        ),
    ),
    limits=(
        # WLP فقط — الإنتاج المحتمل (potential) غير معروض عمداً (منصّة ريّ: الإنتاج المحدود بالمياه وضعها الطبيعيّ).
        "WLP فقط (Water-Limited Production): الإنتاج المحتمل (potential production) **غير معروض** — لا سقف نظريّ.",
        # لا محرّكين للملوحة: PCSE لا يُنمذج الملوحة؛ تبقى عبر مسار fao56/الغسيل (A5). guard يمنع تسرّبها.
        "لا ملوحة في PCSE — الملوحة تبقى في core/engines/fao56 (Maas-Hoffman + غسيل، A5)؛ لا التقاء محرّكين.",
        # المحاصيل بالاسم فقط: خارج السجلّ ⇒ fail-closed (لا معاملات مقترَضة).
        "المحاصيل المدعومة بالاسم حصراً (wheat/barley/potato v1)؛ محصول آخر ⇒ fail-closed لا افتراض.",
        # المعايرة غير مُثبَتة حتى SIM-GOLDEN: لا يُسوَّق تنبّؤاً موثوقاً قبلها.
        "المعايرة غير مُثبَتة حتى SIM-GOLDEN-01 (بيانات حصاد حقيقيّة + عتبات خطأ)؛ المخرَج uncalibrated.",
        # مطفأة افتراضاً: بلا الراية لا محرّك علميّ (السلوك الصادق القائم: fallback تطويريّ / fail-closed إنتاجيّ).
        "مطفأة افتراضاً (SIM_PCSE_ENABLED=off): بلا الراية لا يُشغَّل PCSE — الأمانة القائمة تبقى.",
    ),
    status_enum=(
        "pcse_wofost_uncalibrated",  # PCSE فعليّ لكن غير مُعايَر (قبل golden)
        "deterministic_fallback",  # البديل الحتميّ (تطوير، الراية مطفأة)
        "simulation_unavailable",  # فشل مُغلَق مُصنَّف (إنتاج/راية مشعلة بلا شرط)
    ),
    supported_crops=SUPPORTED_CROP_NAMES,
    calibration_status="uncalibrated_pending_golden",
    flag="SIM_PCSE_ENABLED",
)


def simulation_capability_report() -> dict:
    """تقرير القدرة (يُستهلَك عبر نقطة قدرات/تصدير دون تكرار)."""
    return SIMULATION_CAPABILITY.to_dict()
