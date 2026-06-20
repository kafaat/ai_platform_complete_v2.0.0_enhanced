"""اختبار نَسَب القرار (Decision Lineage، المرحلة ١) — نقيّ حتميّ.

يثبت: (أ) سَكّ معرّف فريد بالبادئة؛ (ب) ensure يُعيد الممرَّر أو يَسُكّ؛ (ج) lineage_stage
تربط بالقرار وبالمرحلة الأمّ والموقع؛ (د) السلسلة الموحّدة decision→outcome→evidence→
adaptation؛ (هـ) مرحلة مجهولة معلَّمة لا مرفوضة؛ (و) field_id/region اختياريّان. بلا شبكة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.decision_lineage import (  # noqa: E402
    LINEAGE_STAGES,
    ensure_decision_id,
    lineage_stage,
    new_decision_id,
)


def test_new_id_unique_with_prefix():
    a, b = new_decision_id(), new_decision_id()
    assert a.startswith("dec_") and len(a) > 4
    assert a != b


def test_ensure_reuses_or_mints():
    assert ensure_decision_id("dec_keepme") == "dec_keepme"
    assert ensure_decision_id("  dec_trim  ") == "dec_trim"
    minted = ensure_decision_id(None)
    assert minted.startswith("dec_")
    assert ensure_decision_id("").startswith("dec_")


def test_chain_order_is_canonical():
    assert LINEAGE_STAGES == ("decision", "outcome", "evidence", "adaptation")


def test_lineage_stage_links_parent_and_position():
    s = lineage_stage("dec_1", "outcome", field_id="f1")
    assert s["decision_id"] == "dec_1"
    assert s["stage"] == "outcome"
    assert s["stage_known"] is True
    assert s["parent_stage"] == "decision"
    assert s["position"] == 2
    assert s["total_stages"] == 4
    assert s["field_id"] == "f1"


def test_first_stage_has_no_parent():
    s = lineage_stage("dec_1", "decision")
    assert s["parent_stage"] is None
    assert s["position"] == 1


def test_unknown_stage_flagged_not_rejected():
    s = lineage_stage("dec_1", "bogus")
    assert s["stage_known"] is False
    assert s["position"] is None
    assert s["parent_stage"] is None


def test_optional_meta_absent_when_none():
    s = lineage_stage("dec_1", "evidence", region="jawf")
    assert s["region"] == "jawf"
    assert "field_id" not in s  # لم يُمرَّر ⇒ غائب (لا تلفيق)
