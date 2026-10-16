"""Full inventory admission; live candidate writes have a separate native witness."""

import copy
import importlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/sahool-platform"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/rag-retrieval"))
pq = importlib.import_module("core.rag.production_qdrant")
reindex = importlib.import_module("reindex_manifest")


def spec():
    return reindex.ReindexSpec("source", "sahool_rag_reindex_v1", "v1", "a" * 64, "b" * 64)


def row(cid, tenant):
    c = pq.KnowledgeChunk(
        chunk_id=cid,
        tenant_id=tenant,
        text="ري القمح",
        source_type="uploaded_document",
        document_id=cid,
        chunk_index=0,
        total_chunks=1,
        metadata={
            "evidence_level": "document",
            "source_uri": "fixture://reindex",
            "source_revision": "v1",
        },
    )
    return (pq.canonical_storage_point_id(cid), c.payload)


def test_complete_inventory_includes_uploads_tenants_and_quarantine():
    rows = [row("upload-a", "a"), row("upload-b", "b"), row("seed:1", "__seed_quarantine__")]
    before = copy.deepcopy(rows)
    result = reindex.inventory(rows, spec())
    assert result["point_count"] == 3
    assert result["tenants"] == {"a": 1, "b": 1, "__seed_quarantine__": 1}
    assert reindex.inventory(list(reversed(rows)), spec()) == result
    assert rows == before


def test_logical_collision_across_tenants_is_not_silently_overwritten():
    with pytest.raises(ValueError, match="collision"):
        reindex.inventory([row("same", "a"), row("same", "b")], spec())


def test_noncanonical_point_identity_requires_existing_migration_plan():
    _, payload = row("document", "a")
    with pytest.raises(ValueError, match="noncanonical"):
        reindex.inventory([("legacy-point", payload)], spec())


def test_empty_and_partial_inventory_never_qualify():
    with pytest.raises(ValueError, match="empty"):
        reindex.inventory([], spec())
    with pytest.raises(ValueError, match="truncated"):
        reindex.inventory([row("a", "a"), row("b", "b")], replace(spec(), max_points=1))


def test_payload_drift_changes_reviewed_inventory_digest():
    old = [row("upload", "a")]
    changed = copy.deepcopy(old)
    changed[0][1]["metadata"]["source_revision"] = "v2"
    assert (
        reindex.inventory(old, spec())["payload_digest"]
        != reindex.inventory(changed, spec())["payload_digest"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_collection", "sahool_agri_kb"),
        ("revision", ""),
        ("model_digest", "latest"),
        ("expected_source_payload_digest", "unknown"),
        ("document_prefix", "arbitrary:"),
        ("max_points", 0),
    ],
)
def test_unpinned_or_unsafe_spec_is_rejected(field, value):
    with pytest.raises(ValueError):
        replace(spec(), **{field: value})


def test_parseable_flat_tenant_payload_is_not_admitted_for_reindex():
    point, payload = row("flat", "a")
    payload["tenant_id"] = payload["metadata"].pop("tenant_id")
    assert pq.KnowledgeChunk.from_payload(payload).tenant_id == "a"
    with pytest.raises(ValueError, match="noncanonical payload"):
        reindex.inventory([(point, payload)], spec())
