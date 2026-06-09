"""
api/chemical_safety.py — حاجز سلامة المدخلات الكيميائيّة

مُكيَّف من عمل v9 سابق (guardrails_engine/tiers/chemical_tier) بعد مراجعته:
المنطق سلامة محضة (فحص/تحذير، لا أتمتة تطبيق) — يتوافق تماماً مع مبدأ
"السلامة لا تُتجاوز أبداً". سدّ فجوة حقيقيّة: لم يكن عندنا فحص للمواد المحظورة.

يتحقّق من:
  • المواد المحظورة دوليّاً (استكهولم/مونتريال/EU/EPA) → BLOCKED قطعيّ
  • الجرعة القصوى الآمنة لكلّ مادّة (kg مادّة فعّالة/هكتار)
  • فترات إعادة الدخول والمناطق العازلة (تُعرَض للمزارع)

المبدأ: human-in-the-loop — يفحص ويحذّر ويحجب، لا يطبّق آليّاً. القرار للمزارع/
المهندس بعد رؤية التحذير.

⚠ القوائم من مصادر دوليّة (اتفاقيّة استكهولم، بروتوكول مونتريال). الجرعات
القصوى قيم مرجعيّة — تحتاج مطابقة مع التسجيل المحلّي اليمني قبل الإنتاج.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChemicalStatus(str, Enum):
    OK = "ok"  # ضمن الحدود الآمنة
    BLOCKED = "blocked"  # محظور دوليّاً — لا يُستخدم
    WARNING = "warning"  # مقيّد أو تجاوز الجرعة — يحتاج مراجعة


# المواد المحظورة/المقيّدة دوليّاً (اتفاقيّة استكهولم + مونتريال + EU + EPA)
# ⚠ مصادر دوليّة موثّقة — تحتاج مطابقة مع التسجيل المحلّي اليمني
_BANNED_CHEMICALS: dict[str, dict] = {
    "methyl_bromide": {"reason_ar": "محظور بموجب بروتوكول مونتريال", "severity": "CRITICAL"},
    "ddt": {"reason_ar": "محظور بموجب اتفاقية استكهولم", "severity": "CRITICAL"},
    "aldrin": {"reason_ar": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
    "chlordane": {"reason_ar": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
    "dieldrin": {"reason_ar": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
    "endrin": {"reason_ar": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
    "heptachlor": {"reason_ar": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
    "mirex": {"reason_ar": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
    "toxaphene": {"reason_ar": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
    "lindane": {"reason_ar": "محظور في الاتحاد الأوروبي", "severity": "CRITICAL"},
    "paraquat": {"reason_ar": "محظور في 53 دولة — سُمّيّة عالية", "severity": "CRITICAL"},
    "endosulfan": {"reason_ar": "محظور بموجب اتفاقية استكهولم", "severity": "CRITICAL"},
    "atrazine": {"reason_ar": "مقيّد — تلوّث المياه الجوفيّة", "severity": "HIGH"},
    "glyphosate": {"reason_ar": "مقيّد — IARC مجموعة 2A محتمل مسرطن", "severity": "MEDIUM"},
}

# الجرعة القصوى الآمنة (kg مادّة فعّالة/هكتار) + قيود التطبيق
# ⚠ قيم مرجعيّة دوليّة — تحتاج معايرة محلّيّة
_MAX_DOSAGES: dict[str, dict] = {
    "glyphosate": {"max_kg_ha": 2.0, "buffer_zone_m": 5, "reentry_hours": 4},
    "copper_sulfate": {"max_kg_ha": 3.0, "buffer_zone_m": 10, "reentry_hours": 24},
    "sulfur": {"max_kg_ha": 5.0, "buffer_zone_m": 5, "reentry_hours": 12},
}


@dataclass
class ChemicalCheck:
    status: ChemicalStatus
    status_ar: str
    chemical: str
    message_ar: str
    severity: str | None = None
    max_kg_ha: float | None = None
    buffer_zone_m: int | None = None
    reentry_hours: int | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "status_ar": self.status_ar,
            "chemical": self.chemical,
            "message_ar": self.message_ar,
            "severity": self.severity,
            "max_kg_ha": self.max_kg_ha,
            "buffer_zone_m": self.buffer_zone_m,
            "reentry_hours": self.reentry_hours,
        }


_STATUS_AR = {
    ChemicalStatus.OK: "ضمن الحدود الآمنة",
    ChemicalStatus.BLOCKED: "محظور — لا يُستخدم",
    ChemicalStatus.WARNING: "يحتاج مراجعة",
}


def check_chemical(
    chemical: str,
    dose_kg_ha: float | None = None,
) -> ChemicalCheck:
    """يفحص مادّة كيميائيّة ضدّ الحظر الدولي والجرعة القصوى.

    Args:
        chemical: اسم المادّة (إنجليزي، lowercase).
        dose_kg_ha: الجرعة المقترحة (kg مادّة فعّالة/هكتار) — اختياري.
    """
    key = chemical.strip().lower().replace(" ", "_")

    # ١. الحظر الدولي (أولويّة قصوى — سلامة لا تُتجاوز)
    if key in _BANNED_CHEMICALS:
        info = _BANNED_CHEMICALS[key]
        sev = info["severity"]
        # CRITICAL/HIGH → محجوب؛ MEDIUM → تحذير شديد
        status = ChemicalStatus.BLOCKED if sev in ("CRITICAL", "HIGH") else ChemicalStatus.WARNING
        return ChemicalCheck(
            status=status,
            status_ar=_STATUS_AR[status],
            chemical=chemical,
            message_ar=f"{info['reason_ar']}. {'لا تستخدمه.' if status == ChemicalStatus.BLOCKED else 'استخدامه يحتاج مبرّراً ومراجعة.'}",
            severity=sev,
        )

    # ٢. فحص الجرعة القصوى (إن عُرفت المادّة والجرعة)
    if key in _MAX_DOSAGES:
        limits = _MAX_DOSAGES[key]
        if dose_kg_ha is not None and dose_kg_ha > limits["max_kg_ha"]:
            return ChemicalCheck(
                status=ChemicalStatus.WARNING,
                status_ar=_STATUS_AR[ChemicalStatus.WARNING],
                chemical=chemical,
                message_ar=(
                    f"الجرعة {dose_kg_ha} kg/ha تتجاوز الحدّ الآمن "
                    f"({limits['max_kg_ha']} kg/ha). راجع قبل التطبيق."
                ),
                max_kg_ha=limits["max_kg_ha"],
                buffer_zone_m=limits["buffer_zone_m"],
                reentry_hours=limits["reentry_hours"],
            )
        # ضمن الحدّ
        return ChemicalCheck(
            status=ChemicalStatus.OK,
            status_ar=_STATUS_AR[ChemicalStatus.OK],
            chemical=chemical,
            message_ar=(
                f"ضمن الحدّ الآمن. احترم المنطقة العازلة {limits['buffer_zone_m']}م "
                f"وفترة إعادة الدخول {limits['reentry_hours']} ساعة."
            ),
            max_kg_ha=limits["max_kg_ha"],
            buffer_zone_m=limits["buffer_zone_m"],
            reentry_hours=limits["reentry_hours"],
        )

    # ٣. مادّة غير معروفة في قوائمنا → تحذير محايد (لا نؤكّد سلامتها)
    return ChemicalCheck(
        status=ChemicalStatus.WARNING,
        status_ar=_STATUS_AR[ChemicalStatus.WARNING],
        chemical=chemical,
        message_ar=(
            "هذه المادّة غير موجودة في قوائم السلامة لدينا — لا نؤكّد سلامتها. "
            "تحقّق من تسجيلها محلّيّاً قبل الاستخدام."
        ),
    )


def list_banned() -> dict:
    """يُرجع قائمة المواد المحظورة/المقيّدة (للعرض والشفافيّة)."""
    return {
        "source_ar": "اتفاقيّة استكهولم، بروتوكول مونتريال، EU، EPA",
        "disclaimer_ar": (
            "قوائم دوليّة مرجعيّة — تحتاج مطابقة مع التسجيل المحلّي اليمني قبل "
            "الإنتاج. الفحص فحص/تحذير، والقرار النهائي للمزارع/المهندس."
        ),
        "count": len(_BANNED_CHEMICALS),
        "chemicals": [
            {"name": k, "reason_ar": v["reason_ar"], "severity": v["severity"]}
            for k, v in _BANNED_CHEMICALS.items()
        ],
    }
