"""api/decision_lineage.py — نَسَب القرار (Decision Lineage) — المرحلة ١

العمود الفقري للسلسلة القابلة للتدقيق: Decision → Outcome → Evidence → Adaptation.
يُسَكّ `decision_id` موحَّد عند القرار، ويُمرَّر ويُعاد في كلّ خطوة لاحقة — فيُربَط
القياس بالقرار، والدليل بالقياس، والتكيّف بالدليل، بمعرّف واحد قابل للتتبّع.

المرحلة ١ (نَسَب): المعرّف يُمرَّر ويُعاد في الاستجابات (ربط منطقيّ كامل end-to-end).
المرحلة ٢ (تخزين): تُضاف الكتابة الدائمة + أحداث outbox (تتطلّب async session) — مؤجَّلة.

نقيّ حتميّ عدا `new_decision_id` (UUID). `lineage_stage` حتميّة بالكامل (قابلة للاختبار).
"""

from __future__ import annotations

import uuid

# ترتيب مراحل السلسلة — المصدر الموحّد للنَّسَب.
LINEAGE_STAGES: tuple[str, ...] = ("decision", "outcome", "evidence", "adaptation")


def new_decision_id() -> str:
    """يَسُكّ معرّف قرار جديداً (بادئة dec_ + 16 خانة hex)."""
    return "dec_" + uuid.uuid4().hex[:16]


def ensure_decision_id(decision_id: str | None) -> str:
    """يُعيد المعرّف الممرَّر إن وُجد (إعادة استخدام للسلسلة)، وإلّا يَسُكّ جديداً."""
    did = (decision_id or "").strip()
    return did or new_decision_id()


def _parent_of(stage: str) -> str | None:
    """المرحلة الأمّ في السلسلة (None للأولى)."""
    if stage in LINEAGE_STAGES:
        i = LINEAGE_STAGES.index(stage)
        return LINEAGE_STAGES[i - 1] if i > 0 else None
    return None


def lineage_stage(
    decision_id: str,
    stage: str,
    *,
    field_id: str | None = None,
    region: str | None = None,
) -> dict:
    """يُنتج كتلة نَسَب متّسقة لمرحلة في السلسلة — نقيّ حتميّ.

    تربط المرحلة بالقرار (decision_id) وبمرحلتها الأمّ، مع موقعها في السلسلة. صدق:
    مرحلة غير معروفة تُعلَن صراحةً (known=False) لا تُرفَض — لا يُختلق ترتيب.
    """
    known = stage in LINEAGE_STAGES
    out = {
        "decision_id": decision_id,
        "stage": stage,
        "stage_known": known,
        "parent_stage": _parent_of(stage),
        "position": (LINEAGE_STAGES.index(stage) + 1) if known else None,
        "total_stages": len(LINEAGE_STAGES),
        "chain": list(LINEAGE_STAGES),
    }
    if field_id is not None:
        out["field_id"] = field_id
    if region is not None:
        out["region"] = region
    return out
