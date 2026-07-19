"""salinity_capability.py — عقد قدرة الملوحة المُعلَن (WATER-SALT-01 / A5).

يُصرّح بالسلوك القائم للملوحة — المُثبَت ``file:line`` في محرّك FAO-56 والسياسات — في
عقد قدرة **واحد مقروء**، بدل بعثرته عبر ثلاث آليّات (بوّابة HALT · سياسة الريّ ·
توصية العجز ``recommended=False``). **لا يغيّر أيّ رياضيّات** (عميقة وصحيحة في
``core/engines/fao56.py``) — تجميع + إعلان فقط. من «دفاع مبعثر» إلى قدرة مُعلَنة.

القيد الحاكم (لا يُتنازَل عنه): **عقد قدرة لا يُعلِن حدوده = fail-open مقنّع.** لذا
``limits`` و``status_enum`` و``references`` إلزاميّة، وكلّ ادّعاء ``covers`` مقرون
بمرجع ``file:line``؛ يفرض ذلك حارس ``tests/test_salinity_capability_contract.py``
ببرهان سلبيّ (عقد ``supported:true`` بلا حدود يفشل).

وحدة صرفة (لا FastAPI/قاعدة/شبكة). مصدر الحقيقة الوحيد لمعنى «دعم الملوحة» وحدوده؛
يُستهلَك مستقبلاً (مظروف B1 · تصدير قدرات · نقطة قدرات) دون تكرار.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityClaim:
    """ادّعاء قدرة مفرد مقروناً بمرجعه في الشيفرة (لا قدرة مزعومة بلا سند)."""

    claim: str
    ref: str  # ``path.py:line`` (أو مدى/قائمة أسطر)


@dataclass(frozen=True)
class SalinityCapability:
    """عقد قدرة الملوحة — يصف السلوك القائم، لا يخترعه."""

    supported: bool
    model: str
    references: tuple[str, ...]  # مراجع النواة (``file:line``)
    covers: tuple[CapabilityClaim, ...]  # ما يُنمذَج فعلاً + سند كلٍّ
    limits: tuple[str, ...]  # متى يتوقّف عن الثقة (الحدّ الصادق — يمنع fail-open)
    status_enum: tuple[str, ...]  # مفردات الحالة الحقيقيّة (سياسة الريّ)

    def to_dict(self) -> dict:
        return {
            "supported": self.supported,
            "model": self.model,
            "references": list(self.references),
            "covers": [{"claim": c.claim, "ref": c.ref} for c in self.covers],
            "limits": list(self.limits),
            "status_enum": list(self.status_enum),
        }


# ── العقد المُعلَن (يصف السلوك القائم المُثبَت file:line) ──────────────
SALINITY_CAPABILITY = SalinityCapability(
    supported=True,
    model="maas_hoffman_ks + fao56_leaching_eq82",
    references=(
        # النواتان الحقيقيّتان (تأكيد grep 2026-07-18):
        "services/sahool-platform/core/engines/fao56.py:127-135",  # salinity_stress_ks (Eq.81)
        "services/sahool-platform/core/engines/fao56.py:590-597",  # leaching_requirement (Eq.82)
    ),
    covers=(
        CapabilityClaim(
            "Ks لخفض الغلّة/النتح من ملوحة التربة عند توفّر soil_ece (Maas-Hoffman، FAO-56 Eq.81)",
            "services/sahool-platform/core/engines/fao56.py:127-135",
        ),
        CapabilityClaim(
            "متطلّب الغسيل عند توفّر ECw + عتبة المحصول + تصريف مقبول (FAO-56 Eq.82، مسقوف 0.5)",
            "services/sahool-platform/core/engines/fao56.py:590-597",
        ),
        CapabilityClaim(
            "ملاءمة المحصول بوزن EC = 0.35 (رفض صلب فوق تحمّل المحصول)",
            "services/sahool-platform/api/crop_suitability.py:46,105-111",
        ),
        CapabilityClaim(
            "بوّابة توصية العجز: مخاطرة ملوحة عالية ⇒ recommended=False (الفيزياء تتقدّم التوفير)",
            "services/sahool-platform/core/engines/deficit_irrigation.py:81,93-96",
        ),
    ),
    limits=(
        "لا تعديل ملوحة عند غياب soil_ece ⇒ Ks=1.0 (H5 off-by-default) — مُعلَن لا صامت",
        "الغسيل لا يُحسَب دون ملوحة ماء الريّ (ECw)",
        "كسر الغسيل مسقوف عند 0.5 (LR>0.5 يُعلَّم لا يُطبَّق)",
        "لا نمذجة نقل ملح زمنيّ ولا تراكم ملح في منطقة الجذر",
        "بلا قياس EC تربة مُدخَل للحقل ⇒ القدرة خاملة لذلك الحقل (لا تخمين)",
    ),
    status_enum=(
        # مفردات سياسة الريّ الحقيقيّة (irrigation_recommendation_policy.py:14):
        "net_only",  # لا بيانات ملوحة ⇒ صافٍ فقط
        "salinity_adjusted",  # Ks مُطبَّق
        "salinity_with_leaching",  # Ks + غسيل
        "blocked_for_review",  # ملوحة حرجة بلا بيانات غسل ⇒ خبير
    ),
)


def salinity_capability_report() -> dict:
    """العقد المُعلَن + ملاحظة صدق (لأيّ نقطة/تشخيص/تصدير مستقبليّ)."""
    d = SALINITY_CAPABILITY.to_dict()
    d["note_ar"] = (
        "قدرة مقيَّدة مُعلَنة: تعمل عند توفّر بيانات ملوحة التربة/الماء، وتُعلِن صراحةً "
        "متى تتوقّف عن الثقة (limits). عقد بلا حدود = fail-open مقنّع (محروس)."
    )
    return d
