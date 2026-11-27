"""Malformed retrieval metadata cannot break or widen the decision-preview scope."""

from __future__ import annotations

import pytest

from shared.knowledge.georag_evidence import scope_annotations

pytestmark = pytest.mark.unit

FIELD = {
    "type": "Polygon",
    "coordinates": [[[44, 15], [45, 15], [45, 16], [44, 16], [44, 15]]],
}


def _annotation(chunk_id, **overrides):
    return {
        "chunk_id": chunk_id,
        "tenant_id": "tenant-a",
        "verified": False,
        "decision_authority": "none",
        "source_uri": "s3://bucket/doc",
        "source_revision": "r1",
        "content_digest": "digest",
        "spatial_scope": {"field_id": "pivot-1"},
        **overrides,
    }


def _scope(*annotations):
    return scope_annotations(
        list(annotations), tenant_id="tenant-a", field_id="pivot-1", field_geometry=FIELD
    )


@pytest.mark.parametrize("kind", [[], {}, ["Polygon"]])
def test_malformed_geometry_does_not_abort_good_annotation(kind):
    result = _scope(
        _annotation("bad", spatial_scope={"geometry": {"type": kind, "coordinates": []}}),
        _annotation("good"),
    )
    assert [a["chunk_id"] for a in result["annotations"]] == ["good"]
    assert result["rejected"] == [{"chunk_id": "bad", "reason": "annotation_geometry_invalid"}]
    assert result["status"] == "evidence_available"
    assert result["direct_execution_permitted"] is False


@pytest.mark.parametrize("scope", [[], "pivot-2", 42])
def test_global_reference_cannot_downgrade_malformed_scope(scope):
    result = _scope(_annotation("bad", tenant_id="__global__", spatial_scope=scope))
    assert result["annotations"] == []
    assert result["rejected"] == [{"chunk_id": "bad", "reason": "spatial_scope_invalid"}]
    assert result["status"] == "evidence_required"


@pytest.mark.parametrize("key", ["source_uri", "source_revision", "content_digest"])
def test_non_string_provenance_is_not_evidence(key):
    result = _scope(_annotation("bad", **{key: {"unverified": "metadata"}}))
    assert result["annotations"] == []
    assert result["rejected"] == [{"chunk_id": "bad", "reason": "provenance_incomplete"}]
    assert result["status"] == "evidence_required"


def test_unscoped_global_reference_remains_advisory():
    result = _scope(_annotation("global", tenant_id="__global__", spatial_scope=None))
    assert result["annotations"][0]["spatial_match"] == "general_reference"
    assert result["status"] == "evidence_required"


def test_foreign_annotation_still_rejected():
    result = _scope(_annotation("foreign", tenant_id="tenant-b"), _annotation("good"))
    assert [a["chunk_id"] for a in result["annotations"]] == ["good"]
    assert result["rejected"] == [{"chunk_id": "foreign", "reason": "tenant_scope_mismatch"}]
