"""v26 workstream 06: both SOR modes reconcile outcome labels against the sealed recommendation.

Pre-cutover the platform writes; after cutover decision-service is the only writer. In both, a
client predicted_yield_t_ha that contradicts the stored recommendation is refused (422) by the
same reconciler, and after cutover an unverified label is never forwarded as authoritative.
"""

from pathlib import Path

import pytest
from core.outcome_reconciler import (
    OutcomeLabelConflict,
    authoritative_outcome_label_refusal,
    reconcile_recommendation_outcome_labels,
)

ROUTER = Path(__file__).resolve().parents[1] / "api/routers/recommendations.py"
SEALED = {"field_id": "f1", "crop": "wheat", "recommendation": {"predicted_yield_t_ha": 3.2}}


def _labels(stored, predicted=None, matured=False, actual=None, crop="wheat"):
    return reconcile_recommendation_outcome_labels(
        stored=stored,
        client_predicted=predicted,
        client_matured=matured,
        actual=actual,
        crop=crop,
        field_id="f1",
    )


@pytest.mark.unit
def test_contradicting_prediction_is_refused_by_the_shared_reconciler():
    with pytest.raises(OutcomeLabelConflict) as exc:
        _labels(SEALED, predicted=9.9)
    assert exc.value.detail["code"] == "predicted_yield_mismatch"


@pytest.mark.unit
def test_sealed_prediction_is_authoritative_and_accepted():
    labels = _labels(SEALED, predicted=3.2)
    assert labels["prediction_source"] == "stored_recommendation"
    assert authoritative_outcome_label_refusal(labels) is None
    absent = _labels(SEALED)  # filled from the sealed recommendation
    assert (
        absent["predicted_yield_t_ha"] == 3.2
        and authoritative_outcome_label_refusal(absent) is None
    )


@pytest.mark.unit
def test_unverified_labels_are_not_authoritative_after_cutover():
    assert authoritative_outcome_label_refusal(_labels(None, predicted=4.0)) == (
        "unverified_predicted_yield_not_authoritative"
    )
    # Maturity claimed for a crop without a lag window cannot be derived from timestamps.
    claimed = _labels({**SEALED, "crop": "qat"}, matured=True, actual=1.0, crop="qat")
    assert claimed["maturity_source"] == "client_unverified"
    assert authoritative_outcome_label_refusal(claimed) == "unverified_maturity_not_authoritative"
    # "Not matured" promotes nothing, so it is not refused.
    pending = _labels({**SEALED, "crop": "qat"}, crop="qat")
    assert authoritative_outcome_label_refusal(pending) is None


def _branches() -> tuple[str, str]:
    text = ROUTER.read_text(encoding="utf-8")
    body = text[text.index('@router.post("/api/v1/recommendations/outcomes"') :]
    cut = body.index("if mode.strict_decision_service_required:")
    pre = body.index("# Pre-cutover bridge:")
    return body[cut:pre], body[pre:]


@pytest.mark.unit
def test_both_branches_reconcile_before_their_write():
    cutover, legacy = _branches()
    assert cutover.index("await _cutover_outcome_labels(user, req)") < cutover.index(
        "await _mirror_recommendation_outcome_to_service("
    )
    assert 'service_payload["metadata"].update(labels)' in cutover
    text = ROUTER.read_text(encoding="utf-8")
    helper = text[text.index("async def _cutover_outcome_labels(") :]
    helper = helper[: helper.index("\n\n\n")]
    assert helper.index("await _server_outcome_labels(") < helper.index(
        "authoritative_outcome_label_refusal(labels)"
    )
    assert legacy.index("await _server_outcome_labels(conn, req)") < legacy.index(
        "INSERT INTO recommendation_outcomes"
    )
