"""اختبار سجلّ دليل المعايرة (#384) — نقيّ حتميّ، تجميع لا تعديل.

يثبت: (أ) عدّ العيّنات (الفارغة لا تُحتسب)؛ (ب) نسبة النجاح من المقاييس المُقيَّمة؛
(ج) إحصاء أعلام النجاح؛ (د) مستوى الدليل (none/expert_opinion/field_preliminary/
field_verified) بعتبة؛ (هـ) آخر تقييم = أحدث طابع؛ (و) calibrated=False. بلا شبكة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.evidence_registry import aggregate_evidence  # noqa: E402


def _outcome(n_eval, n_succ, flags=None, ts=None):
    return {
        "n_evaluated": n_eval,
        "n_success": n_succ,
        "success_flags": flags or [],
        "evaluated_at": ts,
    }


def test_empty_outcomes_none():
    e = aggregate_evidence("jawf", [])
    assert e["sample_count"] == 0
    assert e["evidence_level"] == "none"
    assert e["success_rate"] is None


def test_empty_but_expert_calibrated():
    e = aggregate_evidence("jawf", [], expert_calibrated=True)
    assert e["evidence_level"] == "expert_opinion"


def test_blank_outcomes_not_counted():
    # نتيجة بلا مقياس مُقيَّم لا تُحتسب عيّنة (لا تضخيم دليل).
    e = aggregate_evidence("ibb", [_outcome(0, 0), _outcome(2, 1)])
    assert e["sample_count"] == 1


def test_success_rate_and_flags():
    outs = [
        _outcome(4, 2, ["irrigation_followed", "stress_avoided"]),
        _outcome(2, 2, ["irrigation_followed", "yield_met"]),
    ]
    e = aggregate_evidence("marib", outs)
    assert e["sample_count"] == 2
    assert e["success_rate"] == pytest.approx((2 + 2) / (4 + 2), abs=1e-3)  # 4/6 ≈ 0.667
    assert e["success_flag_counts"]["irrigation_followed"] == 2
    assert e["success_flag_counts"]["yield_met"] == 1


def test_field_preliminary_below_threshold():
    e = aggregate_evidence("tihama", [_outcome(1, 1) for _ in range(5)])
    assert e["evidence_level"] == "field_preliminary"
    assert e["samples_to_verified"] == e["field_verified_min_samples"] - 5
    # The warnings are rendered by clients: collection must not promise approval.
    warnings = " ".join(e["warnings_ar"])
    assert "25 عيّنة لبلوغ عتبة الجمع" in warnings
    assert "لا يمنح اعتماداً زراعياً أو معايرة" in warnings
    assert "عيّنة للتحقّق" not in warnings


def test_threshold_alone_yields_sample_complete_not_field_verified():
    """U01: بلوغُ العتبة اكتمالُ عيّنة لا اعتمادٌ — «مُتحقَّق ميدانيّاً» يشترط مراجعة."""
    n = aggregate_evidence("hadramout", [])["field_verified_min_samples"]
    e = aggregate_evidence("hadramout", [_outcome(1, 1) for _ in range(n)])
    assert e["evidence_level"] == "field_sample_complete"
    assert e["sample_completeness"] == "threshold_reached"
    assert e["review_status"] == "unreviewed"
    assert e["samples_to_verified"] == 0
    assert any("مراجعة مختصّ" in w for w in e["warnings_ar"])


def test_field_verified_requires_threshold_and_review():
    n = aggregate_evidence("hadramout", [])["field_verified_min_samples"]
    e = aggregate_evidence("hadramout", [_outcome(1, 1) for _ in range(n)], reviewed=True)
    assert e["evidence_level"] == "field_verified"
    assert e["review_status"] == "reviewed"
    # المراجعة لا تُعوِّض نقصَ العيّنة.
    few = aggregate_evidence("hadramout", [_outcome(1, 1) for _ in range(3)], reviewed=True)
    assert few["evidence_level"] == "field_preliminary"


@pytest.mark.parametrize("sample_count", [0, 3, 30])
@pytest.mark.parametrize("reviewed", [False, True])
def test_review_warning_matches_review_status(sample_count, reviewed):
    e = aggregate_evidence("jawf", [_outcome(1, 1) for _ in range(sample_count)], reviewed=reviewed)
    warnings = e["warnings_ar"]
    assert e["review_status"] == ("reviewed" if reviewed else "unreviewed")
    assert e["calibrated"] is False
    assert sum("لا يمنح اعتماداً زراعياً أو معايرة" in w for w in warnings) == 1
    assert sum("مراجعة مختصّ" in w for w in warnings) == (0 if reviewed else 1)
    if reviewed:
        assert not any("غير مُعتمَد" in w or "غير مُراجَع" in w for w in warnings)


def test_thirty_rows_from_one_field_and_season_are_not_independent_evidence():
    """التجربة التي كشفت U01: 30 صفّاً للحقل والموسم نفسيهما بنسبة نجاح صفر."""
    rows = [{**_outcome(1, 0), "field_id": "fld_1", "season_id": "ssn_1"} for _ in range(30)]
    e = aggregate_evidence("jawf", rows)
    assert e["evidence_level"] != "field_verified"
    assert e["success_rate"] == 0.0
    assert e["independence"] == {
        "fields": 1,
        "seasons": 1,
        "farms": 0,
        "tenants": 0,
        "unknown_unit_samples": 0,
    }
    assert any("معرّفات الحقول المتاحة: 1، والمواسم: 1" in w for w in e["warnings_ar"])


def test_samples_without_unit_identity_are_declared_not_hidden():
    e = aggregate_evidence("ibb", [_outcome(1, 1) for _ in range(4)])
    assert e["independence"]["unknown_unit_samples"] == 4
    assert any("بلا هويّة" in w for w in e["warnings_ar"])


def test_tenant_identity_does_not_prove_field_and_season_completeness():
    e = aggregate_evidence("jawf", [{**_outcome(1, 1), "tenant_id": "tenant_1"}] * 4)
    assert e["independence"] == {
        "fields": 0,
        "seasons": 0,
        "farms": 0,
        "tenants": 1,
        "unknown_unit_samples": 0,
    }
    warnings = " ".join(e["warnings_ar"])
    assert "معرّفات الحقول المتاحة: 0، والمواسم: 0" in warnings
    assert "الهوية محدودة أو ناقصة" in warnings
    assert "حقلٍ وموسمٍ واحد" not in warnings
    assert "كلّ العيّنات من حقل" not in warnings
    assert e["review_status"] == "unreviewed"


@pytest.mark.parametrize("fields,seasons", [(0, 2), (2, 0), (1, 2), (2, 1), (2, 2)])
def test_identity_warning_checks_field_and_season_dimensions_separately(fields, seasons):
    rows = [
        {
            **_outcome(1, 1),
            "tenant_id": "tenant_1",
            "field_id": f"field_{i % fields}" if fields else None,
            "season_id": f"season_{i % seasons}" if seasons else None,
        }
        for i in range(2)
    ]
    e = aggregate_evidence("jawf", rows)
    assert e["independence"]["fields"] == fields
    assert e["independence"]["seasons"] == seasons
    assert e["independence"]["unknown_unit_samples"] == 0
    identity_warnings = [w for w in e["warnings_ar"] if "معرّفات الحقول المتاحة" in w]
    if fields <= 1 or seasons <= 1:
        assert len(identity_warnings) == 1
        assert f"معرّفات الحقول المتاحة: {fields}، والمواسم: {seasons}" in identity_warnings[0]
    else:
        assert identity_warnings == []


def test_last_evaluated_at_is_max():
    outs = [
        _outcome(1, 1, ts="2026-01-01"),
        _outcome(1, 0, ts="2026-06-19"),
        _outcome(1, 1, ts="2026-03-01"),
    ]
    e = aggregate_evidence("ibb", outs)
    assert e["last_evaluated_at"] == "2026-06-19"


def test_calibrated_false():
    assert aggregate_evidence("jawf", [_outcome(1, 1)])["calibrated"] is False
