"""تجميعُ دليل مرشَّح التعلّم عبر وحداتٍ مستقلّة متماثلة — نقيّ حتميّ، بلا قاعدة.

حقلٌ-موسمٌ واحد وحدةُ تكرارٍ واحدة، فالحدُّ الأدنى (٣) لا يُبلَغ من إغلاقٍ واحد. يثبت هذا الملفّ أنّ
التجميع عبر مواسم المستأجِر الأخرى المكتملة لنفس المحصول القانونيّ: (أ) يبقى مغلقاً عند وحدةٍ واحدة؛
(ب) يبلغ review_ready بثلاث وحدات متمايزة؛ (ج) لا يعدّ محصولاً آخر ولا مستأجِراً آخر؛ (د) يعدّ تكرارَ
الوحدة مرّة؛ (هـ) تتغيّر البصمةُ بتغيّر المجمّع؛ (و) الاعتمادُ يُسمّي بصمةَ المجمّع نفسها.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.learning_feedback import (  # noqa: E402
    comparable_pool_rows,
    evaluate_season_learning,
    learning_candidate_review_transition,
    resolve_pooling_crop,
)

TENANT = "00000000-0000-0000-0000-000000000001"
OTHER_TENANT = "00000000-0000-0000-0000-000000000002"
KW = dict(tenant_id=TENANT, field_id="fld-1", season_id="ssn-1", minimum_outcomes=3)


def _row(rec, *, farm="farm-1", season="ssn-1", field="fld-1", crop="wheat", tenant=None, act=4.2):
    row = {
        "recommendation_id": rec,
        "predicted_yield_t_ha": 4.0,
        "actual_yield_t_ha": act,
        "accepted": True,
        "matured_within_lag": True,
        "farm_id": farm,
        "season_id": season,
        "field_id": field,
        "crop": crop,
    }
    if tenant is not None:
        row["tenant_id"] = tenant
    return row


def _closing():
    return [_row(f"c{i}") for i in range(3)]


def _pool_unit(farm, season, field, *, n=1, crop="wheat", tenant=TENANT):
    return [
        _row(
            f"{farm}-{season}-{i}", farm=farm, season=season, field=field, crop=crop, tenant=tenant
        )
        for i in range(n)
    ]


def test_one_unit_stays_blocked_with_the_actual_count():
    evaluation = evaluate_season_learning(_closing(), [], **KW)
    assert evaluation["status"] == "blocked"
    assert evaluation["independent_units"] == 1
    assert evaluation["contributing_unit_count"] == 1
    assert "MINIMUM_INDEPENDENT_UNITS_NOT_MET" in evaluation["limitations"]
    assert evaluation["unit_basis"] == "distinct (farm_id, season_id)"
    assert evaluation["pooling_applied"] is True


def test_three_distinct_comparable_units_reach_review_ready_and_are_auditable():
    pool = _pool_unit("farm-2", "ssn-0", "fld-2") + _pool_unit("farm-3", "ssn-1", "fld-3")
    evaluation = evaluate_season_learning(_closing(), pool, **KW)
    assert evaluation["status"] == "review_ready"
    assert evaluation["limitations"] == []
    assert evaluation["independent_units"] == 3
    assert evaluation["pooling_key"] == {
        "tenant_scope": "app.current_tenant",
        "crop_id": "wheat",
        "task": "yield_forecast_calibration",
        "source_table": "recommendation_outcomes",
    }
    assert evaluation["contributing_units"] == [
        {"farm_id": "farm-1", "season_id": "ssn-1", "outcome_count": 3, "closing": True},
        {"farm_id": "farm-2", "season_id": "ssn-0", "outcome_count": 1, "closing": False},
        {"farm_id": "farm-3", "season_id": "ssn-1", "outcome_count": 1, "closing": False},
    ]
    assert evaluation["outcome_count"] == 5
    assert evaluation["closing_unit_outcome_count"] == 3
    assert len(evaluation["source_digests"]) == 5


def test_other_crop_and_other_tenant_are_not_counted():
    pool = (
        _pool_unit("farm-2", "ssn-0", "fld-2", crop="sorghum")
        + _pool_unit("farm-3", "ssn-0", "fld-3", tenant=OTHER_TENANT)
        + [{**_pool_unit("farm-4", "ssn-0", "fld-4")[0], "tenant_id": None}]
    )
    evaluation = evaluate_season_learning(_closing(), pool, **KW)
    assert evaluation["status"] == "blocked"
    assert evaluation["independent_units"] == 1
    assert evaluation["pool_rejected"] == {"crop_mismatch": 1, "tenant_mismatch": 2}
    assert "MINIMUM_INDEPENDENT_UNITS_NOT_MET" in evaluation["limitations"]


def test_arabic_alias_of_the_same_canonical_crop_is_comparable():
    pool = _pool_unit("farm-2", "ssn-0", "fld-2", crop="قمح") + _pool_unit(
        "farm-3", "ssn-0", "fld-3", crop="Wheat"
    )
    evaluation = evaluate_season_learning(_closing(), pool, **KW)
    assert evaluation["independent_units"] == 3
    assert evaluation["status"] == "review_ready"


def test_duplicate_outcomes_of_one_unit_count_once():
    # خمسُ نتائج لوحدةٍ واحدة عبر حقلين + حقلٌ آخر في مزرعة الإغلاق وموسمه = وحدتان لا سبع.
    pool = (
        _pool_unit("farm-2", "ssn-0", "fld-2", n=3)
        + _pool_unit("farm-2", "ssn-0", "fld-9", n=2)
        + _pool_unit("farm-1", "ssn-1", "fld-8", n=2)
    )
    evaluation = evaluate_season_learning(_closing(), pool, **KW)
    assert evaluation["independent_units"] == 2
    assert evaluation["status"] == "blocked"
    assert evaluation["contributing_units"][0] == {
        "farm_id": "farm-1",
        "season_id": "ssn-1",
        "outcome_count": 5,
        "closing": True,
    }


def test_closing_unit_rows_in_the_pool_are_not_recounted():
    kept, rejected = comparable_pool_rows(
        _pool_unit("farm-1", "ssn-1", "fld-1", n=2) + _pool_unit("farm-2", "ssn-0", "fld-2"),
        tenant_id=TENANT,
        crop_id="wheat",
        field_id="fld-1",
        season_id="ssn-1",
    )
    assert [r["farm_id"] for r in kept] == ["farm-2"]
    assert rejected == {"closing_unit_row": 2}


def test_pool_rows_without_season_are_not_attributed_to_the_closing_season():
    row = {**_pool_unit("farm-2", "ssn-0", "fld-2")[0], "season_id": None}
    kept, rejected = comparable_pool_rows(
        [row], tenant_id=TENANT, crop_id="wheat", field_id="fld-1", season_id="ssn-1"
    )
    assert kept == [] and rejected == {"missing_season": 1}


def test_digest_changes_when_the_pool_changes_but_not_when_it_is_reordered():
    a = _pool_unit("farm-2", "ssn-0", "fld-2") + _pool_unit("farm-3", "ssn-0", "fld-3")
    b = _pool_unit("farm-2", "ssn-0", "fld-2") + _pool_unit("farm-4", "ssn-0", "fld-4")
    ev_a = evaluate_season_learning(_closing(), a, **KW)
    ev_a_reordered = evaluate_season_learning(_closing(), list(reversed(a)), **KW)
    ev_b = evaluate_season_learning(_closing(), b, **KW)
    assert ev_a["status"] == ev_b["status"] == "review_ready"
    assert ev_a["pool_digest"] != ev_b["pool_digest"]
    assert ev_a["source_digests"] != ev_b["source_digests"]
    assert ev_a["pool_digest"] == ev_a_reordered["pool_digest"]
    assert ev_a["source_digests"] == ev_a_reordered["source_digests"]


@pytest.mark.parametrize(
    ("crops", "limitation"),
    [
        ([None, None, None], "POOLING_CROP_MISSING"),
        (["خضروات", "خضروات", "خضروات"], "POOLING_CROP_UNRESOLVED"),
        (["wheat", "sorghum", "wheat"], "POOLING_CROP_AMBIGUOUS"),
    ],
)
def test_unresolved_closing_crop_disables_pooling(crops, limitation):
    closing = [{**row, "crop": crop} for row, crop in zip(_closing(), crops, strict=True)]
    assert resolve_pooling_crop(closing) == (None, limitation)
    pool = _pool_unit("farm-2", "ssn-0", "fld-2") + _pool_unit("farm-3", "ssn-0", "fld-3")
    evaluation = evaluate_season_learning(closing, pool, **KW)
    assert evaluation["pooling_applied"] is False
    assert evaluation["independent_units"] == 1
    assert evaluation["status"] == "blocked"
    assert limitation in evaluation["limitations"]


def test_closing_unit_without_an_eligible_outcome_cannot_borrow_a_pool():
    closing = [{**row, "matured_within_lag": False} for row in _closing()]
    pool = _pool_unit("farm-2", "ssn-0", "fld-2") + _pool_unit("farm-3", "ssn-0", "fld-3")
    evaluation = evaluate_season_learning(closing, pool, **KW)
    assert evaluation["pooling_applied"] is False
    assert evaluation["independent_units"] == 0
    assert evaluation["status"] == "blocked"
    assert "POOLING_REQUIRES_ELIGIBLE_CLOSING_OUTCOME" in evaluation["limitations"]


def test_approval_is_bound_to_the_reviewed_pool_digest():
    pool = _pool_unit("farm-2", "ssn-0", "fld-2") + _pool_unit("farm-3", "ssn-0", "fld-3")
    digest = evaluate_season_learning(_closing(), pool, **KW)["pool_digest"]
    with pytest.raises(ValueError, match="REVIEWED_POOL_DIGEST_MISMATCH"):
        learning_candidate_review_transition(
            "review_ready",
            "approved",
            reviewed_by="agronomist-1",
            evidence_pool_digest=digest,
            reviewed_pool_digest="0" * 64,
        )
    ok = learning_candidate_review_transition(
        "review_ready",
        "approved",
        reviewed_by="agronomist-1",
        evidence_pool_digest=digest,
        reviewed_pool_digest=digest,
    )
    assert ok["status"] == "approved"
    # الاعتمادُ ما زال يتطلّب مراجِعاً بشريّاً ومن review_ready وحدها.
    with pytest.raises(ValueError, match="REVIEWER_REQUIRED"):
        learning_candidate_review_transition(
            "review_ready",
            "approved",
            reviewed_by=" ",
            evidence_pool_digest=digest,
            reviewed_pool_digest=digest,
        )
    with pytest.raises(ValueError, match="INVALID_REVIEW_TRANSITION"):
        learning_candidate_review_transition("blocked", "approved", reviewed_by="agronomist-1")
