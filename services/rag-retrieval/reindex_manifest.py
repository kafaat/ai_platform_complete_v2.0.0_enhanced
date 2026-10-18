"""Prepare a complete, versioned shadow index without modifying serving authority.

Bootstrap seed upserts are not a reindex. This operation inventories every stored
document, preserves tenant/quarantine identities and provenance, re-embeds all
rows, and verifies the candidate. Alias/consumer cutover is deliberately separate:
the query encoder and collection must be admitted together by the existing RAG
convergence process.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from core.rag.production_qdrant import (
    CollectionProbeStatus,
    EmbeddingProvider,
    KnowledgeChunk,
    QdrantHttpClient,
    canonical_storage_point_id,
    canonical_storage_shape,
)
from retrieval_profile import (
    DENSE_WEIGHT,
    LEGACY_PROFILE,
    NOMIC_DIGEST,
    NOMIC_PROFILE,
    QUERY_PREFIX,
    SPARSE_WEIGHT,
)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ReindexSpec:
    source_collection: str
    target_collection: str
    revision: str
    model_digest: str
    expected_source_payload_digest: str
    document_prefix: str = ""
    max_points: int = 10000
    retrieval_profile: str = LEGACY_PROFILE

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", self.source_collection):
            raise ValueError("explicit source collection required")
        if not re.fullmatch(r"sahool_rag_reindex_[a-zA-Z0-9_-]+", self.target_collection):
            raise ValueError("target must be an explicitly isolated reindex collection")
        if self.target_collection == self.source_collection:
            raise ValueError("source collection cannot be overwritten")
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", self.revision):
            raise ValueError("explicit immutable reindex revision required")
        if not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", self.model_digest):
            raise ValueError("pinned model digest required")
        if not re.fullmatch(r"[0-9a-f]{64}", self.expected_source_payload_digest):
            raise ValueError("pinned complete source payload digest required")
        if self.document_prefix not in {"", "search_document: "}:
            raise ValueError("unknown document encoding contract")
        if self.retrieval_profile not in {LEGACY_PROFILE, NOMIC_PROFILE}:
            raise ValueError("unknown retrieval profile")
        if self.retrieval_profile == NOMIC_PROFILE and (
            self.document_prefix != "search_document: " or self.model_digest != NOMIC_DIGEST
        ):
            raise ValueError("Nomic profile requires measured model and document prefix")
        if self.retrieval_profile == LEGACY_PROFILE and self.document_prefix:
            raise ValueError("prefixed documents require the matching query profile")
        if type(self.max_points) is not int or not 1 <= self.max_points <= 100000:
            raise ValueError("bounded complete inventory required")


def inventory(rows: list[tuple[str, dict[str, Any]]], spec: ReindexSpec) -> dict[str, Any]:
    """Validate full stored identities; never silently skip incompatible rows."""
    if not rows or len(rows) > spec.max_points:
        raise ValueError("empty or truncated source inventory cannot certify a reindex")
    seen_points: set[str] = set()
    seen_chunks: set[str] = set()
    tenants: Counter[str] = Counter()
    normalized = []
    for point_id, payload in rows:
        if not canonical_storage_shape(payload):
            raise ValueError("noncanonical payload requires an explicit migration disposition")
        chunk = KnowledgeChunk.from_payload(payload, fallback_id=point_id)
        if point_id in seen_points or chunk.chunk_id in seen_chunks:
            raise ValueError("identity collision requires a separate migration disposition")
        if point_id != canonical_storage_point_id(chunk.chunk_id):
            raise ValueError("noncanonical storage identity requires the existing migration plan")
        seen_points.add(point_id)
        seen_chunks.add(chunk.chunk_id)
        tenants[chunk.tenant_id] += 1
        normalized.append((point_id, payload))
    return {
        "point_count": len(rows),
        "payload_digest": _digest(sorted(normalized, key=lambda row: row[0])),
        "tenants": dict(sorted(tenants.items())),
        "logical_id_digest": _digest(sorted(seen_chunks)),
    }


def _read_complete(client: QdrantHttpClient, spec: ReindexSpec) -> list[tuple[str, dict]]:
    page_size = min(spec.max_points + 1, 256)
    rows = client.scroll_payloads(page_size=page_size, max_pages=(spec.max_points // page_size) + 2)
    if client.collection_point_count() != len(rows):
        raise ValueError("source count and scroll disagree; no stable full inventory")
    inventory(rows, spec)
    return rows


def _aliases(client: QdrantHttpClient) -> list[dict[str, str]]:
    response = client._request("GET", "/aliases")
    if response.get("status") != "ok" or not isinstance(response.get("result"), dict):
        raise ValueError("alias inventory unavailable")
    aliases = response["result"].get("aliases")
    if not isinstance(aliases, list) or any(
        not isinstance(a, dict) or not a.get("alias_name") or not a.get("collection_name")
        for a in aliases
    ):
        raise ValueError("alias inventory malformed")
    return sorted(aliases, key=lambda a: (a["alias_name"], a["collection_name"]))


def _verify_vectors(target: QdrantHttpClient, points: list[dict[str, Any]]) -> str:
    expected = {p["id"]: p["vector"] for p in points}
    observed: dict[str, list[float]] = {}
    offset = None
    for _ in range((len(points) // 128) + 2):
        body: dict[str, Any] = {"limit": 128, "with_payload": False, "with_vector": True}
        if offset is not None:
            body["offset"] = offset
        result = target._request("POST", f"/collections/{target.collection}/points/scroll", body)[
            "result"
        ]
        for row in result["points"]:
            point_id = str(row["id"])
            if point_id in observed or point_id not in expected:
                raise RuntimeError("unexpected candidate vector identity")
            vector = row["vector"]
            original = expected[point_id]
            norm = math.sqrt(sum(float(x) ** 2 for x in original))
            normalized = [float(x) / norm for x in original]
            if (
                not isinstance(vector, list)
                or len(vector) != len(normalized)
                or not all(
                    math.isfinite(float(a))
                    and math.isclose(float(a), b, rel_tol=1e-4, abs_tol=1e-5)
                    for a, b in zip(vector, normalized, strict=True)
                )
            ):
                raise RuntimeError("candidate vector does not match the requested Cosine embedding")
            observed[point_id] = vector
        offset = result.get("next_page_offset")
        if offset is None:
            break
    if offset is not None or set(observed) != set(expected):
        raise RuntimeError("candidate vector inventory incomplete")
    return _digest(sorted(observed.items()))


def prepare_shadow_reindex(
    source: QdrantHttpClient,
    embeddings: EmbeddingProvider,
    spec: ReindexSpec,
    *,
    client_factory=QdrantHttpClient,
) -> dict[str, Any]:
    """Prepare and verify a full candidate; never switch aliases or serving config.

    Caller must supply an encoder already pinned/verified to ``model_digest``.
    A failed write may leave an unserved partial candidate for inspection. Existing
    candidate names are never reused, overwritten, or automatically deleted.
    """
    if source.collection != spec.source_collection:
        raise ValueError("source client does not match the explicit reindex specification")
    aliases = _aliases(source)
    if any(a.get("alias_name") == spec.source_collection for a in aliases):
        raise ValueError("source must be a concrete collection, not a movable alias")
    initial_rows = _read_complete(source, spec)
    initial = inventory(initial_rows, spec)
    if initial["payload_digest"] != spec.expected_source_payload_digest:
        raise ValueError("source inventory differs from the reviewed reindex specification")
    target = client_factory(
        source.base_url,
        spec.target_collection,
        api_key=source.api_key,
        timeout_s=source.timeout_s,
    )
    if target.probe_collection() is not CollectionProbeStatus.NOT_FOUND:
        raise ValueError("candidate already exists or existence is unproved; refusing writes")
    points = []
    dimensions: set[int] = set()
    for point_id, payload in initial_rows:
        text = KnowledgeChunk.from_payload(payload, fallback_id=point_id).text
        vector = embeddings.embed(spec.document_prefix + text)
        if not vector or not all(math.isfinite(float(v)) for v in vector) or not any(vector):
            raise ValueError("invalid embedding; no candidate writes performed")
        dimensions.add(len(vector))
        copied = copy.deepcopy(payload)
        copied["metadata"]["reindex_revision"] = spec.revision
        copied["metadata"]["embedding_model_digest"] = spec.model_digest
        copied["metadata"]["document_embedding_prefix"] = spec.document_prefix
        copied["metadata"]["retrieval_profile"] = spec.retrieval_profile
        points.append({"id": point_id, "vector": vector, "payload": copied})
    if len(dimensions) != 1:
        raise ValueError("embedding dimension drift; no candidate writes performed")
    if inventory(_read_complete(source, spec), spec) != initial:
        raise ValueError("source changed during embedding; candidate not created")
    dimension = next(iter(dimensions))
    # Create must fail on a race; ensure_collection would accept an existing target.
    target._request(
        "PUT",
        f"/collections/{spec.target_collection}",
        {
            "vectors": {"size": dimension, "distance": "Cosine"},
        },
    )
    target.ensure_tenant_payload_index()
    for start in range(0, len(points), 128):
        response = target._request(
            "PUT",
            f"/collections/{spec.target_collection}/points?wait=true",
            {
                "points": points[start : start + 128],
            },
        )
        if (
            response.get("status") != "ok"
            or response.get("result", {}).get("status") != "completed"
        ):
            raise RuntimeError("candidate write not completed; no authority change")
    expected_rows = [(str(p["id"]), p["payload"]) for p in points]
    expected = inventory(expected_rows, spec)
    observed = inventory(_read_complete(target, spec), spec)
    if observed != expected:
        raise RuntimeError("candidate payload/tenant/revision inventory mismatch")
    vector_digest = _verify_vectors(target, points)
    if inventory(_read_complete(source, spec), spec) != initial:
        raise RuntimeError("source changed during candidate preparation; candidate inadmissible")
    final_aliases = _aliases(source)
    if final_aliases != aliases:
        raise RuntimeError("serving aliases changed concurrently; candidate needs new review")
    return {
        "schema": "sahool.rag-shadow-reindex/v1",
        "source_collection": spec.source_collection,
        "target_collection": spec.target_collection,
        "revision": spec.revision,
        "model_digest": spec.model_digest,
        "document_prefix": spec.document_prefix,
        "retrieval_profile": spec.retrieval_profile,
        "vector_size": dimension,
        "vector_distance": "Cosine",
        "query_prefix": QUERY_PREFIX if spec.retrieval_profile == NOMIC_PROFILE else "",
        "dense_weight": DENSE_WEIGHT if spec.retrieval_profile == NOMIC_PROFILE else 0.7,
        "sparse_weight": SPARSE_WEIGHT if spec.retrieval_profile == NOMIC_PROFILE else 0.3,
        "source": initial,
        "candidate": observed,
        "candidate_vector_digest": vector_digest,
        "source_preserved": True,
        "aliases_preserved": True,
        "serving_authority_changed": False,
        "acceptance": "SHADOW_PREPARED_QUERY_ENCODER_AND_CUTOVER_ADMISSION_STILL_REQUIRED",
    }
