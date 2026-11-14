"""Canonical RAG operational-readiness predicate.

Readiness of the retrieval dependency is not authority cutover: the latter
requires a separate, subject-bound live-parity and corpus audit receipt.
"""

from __future__ import annotations

from typing import Any


def rag_operational_ready(payload: Any) -> bool:
    """Fail closed unless a usable, profile-bound hybrid retrieval corpus is ready.

    Does not certify canonical payload parity, per-tenant relevance, grounded
    response quality, or the direct-Qdrant authority cutover.
    """
    if not isinstance(payload, dict):
        return False
    count = payload.get("sparse_index_count")
    return (
        payload.get("status") == "ready"
        and payload.get("embedding_contract_parity") is True
        and payload.get("collection_vector_schema_parity") is True
        and payload.get("sparse_index_hydrated") is True
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
    )
