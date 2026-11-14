"""One readiness decision for the advisor and the live RAG certification tool.

These are pure, non-network tests. Runtime E2E and RAG authority cutover must
still be certified separately with deployment and tenant-bound receipts.
"""

from pathlib import Path

import pytest

from shared.ai.rag_readiness import rag_operational_ready

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _usable() -> dict:
    return {
        "status": "ready",
        "embedding_contract_parity": True,
        "collection_vector_schema_parity": True,
        "sparse_index_hydrated": True,
        "sparse_index_count": 5,
        # Retrieval may be operational during parity, but not yet authoritative.
        "canonical_payload_parity": False,
    }


def test_ready_is_an_operational_claim_not_an_authority_cutover():
    assert rag_operational_ready(_usable())


@pytest.mark.parametrize(
    "missing",
    [
        "status",
        "embedding_contract_parity",
        "collection_vector_schema_parity",
        "sparse_index_hydrated",
        "sparse_index_count",
    ],
)
def test_missing_proof_is_not_ready(missing):
    payload = _usable()
    payload.pop(missing)
    assert not rag_operational_ready(payload)


@pytest.mark.parametrize("count", [0, -1, None, True, False, "5", 5.0])
def test_sparse_index_requires_a_positive_integer(count):
    payload = _usable()
    payload["sparse_index_count"] = count
    assert not rag_operational_ready(payload)


@pytest.mark.parametrize(
    "name",
    [
        "embedding_contract_parity",
        "collection_vector_schema_parity",
        "sparse_index_hydrated",
    ],
)
def test_missing_operational_parity_blocks_readiness(name):
    payload = _usable()
    payload[name] = False
    assert not rag_operational_ready(payload)


@pytest.mark.parametrize("value", [None, [], "ready", True])
def test_unexpected_response_type_fails_closed(value):
    assert not rag_operational_ready(value)


def test_advisor_and_certification_reference_same_predicate():
    advisor = (ROOT / "services/ai_agronomist/main.py").read_text(encoding="utf-8")
    live_cert = (ROOT / "scripts/ci/ai_rag_live_certification.py").read_text(
        encoding="utf-8"
    )
    assert "rag_operational_ready(rag)" in advisor
    assert "rag_operational_ready(r)" in live_cert
    assert "ready.status == 200 and rag_operational_ready(r)" in live_cert
