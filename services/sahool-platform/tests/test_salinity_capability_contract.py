"""حارس عقد قدرة الملوحة (WATER-SALT-01 / A5) + برهان سلبيّ.

يفرض القيد الحاكم: **عقد قدرة يُعلِن ``supported: true`` يجب أن يحمل حدوداً غير فارغة
(``limits``) + مفردات حالة (``status_enum``) + مراجع (``references``)، وكلّ ادّعاء
``covers`` مقروناً بمرجع ``file:line`` صالح.** عقد بلا حدود = fail-open مقنّع ⇒ فشل
الحارس. فحص تعاقُد على الكائن الصرف — لا قاعدة/خدمات.
"""

from __future__ import annotations

import re

import pytest
from core.salinity_capability import (
    SALINITY_CAPABILITY,
    CapabilityClaim,
    SalinityCapability,
    salinity_capability_report,
)

pytestmark = pytest.mark.unit

# مرجع صالح: ``path/to/file.py:line`` مع مدى/قائمة أسطر اختياريّة (12، 12-20، 12,30).
_REF = re.compile(r"^[\w./-]+\.py:\d+(?:[-,]\d+)*$")


def test_supported_capability_declares_nonempty_limits() -> None:
    """قدرة مدعومة بلا حدود = fail-open مقنّع — ممنوع بنيويّاً."""
    cap = SALINITY_CAPABILITY
    assert cap.supported is True
    assert cap.limits, "عقد supported:true بلا limits = fail-open مقنّع"
    assert all(isinstance(x, str) and x.strip() for x in cap.limits)


def test_declares_status_enum_matching_real_policy_vocabulary() -> None:
    """مفردات الحالة = مفردات سياسة الريّ الحقيقيّة (لا enum موازٍ مخترَع)."""
    assert set(SALINITY_CAPABILITY.status_enum) == {
        "net_only",
        "salinity_adjusted",
        "salinity_with_leaching",
        "blocked_for_review",
    }


def test_every_covers_claim_has_a_valid_file_line_reference() -> None:
    """لا قدرة مزعومة بلا سند: كلّ ادّعاء covers له مرجع file:line صالح."""
    assert SALINITY_CAPABILITY.covers, "covers لا يجوز أن يكون فارغاً لقدرة مدعومة"
    for c in SALINITY_CAPABILITY.covers:
        assert isinstance(c, CapabilityClaim)
        assert c.claim.strip(), "ادّعاء فارغ"
        assert _REF.match(c.ref), f"مرجع covers غير صالح: {c.ref!r}"


def test_core_references_present_and_valid() -> None:
    assert SALINITY_CAPABILITY.references, "قدرة مدعومة بلا مراجع نواة = ادّعاء بلا سند"
    for r in SALINITY_CAPABILITY.references:
        assert _REF.match(r), f"مرجع نواة غير صالح: {r!r}"


def test_report_carries_honesty_note_and_limits() -> None:
    rep = salinity_capability_report()
    assert rep["supported"] is True
    assert rep["limits"], "التقرير يجب أن يحمل الحدود (لا قدرة بلا حدّ)"
    assert rep["status_enum"]
    assert "note_ar" in rep and rep["note_ar"].strip()


# ── برهان سلبيّ: منطق الحارس نفسه يرفض عقداً بلا حدود ────────────────
def _guard_rejects_fail_open(cap: SalinityCapability) -> bool:
    """يحاكي شرط الحارس: يرفض قدرة مدعومة تفتقد الحدود/الحالة/المراجع."""
    if not cap.supported:
        return False  # قدرة غير مدعومة لا تحتاج حدوداً
    return not (cap.limits and cap.status_enum and cap.references)


def test_negative_proof_fail_open_capability_is_rejected() -> None:
    """عقد supported:true بلا حدود — يجب أن يرفضه منطق الحارس؛ والعقد الحقيقيّ يُقبَل."""
    fail_open = SalinityCapability(
        supported=True,
        model="x",
        references=(),
        covers=(),
        limits=(),  # ← الحدّ غائب = fail-open مقنّع
        status_enum=(),
    )
    assert _guard_rejects_fail_open(fail_open) is True
    assert _guard_rejects_fail_open(SALINITY_CAPABILITY) is False
