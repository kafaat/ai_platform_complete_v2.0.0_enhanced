"""P2 (bounded) GeoRAG + unified-decision integration.

Pins: spatial scoping of retrieved annotations by tenant / field / geometry, provenance
required, fail closed on missing evidence, no execution authority, additive decision block,
and a real HTTP round trip through the retrieval annotation contract. No PG surface exists
in this slice (annotations are not persisted), so no live-PG test is claimed.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.unified_decision import unified_decision  # noqa: E402
from core.rag.production_qdrant import KnowledgeChunk, RetrievedAnnotation  # noqa: E402

from shared.knowledge.georag_evidence import (  # noqa: E402
    fetch_annotations,
    scope_annotations,
)

T = "tenant-a"
FIELD = {
    "type": "Polygon",
    "coordinates": [[[44.0, 15.0], [44.01, 15.0], [44.01, 15.01], [44.0, 15.01], [44.0, 15.0]]],
}
INSIDE = {
    "type": "Polygon",
    "coordinates": [
        [[44.002, 15.002], [44.004, 15.002], [44.004, 15.004], [44.002, 15.004], [44.002, 15.002]]
    ],
}
FAR = {
    "type": "Polygon",
    "coordinates": [[[45.0, 16.0], [45.01, 16.0], [45.01, 16.01], [45.0, 16.01], [45.0, 16.0]]],
}


def _ann(cid="c1", *, tenant=T, scope=None, source_class="tenant_document", **over):
    a = {
        "type": "rag_annotation",
        "verified": False,
        "decision_authority": "none",
        "chunk_id": cid,
        "document_id": "d1",
        "tenant_id": tenant,
        "source_class": source_class,
        "source_uri": "s3://x/d1",
        "source_revision": "r1",
        "content_digest": "abc",
        "text": "t",
        "spatial_scope": scope,
    }
    a.update(over)
    return a


def _scope(anns, geom=FIELD, field_id="f1", tenant=T):
    return scope_annotations(
        anns, tenant_id=tenant, field_id=field_id, field_geometry=geom, zone_id=None
    )


def test_intersecting_geometry_admitted():
    r = _scope([_ann(scope={"geometry": INSIDE})])
    assert r["status"] == "evidence_available"
    assert [a["chunk_id"] for a in r["annotations"]] == ["c1"]
    assert r["direct_execution_permitted"] is False and r["decision_authority"] == "none"


def test_disjoint_geometry_rejected_and_fails_closed():
    r = _scope([_ann(scope={"geometry": FAR})])
    assert r["annotations"] == [] and r["status"] == "evidence_required"
    assert "geometry_disjoint" in r["rejected"][0]["reason"]


def test_other_field_id_rejected():
    r = _scope([_ann(scope={"field_id": "f2"})])
    assert r["annotations"] == [] and r["rejected"][0]["reason"] == "field_scope_mismatch"


def test_field_id_match_admitted():
    assert _scope([_ann(scope={"field_id": "f1"})])["annotations"]


def test_cross_tenant_rejected():
    r = _scope([_ann(tenant="tenant-b", scope={"field_id": "f1"})])
    assert r["annotations"] == [] and r["rejected"][0]["reason"] == "tenant_scope_mismatch"


def test_tenant_doc_without_spatial_scope_rejected():
    r = _scope([_ann(scope=None)])
    assert r["annotations"] == [] and r["rejected"][0]["reason"] == "spatial_scope_missing"


def test_global_reference_admitted_as_non_spatial():
    r = _scope([_ann(tenant="__global__", source_class="official_reference", publisher="p")])
    assert r["annotations"][0]["spatial_match"] == "general_reference"


@pytest.mark.parametrize("missing", ["source_uri", "source_revision", "content_digest"])
def test_missing_provenance_rejected(missing):
    r = _scope([_ann(scope={"field_id": "f1"}, **{missing: ""})])
    assert r["annotations"] == [] and r["rejected"][0]["reason"] == "provenance_incomplete"


def test_authority_claims_rejected():
    for over in ({"decision_authority": "approve"}, {"verified": True}):
        r = _scope([_ann(scope={"field_id": "f1"}, **over)])
        assert (
            r["annotations"] == [] and r["rejected"][0]["reason"] == "annotation_claims_authority"
        )


@pytest.mark.parametrize(
    "geom",
    [
        None,
        {"type": "Point", "coordinates": [0, 0]},
        {"type": "Polygon", "coordinates": []},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]]},
    ],
)
def test_invalid_field_geometry_fails_closed_for_geometry_scoped(geom):
    r = _scope([_ann(scope={"geometry": INSIDE})], geom=geom)
    assert r["annotations"] == [] and "field_geometry_invalid" in r["reason_codes"]


def test_no_annotations_is_evidence_required():
    r = _scope([])
    assert r["status"] == "evidence_required" and "no_annotations" in r["reason_codes"]


def test_nan_geometry_rejected():
    bad = {
        "type": "Polygon",
        "coordinates": [[[float("nan"), 0], [1, 0], [1, 1], [float("nan"), 0]]],
    }
    r = _scope([_ann(scope={"geometry": bad})])
    assert r["annotations"] == []


def test_digest_deterministic():
    a = _scope([_ann(scope={"geometry": INSIDE})])
    b = _scope([_ann(scope={"geometry": INSIDE})])
    assert a["evidence_digest"] == b["evidence_digest"]


# ── decision integration ──────────────────────────────────────────────────
def _twin():
    return {
        "crop": "wheat",
        "crop_known": True,
        "phenology": {},
        "water": {"needs_irrigation": False},
        "nutrient": {"target_uptake_kg_ha": 0.0},
    }


def _decide(**kw):
    return unified_decision(_twin(), {"days": []}, {"confidence": "low"}, **kw)


def test_decision_without_georag_fails_closed():
    d = _decide()
    g = d["georag_evidence"]
    assert g["status"] == "evidence_required" and "georag_not_supplied" in g["reason_codes"]
    assert d["decision_scope"]["georag_grounded"] is False
    assert d["decision_scope"]["direct_execution_permitted"] is False


def test_decision_with_georag_carries_scope_and_no_authority():
    ev = scope_annotations(
        [_ann(scope={"geometry": INSIDE})],
        tenant_id=T,
        field_id="f1",
        field_geometry=FIELD,
        zone_id="z1",
    )
    d = _decide(georag_evidence=ev, field_geometry=FIELD, zone_id="z1", tenant_id=T, field_id="f1")
    assert d["georag_evidence"]["status"] == "evidence_available"
    s = d["decision_scope"]
    assert s["georag_grounded"] is True and s["zone_id"] == "z1" and s["geometry_digest"]
    assert s["direct_execution_permitted"] is False


def test_forged_georag_envelope_is_not_trusted():
    forged = {"status": "evidence_available", "annotations": [_ann()], "evidence_digest": "x"}
    d = _decide(georag_evidence=forged)
    assert d["georag_evidence"]["status"] == "evidence_required"
    assert "georag_envelope_invalid" in d["georag_evidence"]["reason_codes"]


# ── real HTTP round trip with the real annotation contract ────────────────
def _real_annotation():
    chunk = KnowledgeChunk(
        chunk_id="k1",
        tenant_id=T,
        text="wheat salinity note",
        source_type="tenant_document",
        document_id="d9",
        chunk_index=0,
        total_chunks=1,
        metadata={
            "evidence_level": "document",
            "source_class": "tenant_document",
            "source_uri": "s3://b/d9",
            "source_revision": "r2",
            "spatial_scope": {"geometry": INSIDE},
        },
    )
    return RetrievedAnnotation(chunk, 0.5, 0.5, 0.1).as_annotation()


class _H(BaseHTTPRequestHandler):
    seen: dict = {}

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _H.seen = {"body": body, "path": self.path, "auth": self.headers.get("X-Tenant-ID")}
        if body.get("query") == "boom":
            self.send_response(503)
            self.end_headers()
            return
        payload = json.dumps({"annotations": [_real_annotation()]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    s = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


def test_http_round_trip_into_decision(server):
    anns, err = fetch_annotations(
        server, tenant_id=T, field_id="f1", query="salinity", crop="wheat", timeout_s=3
    )
    assert err is None and _H.seen["path"] == "/v1/search"
    assert _H.seen["body"]["tenant_id"] == T and _H.seen["body"]["field_id"] == "f1"
    ev = scope_annotations(anns, tenant_id=T, field_id="f1", field_geometry=FIELD, zone_id=None)
    d = _decide(georag_evidence=ev, field_geometry=FIELD, tenant_id=T, field_id="f1")
    assert d["decision_scope"]["georag_grounded"] is True
    assert d["georag_evidence"]["annotations"][0]["chunk_id"] == "k1"


def test_http_failure_fails_closed(server):
    anns, err = fetch_annotations(server, tenant_id=T, field_id="f1", query="boom", timeout_s=3)
    assert anns == [] and err == "georag_retrieval_unavailable"
    ev = scope_annotations(
        anns, tenant_id=T, field_id="f1", field_geometry=FIELD, zone_id=None, retrieval_error=err
    )
    assert ev["status"] == "evidence_required" and err in ev["reason_codes"]


def test_unreachable_service_fails_closed():
    anns, err = fetch_annotations(
        "http://127.0.0.1:9", tenant_id=T, field_id="f1", query="q", timeout_s=1
    )
    assert anns == [] and err == "georag_retrieval_unavailable"


@pytest.mark.parametrize("difference", ["field", "geometry", "tenant", "zone", "missing_geometry"])
def test_spatial_evidence_is_bound_to_the_decision_context(difference):
    ev = _scope([_ann(scope={"geometry": INSIDE})])
    context = {"field_id": "f1", "tenant_id": T, "field_geometry": FIELD, "zone_id": None}
    overrides = {
        "field": {"field_id": "f2"},
        "geometry": {"field_geometry": FAR},
        "tenant": {"tenant_id": "tenant-b"},
        "zone": {"zone_id": "different"},
        "missing_geometry": {"field_geometry": None},
    }
    assert _decide(georag_evidence=ev, **context)["decision_scope"]["georag_grounded"]
    decision = _decide(georag_evidence=ev, **(context | overrides[difference]))
    assert not decision["decision_scope"]["georag_grounded"]
    assert not decision["georag_evidence"]["annotations"]


def test_general_reference_alone_does_not_ground_a_field_decision():
    ev = _scope([_ann(tenant="__global__", source_class="official_reference", publisher="p")])
    assert ev["annotations"][0]["spatial_match"] == "general_reference"
    assert ev["status"] == "evidence_required"


def test_touching_field_boundary_does_not_ground_the_neighbor():
    adjacent = {
        "type": "Polygon",
        "coordinates": [[[44.01, 15], [44.02, 15], [44.02, 15.01], [44.01, 15.01], [44.01, 15]]],
    }
    assert _scope([_ann(scope={"geometry": adjacent})])["status"] == "evidence_required"


@pytest.mark.parametrize(
    "scope_zone,decision_zone,admitted",
    [
        ("z1", "z2", False),
        ("z1", None, False),
        ("z1", "z1", True),
        ("", "z1", False),
        ([], "z1", False),
        (None, "z1", True),
    ],
)
@pytest.mark.parametrize("scope_key", ["field_id", "geometry"])
def test_zone_scope(scope_zone, decision_zone, admitted, scope_key):
    scope = {scope_key: "f1" if scope_key == "field_id" else INSIDE, "zone_id": scope_zone}
    result = scope_annotations(
        [_ann(scope=scope)], tenant_id=T, field_id="f1", field_geometry=FIELD, zone_id=decision_zone
    )
    assert bool(result["annotations"]) is admitted
    assert result["status"] == ("evidence_available" if admitted else "evidence_required")
    if not admitted:
        assert result["rejected"][0]["reason"] == "zone_scope_mismatch"
    assert result["direct_execution_permitted"] is False


@pytest.mark.parametrize(
    "metadata,decision_zone,reason",
    [
        ({"field_id": "f1", "zone_id": "z1"}, None, "zone_scope_mismatch"),
        ({"field_id": "f1", "zone_id": "z1"}, "z2", "zone_scope_mismatch"),
        ({"field_id": "f1", "zone_id": "z1"}, "z1", None),
        ({"field_id": "f1"}, None, None),
        ({"field_id": "f1", "zone_id": ""}, "z1", "zone_scope_mismatch"),
        ({"zone_id": "z1"}, "z1", "spatial_scope_missing"),
        ({"spatial_scope": {"geometry": INSIDE}, "zone_id": "z1"}, None, "zone_scope_mismatch"),
        ({"spatial_scope": {"geometry": INSIDE}, "field_id": "f2"}, None, "field_scope_mismatch"),
        (
            {"spatial_scope": {"field_id": "f2"}, "field_id": "f1"},
            None,
            "spatial_scope_conflict",
        ),
        (
            {"spatial_scope": {"field_id": "f1", "zone_id": "z1"}, "zone_id": "z2"},
            "z1",
            "spatial_scope_conflict",
        ),
        ({"spatial_scope": "malformed", "field_id": "f1"}, None, "spatial_scope_conflict"),
    ],
)
def test_stored_chunk_preserves_all_declared_scope(metadata, decision_zone, reason):
    chunk = KnowledgeChunk(
        chunk_id="c1",
        tenant_id=T,
        text="salinity observation",
        source_type="tenant_document",
        document_id="d1",
        chunk_index=0,
        total_chunks=1,
        metadata={
            "evidence_level": "document",
            "source_uri": "urn:fixture:d1",
            "source_revision": "r1",
            **metadata,
        },
    )
    restored = KnowledgeChunk.from_payload(chunk.payload())
    annotation = RetrievedAnnotation(restored, 0.5, 0.5, 0.1).as_annotation()
    evidence = scope_annotations(
        [annotation], tenant_id=T, field_id="f1", field_geometry=FIELD, zone_id=decision_zone
    )
    assert evidence["status"] == ("evidence_required" if reason else "evidence_available")
    assert evidence["rejected"] == ([{"chunk_id": "c1", "reason": reason}] if reason else [])
