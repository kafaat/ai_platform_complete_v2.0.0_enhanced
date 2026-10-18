"""Validate experiment arithmetic/admission; these tests are not retrieval evidence."""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "certification/evidence/chatgpt_closure_nine_20261016/rag/relevance_experiment.py"
spec = importlib.util.spec_from_file_location("rag_relevance_experiment", PATH)
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def manifest():
    return {
        "version": "ar-fixture-v1",
        "judgment_provenance": "unit fixture only; not expert relevance judgments",
        "subject_sha": "a" * 40,
        "model": "nomic-embed-text:latest",
        "model_digest": "b" * 64,
        "collections": {
            "raw": "sahool_rag_experiment_raw",
            "prefixed": "sahool_rag_experiment_prefixed",
        },
        "queries": [
            {
                "id": "q1",
                "text": "ري القمح",
                "split": "selection",
                "tenant_id": "a",
                "judgments": {"d1": 3},
            },
            {
                "id": "q2",
                "text": "ملوحة التربة",
                "split": "acceptance",
                "tenant_id": "a",
                "judgments": {"d2": 3},
            },
        ],
    }


def test_rank_degradation_is_measured():
    qrels = {"a": 3, "b": 1, "c": 0}
    ideal = experiment.metrics(["a", "b"], qrels, 2)
    degraded = experiment.metrics(["c", "a"], qrels, 2)
    assert ideal == {"precision_at_k": 1, "recall_at_k": 1, "mrr_at_k": 1, "ndcg_at_k": 1}
    assert degraded["precision_at_k"] == degraded["recall_at_k"] == degraded["mrr_at_k"] == 0.5
    assert degraded["ndcg_at_k"] < ideal["ndcg_at_k"]


def test_empty_results_are_zero_not_perfect_parity():
    assert set(experiment.metrics([], {"a": 3}, 5).values()) == {0}


@pytest.mark.parametrize(
    "ids,qrels,k",
    [
        (["a", "a"], {"a": 1}, 5),
        (["b"], {"a": 1}, 5),
        ([], {"a": 0}, 5),
        ([], {"a": 4}, 5),
        ([], {"a": True}, 5),
        ([], {"a": 1}, 0),
        ([], {"a": 1}, True),
    ],
)
def test_invalid_metric_inputs_fail_closed(ids, qrels, k):
    with pytest.raises(ValueError):
        experiment.metrics(ids, qrels, k)


def test_experiment_requires_held_out_queries():
    value = manifest()
    experiment.validate_manifest(value)
    value["queries"][1]["text"] = value["queries"][0]["text"]
    with pytest.raises(ValueError, match="overlaps"):
        experiment.validate_manifest(value)


def test_production_collection_not_accepted_as_experiment():
    value = manifest()
    value["collections"]["raw"] = "sahool_agri_kb"
    with pytest.raises(ValueError, match="isolated"):
        experiment.validate_manifest(value)


def test_exact_model_identity_required():
    value = manifest()
    value["model_digest"] = "latest"
    with pytest.raises(ValueError, match="digest"):
        experiment.validate_manifest(value)


@pytest.mark.parametrize("vector", [[float("nan"), 1], [float("inf"), 1], [1], [0, 0]])
def test_invalid_or_changed_vectors_cannot_certify_prefix(vector):
    assert not experiment.vector_matches(vector, [1, 2])


def test_document_vector_correspondence_is_numeric_not_dimension_only():
    assert experiment.vector_matches([1.0, 2.0], [1.0, 2.0])
    assert not experiment.vector_matches([2.0, 1.0], [1.0, 2.0])
    assert not experiment.vector_matches([0.0, 0.0], [0.0, 0.0])


@pytest.mark.parametrize(
    "endpoint", ["file:///tmp/model", "https://user:secret@host", "https://host?key=secret"]
)
def test_endpoint_credentials_and_non_http_schemes_rejected(endpoint):
    with pytest.raises(ValueError):
        experiment.safe_endpoint(endpoint)
