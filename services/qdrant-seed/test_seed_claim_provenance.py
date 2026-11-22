"""Exercise the real seed writer, local Qdrant storage and annotation contract."""

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(Path(__file__).parent), str(ROOT / "services/sahool-platform"), str(ROOT)]

from aljawf_knowledge import ALJAWF_KNOWLEDGE  # noqa: E402

from shared.ai.seed_claims import partition_generation_references  # noqa: E402


def test_seed_records_are_attributed_not_verified():
    assert len(ALJAWF_KNOWLEDGE) == 54
    assert len({d["source"] for d in ALJAWF_KNOWLEDGE}) == 31
    assert sum(d["topic"] == "decision_rule" for d in ALJAWF_KNOWLEDGE) == 39
    assert all(
        d["claim_source_label"] == d["source"]
        and d["claim_verification"] == "not_verified_against_original"
        for d in ALJAWF_KNOWLEDGE
    )
    assert any(d["claim_locator"] == "ص 17" for d in ALJAWF_KNOWLEDGE)


def test_annotations_and_legacy_claims_after_local_qdrant_roundtrip(tmp_path, monkeypatch):
    import seed
    from core.rag.production_qdrant import KnowledgeChunk, RetrievedAnnotation
    from qdrant_client import AsyncQdrantClient

    async def run():
        path = str(tmp_path / "qdrant")
        store = AsyncQdrantClient(path=path)
        monkeypatch.setattr(seed, "AsyncQdrantClient", lambda **kwargs: store)

        # The indexed vectors are deterministic fixtures, not Ollama output.
        async def embed(text, http):
            return [0.6, 0.8]

        monkeypatch.setattr(seed, "_embed", embed)
        monkeypatch.setattr(seed, "SEED_TENANT_ID", "research-test")
        monkeypatch.setattr(seed, "_load_provenance_manifest", lambda: {})
        monkeypatch.setattr(seed, "_load_excluded_chunk_ids", lambda: frozenset())
        await seed.seed()
        client = AsyncQdrantClient(path=path)
        try:
            records, _ = await client.scroll(seed.COLLECTION, limit=100, with_payload=True)
            assert len(records) == 64
            by_id = {p.payload["metadata"]["chunk_id"]: p.payload for p in records}
            exemplar = by_id["seed:100"]
            ck = KnowledgeChunk.from_payload(exemplar)
            note = RetrievedAnnotation(ck, 0.8, None, 0.8).as_annotation()
            assert note["claim_source_label"] == exemplar["metadata"]["claim_source_label"]
            assert note["claim_verification"] == "not_verified_against_original"
            legacy = dict(note)
            for k in ("claim_source_label", "claim_locator", "claim_verification"):
                legacy.pop(k)
            usable, held = partition_generation_references(
                [note, legacy, {"chunk_id": "else", "text": "original"}]
            )
            # No approval record exists, so nothing reaches generation: the flagged seeds keep
            # their claim pointer and the unflagged excerpt is held for lack of a record.
            assert usable == []
            assert len(held) == 3 and all("text" not in v for v in held)
            assert all(
                v["claim_source_label"] == note["claim_source_label"]
                and v["generation_hold_reason"] == "seed_claim_not_verified_against_original"
                for v in held[:2]
            )
            assert held[2]["chunk_id"] == "else"
            assert held[2]["generation_hold_reason"] == "source_revision_missing"
        finally:
            await client.close()

    asyncio.run(run())
