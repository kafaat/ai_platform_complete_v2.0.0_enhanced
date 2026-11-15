"""Source-binding regressions at the persisted decision boundary (real PostgreSQL)."""

from datetime import timedelta
from uuid import uuid4

import pytest
from test_ac1_agronomic_context import TENANT, _compose_payload, _now, _run
from test_agronomic_lineage_integrity import _decision, _veg_payload, pytestmark_pg
from test_soil_profile_context_gate import _soil


@pytestmark_pg
def test_context_rejects_foreign_or_unavailable_soil(monkeypatch):
    from persistence import compose_agronomic_context

    monkeypatch.setenv("DECISION_REQUIRE_SOIL_PROFILE", "true")
    now = _now()
    payload = _compose_payload("pivot", uuid4().hex, now=now)
    payload.context["soil"] = dict(
        _soil(),
        field_id="east",
        tenant_id=str(uuid4()),
        data_available_at=(now + timedelta(days=1)).isoformat(),
    )
    response = _run(compose_agronomic_context(tenant_id=TENANT, created_by="qa", payload=payload))
    assert response["status"] == "rejected"
    assert {v["code"] for v in response["violations"]} >= {
        "soil_field_mismatch",
        "soil_tenant_mismatch",
        "soil_profile_after_cutoff",
    }


@pytestmark_pg
def test_unrelated_manifests_and_unavailable_images_are_refused():
    from persistence import (
        compose_agronomic_context,
        persist_decision_record,
        persist_vegetation_snapshot,
    )

    field = "f_" + uuid4().hex
    now = _now()
    a = _compose_payload(field, uuid4().hex, now=now)
    b = _compose_payload(field, uuid4().hex, now=now)
    b.context["irrigation"]["type"] = "rainfed"
    b.features[0].value = 0.12

    def compose(payload, tenant=TENANT):
        return _run(compose_agronomic_context(tenant_id=tenant, created_by="qa", payload=payload))

    A, B = compose(a), compose(b)

    def write(context, image=None):
        payload = _decision(field, context, image, context["feature_manifest_hash"])
        return _run(
            persist_decision_record(
                tenant_id=TENANT, payload=payload, decision_id="dc_" + uuid4().hex
            )
        )

    mixed = {
        **A,
        "feature_manifest_id": B["feature_manifest_id"],
        "feature_manifest_hash": B["feature_manifest_hash"],
    }
    assert write(mixed)["reason"] == "context_composition_mismatch"
    # A genuine combination of reused components must still have its own receipt.
    c = a.model_copy(deep=True)
    c.features = b.features
    c.idempotency_key = uuid4().hex
    C = compose(c)
    assert C["snapshot_id"] == A["snapshot_id"]
    assert C["feature_manifest_id"] == B["feature_manifest_id"]
    assert write(C)["decision_id"]
    assert compose(c)["replay"]
    assert compose(c, str(uuid4()))["snapshot_id"] != C["snapshot_id"]
    for future in (True, False):
        v = _veg_payload(field, uuid4().hex + uuid4().hex)
        if future:
            v.data_available_at = now + timedelta(days=1)
        else:
            v.quality_gate = {"executable": False}
        V = _run(
            persist_vegetation_snapshot(
                tenant_id=TENANT, payload=v, snapshot_id="veg_" + uuid4().hex
            )
        )
        assert write(C, V["snapshot_id"])["reason"] == (
            "vegetation_unavailable_at_cutoff" if future else "vegetation_not_executable"
        )
