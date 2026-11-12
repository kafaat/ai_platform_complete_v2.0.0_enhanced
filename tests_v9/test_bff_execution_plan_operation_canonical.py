"""The platform BFF and decision-service agree on the spelling of operation_type.

decision-service normalises operation_type (strip + lowercase) before binding a plan
to its approved irrigation decision. The BFF branched on the raw value, so
" manual_irrigation " became a validated canonical plan downstream while the BFF
skipped its manual-irrigation checks and source. DECISION-MANUAL-PLAN-PADDED-OPERATION-BYPASS-01.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services", "sahool-platform")


@pytest.fixture(scope="module")
def request_model():
    added = CORE not in sys.path
    if added:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    try:
        from api.routers.decision_review import ExecutionPlanRequest
    finally:
        if added:
            sys.path.remove(CORE)
    return ExecutionPlanRequest


@pytest.mark.parametrize(
    "raw",
    ["manual_irrigation", " manual_irrigation ", "Manual_Irrigation", "\tMANUAL_IRRIGATION\n"],
)
def test_padded_or_case_variant_reaches_the_manual_branch(request_model, raw):
    req = request_model(
        review_id="r1",
        candidate_lineage_id="c1",
        operation_type=raw,
        idempotency_key="k1",
    )
    assert req.operation_type == "manual_irrigation"


def test_other_operations_keep_their_name(request_model):
    req = request_model(
        review_id="r1", candidate_lineage_id="c1", operation_type=" Scouting ", idempotency_key="k1"
    )
    assert req.operation_type == "scouting"
