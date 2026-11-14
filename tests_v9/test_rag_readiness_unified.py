"""Advisor and RAG live certification share one readiness decision.

These are pure checks; operational readiness does not grant RAG cutover.
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
        "canonical_payload_parity": False,
    }


def test_ready_is_an_operational_claim_not_an_authority_cutover():
    assert rag_operational_ready(_usable())


def test_missing_proof_is_not_ready():
    for key in (
        "status",
        "embedding_contract_parity",
        "collection_vector_schema_parity",
        "sparse_index_hydrated",
        "sparse_index_count",
    ):
        payload = _usable()
        payload.pop(key)
        assert not rag_operational_ready(payload), key


def test_explicit_unready_and_invalid_ready_flags_fail_closed():
    for value in (False, None, 0, "false", "true"):
        payload = _usable()
        payload["ready"] = value
        assert not rag_operational_ready(payload), value


def test_sparse_index_requires_a_positive_integer():
    for count in (0, -1, None, True, False, "5", 5.0):
        payload = _usable()
        payload["sparse_index_count"] = count
        assert not rag_operational_ready(payload), count


def test_parity_flags_must_be_exact_true():
    for name in (
        "embedding_contract_parity",
        "collection_vector_schema_parity",
        "sparse_index_hydrated",
    ):
        for value in (False, None, 1, "true"):
            payload = _usable()
            payload[name] = value
            assert not rag_operational_ready(payload), (name, value)


def test_unexpected_response_type_fails_closed():
    for value in (None, [], "ready", True):
        assert not rag_operational_ready(value)


def test_advisor_and_certification_reference_same_predicate():
    advisor = (ROOT / "services/ai_agronomist/main.py").read_text(
        encoding="utf-8"
    )
    cert = (ROOT / "scripts/ci/ai_rag_live_certification.py").read_text(
        encoding="utf-8"
    )
    assert "rag_operational_ready(rag)" in advisor
    assert "rag_operational_ready(r)" in cert
    assert "ready.status == 200 and rag_operational_ready(r)" in cert
