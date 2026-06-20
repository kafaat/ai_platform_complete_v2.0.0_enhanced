"""اختبار توحيد نَسَب التنفيذ (Unified Execution Lineage، PR #396) — نقيّ حتميّ.

يثبت: (أ) سَكّ معرّف عالميّ فريد بالبادئة lin_؛ (ب) ensure يُعيد الممرَّر أو يَسُكّ؛
(ج) normalize_ref_type يتحقّق ضمن المجموعة المغلقة ويرفض المجهول؛ (د) lineage_link_row
يُشكّل صفّاً متّسقاً (يُطبّع/يُجرّد) ويرفض ref_id فارغ. بلا شبكة، بلا قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.execution_lineage import (  # noqa: E402
    LINEAGE_PREFIX,
    REF_TYPES,
    ensure_lineage_id,
    lineage_link_row,
    new_lineage_id,
    normalize_ref_type,
)


def test_new_id_unique_with_prefix():
    a, b = new_lineage_id(), new_lineage_id()
    assert a.startswith(LINEAGE_PREFIX) and len(a) > len(LINEAGE_PREFIX)
    assert a != b


def test_ref_types_are_closed_set():
    assert REF_TYPES == ("decision", "dispatch", "command", "execution", "outcome")


def test_ensure_reuses_or_mints():
    assert ensure_lineage_id("lin_keepme") == "lin_keepme"
    assert ensure_lineage_id("  lin_trim  ") == "lin_trim"
    assert ensure_lineage_id(None).startswith(LINEAGE_PREFIX)
    assert ensure_lineage_id("").startswith(LINEAGE_PREFIX)


def test_normalize_ref_type_accepts_and_lowercases():
    assert normalize_ref_type("decision") == "decision"
    assert normalize_ref_type("  DISPATCH  ") == "dispatch"
    assert normalize_ref_type("Command") == "command"


def test_normalize_ref_type_rejects_unknown():
    with pytest.raises(ValueError):
        normalize_ref_type("bogus")
    with pytest.raises(ValueError):
        normalize_ref_type("")


def test_link_row_shapes_and_normalizes():
    row = lineage_link_row("lin_abc", "DISPATCH", "  disp_9 ")
    assert row == {"lineage_id": "lin_abc", "ref_type": "dispatch", "ref_id": "disp_9"}


def test_link_row_mints_lineage_when_absent():
    row = lineage_link_row(None, "decision", "dec_1")
    assert row["lineage_id"].startswith(LINEAGE_PREFIX)
    assert row["ref_type"] == "decision"
    assert row["ref_id"] == "dec_1"


def test_link_row_rejects_empty_ref_id():
    with pytest.raises(ValueError):
        lineage_link_row("lin_1", "decision", "   ")


def test_link_row_rejects_unknown_ref_type():
    with pytest.raises(ValueError):
        lineage_link_row("lin_1", "nonsense", "x1")
