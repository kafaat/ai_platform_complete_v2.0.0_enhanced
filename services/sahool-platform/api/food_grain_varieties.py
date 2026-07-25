"""كتالوج أصناف الحبوب الغذائيّة اليمنيّة — مرجعيّ موثّق المصدر (reference-only).

يُبتلَع سِجِلّ ``SAHOOL-YEMEN-FOOD-GRAINS-SOURCE-VERIFIED-V1`` (29 صنفاً من الدليل الرسميّ
للهيئة العامة للبحوث والإرشاد الزراعيّ — اليمن، 2022) كـ**كتالوج مرجعيّ** فقط.

**بوّابة الحوكمة الحرِجة (reference_only_not_operational):** بيانات الأصناف (كميّة البذور،
التسميد، الماء، …) موثّقةٌ من المصدر لكنّها **محجوبةٌ عن التنفيذ الآليّ** — لا تُغذّي محرّك
القرار مباشرةً. أيّ استخدام قراريّ يمرّ عبر المسار المحكوم (مرشّح → موافقة خبير) كبقيّة
المنصّة (DECISION-CENTER-UNIFY-01). هذه الوحدة **قراءة صرفة**: تُحمّل + تُتحقّق + تُقدّم؛
لا تكتب ولا تُقرّر ولا تُستورَد من محرّك القرار (حارس ساكن يمنع ذلك).

الصدق: لا اختلاق — الحقول الخبيرة (جودة/مقاومة/بيئة) تُحفَظ في ``expert_enrichment`` منفصلةً
ولا تُنسَب للمصدر؛ تحذيرات الجودة (``quality_issues``) جزءٌ من السِجِلّ لا تُحذَف.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# حالة الحوكمة الوحيدة المسموحة لكلّ صنف في هذا الكتالوج (fail-closed على غيرها).
REFERENCE_ONLY_STATUS = "reference_only_not_operational"

_DATASET_PATH = Path(__file__).with_name("food_grain_varieties_verified_v1.json")
_SCHEMA_PATH = Path(__file__).with_name("food_grain_varieties_verified_v1.schema.json")


class VarietyCatalogIntegrityError(RuntimeError):
    """يُرفَع حين يخالف السِجِلّ ثوابت الحوكمة (بوّابة/نَسَب/عدد) — fail-closed لا تقديم صامت."""


@lru_cache(maxsize=1)
def load_food_grain_varieties() -> dict[str, Any]:
    """يُحمّل سِجِلّ الأصناف المرجعيّ ويؤكّد ثوابت الحوكمة قبل تقديمه (مُخزَّن).

    يفشل مُغلَقاً (``VarietyCatalogIntegrityError``) إن:
      * لم يطابق ``record_count`` عدد الأصناف الفعليّ،
      * وُجد صنفٌ حالته ليست ``reference_only_not_operational`` (تسرّب تشغيليّ)،
      * غاب نَسَب المصدر (``source_pages``/``source_verification``) لأيّ صنف،
      * غاب ``source_pdf_sha256`` من الميتاداتا.
    لا يُصلِح المصدر صامتاً؛ فقط يرفض تقديمه إن اختلّت الثوابت.
    """
    data = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    meta = data.get("metadata") or {}
    varieties = data.get("varieties") or []

    declared = meta.get("record_count")
    if declared != len(varieties):
        raise VarietyCatalogIntegrityError(
            f"record_count={declared} لا يطابق عدد الأصناف={len(varieties)}"
        )
    if not meta.get("source_pdf_sha256"):
        raise VarietyCatalogIntegrityError("نَسَب المصدر ناقص: لا source_pdf_sha256")
    for v in varieties:
        if v.get("decision_engine_use_status") != REFERENCE_ONLY_STATUS:
            raise VarietyCatalogIntegrityError(
                f"صنف {v.get('id')} حالته ليست {REFERENCE_ONLY_STATUS} — تسرّب تشغيليّ محظور"
            )
        if not v.get("source_pages") or not v.get("source_verification"):
            raise VarietyCatalogIntegrityError(f"نَسَب المصدر ناقص للصنف {v.get('id')}")
    return data


def catalog_metadata() -> dict[str, Any]:
    """ميتاداتا الكتالوج (المصدر/الإصدار/العدّ) + وسم بوّابة الحوكمة الصريح."""
    meta = dict(load_food_grain_varieties()["metadata"])
    meta["decision_engine_use_status"] = REFERENCE_ONLY_STATUS
    return meta


def list_food_grain_varieties(crop_code: str | None = None) -> list[dict[str, Any]]:
    """كلّ الأصناف المرجعيّة (اختياريّاً مُرشَّحة بـ``crop_code``: wheat/barley/…)."""
    varieties = load_food_grain_varieties()["varieties"]
    if crop_code:
        c = crop_code.strip().lower()
        varieties = [v for v in varieties if str(v.get("crop_code", "")).lower() == c]
    return list(varieties)


def get_food_grain_variety(variety_id: str) -> dict[str, Any] | None:
    """صنفٌ واحد بمعرّفه (``id``)، أو ``None`` إن لم يوجد."""
    vid = (variety_id or "").strip()
    for v in load_food_grain_varieties()["varieties"]:
        if v.get("id") == vid:
            return v
    return None


def quality_issues() -> list[dict[str, Any]]:
    """قضايا الجودة المُسجَّلة على السِجِلّ (شفافيّة — لا تُخفى ولا تُحذَف)."""
    return list(load_food_grain_varieties().get("quality_issues") or [])
