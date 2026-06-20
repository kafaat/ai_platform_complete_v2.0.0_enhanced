"""api/execution_lineage.py — توحيد نَسَب التنفيذ (Unified Execution Lineage، PR #396).

نظاما قرار متوازيان بمعرّفات مختلفة: `dec_*` (قرارات المحصول، decision_record) و`disp_*`
(dispatch_decisions) + execution_ledger. بدل إعادة تسمية أيّ معرّف قائم (يكسر التاريخ
والمراجع)، يُسَكّ معرّف عالميّ موحّد `lin_*` يُربَط **فوق** المعرّفات القائمة — القديم
يستمر، الجديد يعمل. هذا الملفّ نقيّ حتميّ (عدا سَكّ UUID) فيُختبَر وحدويّاً بلا قاعدة.

  • new_lineage_id(): يَسُكّ معرّفاً عالميّاً (بادئة lin_ + 16 خانة hex).
  • normalize_ref_type(s): يتحقّق أنّ نوع المرجع ضمن المجموعة المغلقة (وإلّا ValueError).
  • lineage_link_row(...): يُشكّل صفّ ربط متّسقاً (نقيّ) لإدامته في lineage_link.
"""

from __future__ import annotations

import uuid

# أنواع المراجع القابلة للربط — المجموعة المغلقة (تطابق CHECK في migration v82).
REF_TYPES: tuple[str, ...] = ("decision", "dispatch", "command", "execution", "outcome")

# بادئة المعرّف العالميّ الموحّد — مميَّزة عن dec_/disp_/led_ القائمة (لا تصادم).
LINEAGE_PREFIX = "lin_"


def new_lineage_id() -> str:
    """يَسُكّ معرّف نَسَب عالميّاً جديداً (بادئة lin_ + 16 خانة hex)."""
    return LINEAGE_PREFIX + uuid.uuid4().hex[:16]


def ensure_lineage_id(lineage_id: str | None) -> str:
    """يُعيد المعرّف الممرَّر إن وُجد (إعادة استخدام للسلسلة)، وإلّا يَسُكّ جديداً.

    صدق: لا يُلفّق بادئة على معرّف ممرَّر — يُحترَم كما هو (قد يربط الداعي معرّفاً قائماً).
    """
    lin = (lineage_id or "").strip()
    return lin or new_lineage_id()


def normalize_ref_type(ref_type: str) -> str:
    """يُطبّع نوع المرجع ويتحقّق أنّه ضمن المجموعة المغلقة — وإلّا ValueError (fail-closed).

    لا اختراع: نوع مجهول يُرفَض صراحةً بدل ربط صامت لمرجع غير معروف.
    """
    rt = (ref_type or "").strip().lower()
    if rt not in REF_TYPES:
        raise ValueError(f"نوع مرجع غير معروف: {ref_type!r} (المسموح: {', '.join(REF_TYPES)})")
    return rt


def lineage_link_row(
    lineage_id: str,
    ref_type: str,
    ref_id: str,
) -> dict:
    """يُشكّل صفّ ربط نَسَب متّسقاً — نقيّ حتميّ، قابل للاختبار وحدويّاً.

    يُطبّع ref_type (fail-closed على المجهول) ويُجرّد ref_id، فيُنتِج dict جاهزاً للإدامة
    في lineage_link. صدق: ref_id فارغ يُرفَض (لا ربط لمرجع بلا هويّة).
    """
    rid = (ref_id or "").strip()
    if not rid:
        raise ValueError("معرّف المرجع (ref_id) مطلوب — لا ربط لمرجع بلا هويّة.")
    return {
        "lineage_id": ensure_lineage_id(lineage_id),
        "ref_type": normalize_ref_type(ref_type),
        "ref_id": rid,
    }
