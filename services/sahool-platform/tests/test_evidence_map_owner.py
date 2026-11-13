import api.main  # noqa: F401
import api.routers.evidence_map as router
import pytest
from fastapi import HTTPException

TENANT = "my-tenant"


def _reply(defect=None):
    counts = {"p": {"decisions": 3, "outcomes": 2, "successes": 1}}
    reply = {"counts": counts, "tenant_id": TENANT, "authoritative": True}
    if defect == "wrong_tenant":
        reply["tenant_id"] = "another-tenant"
    elif defect == "missing_field":
        counts.clear()
    elif defect == "negative":
        counts["p"]["decisions"] = -1
    elif defect == "mirror":
        reply["authoritative"] = False
    elif defect == "too_many_successes":
        counts["p"]["successes"] = 3
    return reply


@pytest.mark.parametrize(
    "defect", ["wrong_tenant", "missing_field", "negative", "mirror", "too_many_successes"]
)
def test_owner_failure_cannot_be_displayed_as_an_empty_or_verified_field(defect):
    fields = [{"field_id": "p"}]
    with pytest.raises(HTTPException) as exc:
        router._apply_owner_counts(fields, _reply(defect), TENANT)
    assert exc.value.status_code == 502
    assert fields == [{"field_id": "p"}]


def test_authoritative_owner_counts_are_copied_onto_the_field():
    fields = [{"field_id": "p"}]
    router._apply_owner_counts(fields, _reply(), TENANT)
    assert fields == [
        {"field_id": "p", "decisions": 3, "outcomes": 2, "successes": 1, "last_outcome_at": None}
    ]
