"""W2-03: the learning-update contract carries the agronomic review end to end.

The platform sends ``review_status``, ``agronomically_approved`` and ``agronomic_review``;
``LearningUpdateIn`` had none of them, so Pydantic dropped them and an approved or rejected
review was lost. In SoR mode the reply now carries ``write`` and the review read back from the
stored row, which is what the platform's strict cutover (``_unproven_learning_update_fields``)
demands. Storage behaviour itself is proven on PostgreSQL in ``test_migration_033_pg16.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import main
import pytest
from fastapi.testclient import TestClient

client = TestClient(main.app)
HEADERS = {"X-Tenant-Id": "00000000-0000-0000-0000-0000000000a1"}
REVIEW = {"reviewer_id": "agro-1", "verdict": "approved", "evidence_ids": ["ev-1"]}


@pytest.fixture
def sor(monkeypatch):
    monkeypatch.delenv("DECISION_REQUIRE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("SAHOOL_ENV", raising=False)
    monkeypatch.setattr(main, "sor_enabled", lambda: True)
    received: list = []

    async def stored(**kwargs):
        received.append(kwargs)
        # The stored row answers, not the request: report what "the database" holds.
        return {
            "update_id": kwargs["update_id"],
            "replayed": False,
            "write": "updated",
            "review_status": "approved",
            "agronomically_approved": True,
        }

    monkeypatch.setattr(main, "persist_learning_update", stored)
    return received


def _send(**extra):
    body = {
        "update_id": "lu_1",
        "model_id": "m1",
        "source_type": "outcome_record",
        "source_id": "o1",
    }
    body.update(extra)
    return client.post("/v1/learning/updates", headers=HEADERS, json=body)


def test_review_fields_reach_the_writer_instead_of_being_dropped(sor):
    res = _send(review_status="approved", agronomically_approved=True, agronomic_review=REVIEW)
    assert res.status_code == 200, res.text
    payload = sor[0]["payload"]
    assert payload.review_status == "approved"
    assert payload.agronomically_approved is True
    assert payload.agronomic_review == REVIEW


def test_reply_proves_the_stored_write_and_review(sor):
    body = _send(
        review_status="approved", agronomically_approved=True, agronomic_review=REVIEW
    ).json()
    assert body["authoritative"] is True and body["persisted"] is True
    assert body["write"] == "updated"
    assert body["review_status"] == "approved" and body["agronomically_approved"] is True
    assert body["tenant_id"] == HEADERS["X-Tenant-Id"] and body["update_id"] == "lu_1"


def test_an_unknown_review_status_is_refused_before_storage(sor):
    res = _send(review_status="looks-fine")
    assert res.status_code == 422
    assert sor == []


def test_a_review_the_database_refuses_answers_422_not_500(monkeypatch, sor):
    async def refused(**kwargs):
        raise main.LearningUpdateReviewInvalid("chk_oluj_agronomic_approval_consistency")

    monkeypatch.setattr(main, "persist_learning_update", refused)
    res = _send(review_status="approved", agronomically_approved=True, agronomic_review=None)
    assert res.status_code == 422
    assert "agronomic_review_invalid" in res.json()["detail"]


def test_an_unreviewed_update_keeps_the_defaults(sor):
    _send()
    payload = sor[0]["payload"]
    assert payload.review_status == "unreviewed"
    assert payload.agronomically_approved is False
    assert payload.agronomic_review is None


def test_a_review_storage_gap_answers_503_with_its_reason(monkeypatch, sor):
    async def unavailable(**kwargs):
        raise main.LearningUpdateReviewUnavailable("online_learning_updates has no review columns")

    monkeypatch.setattr(main, "persist_learning_update", unavailable)
    res = _send(review_status="approved", agronomically_approved=True, agronomic_review=REVIEW)
    assert res.status_code == 503
    assert res.json()["detail"] == "agronomic review storage waits for migration 039"


def test_an_identity_conflict_answers_409(monkeypatch, sor):
    async def conflict(**kwargs):
        raise main.LearningUpdateConflict(kwargs["update_id"])

    monkeypatch.setattr(main, "persist_learning_update", conflict)
    res = _send()
    assert res.status_code == 409
    assert res.json()["detail"] == "learning_update_id_conflict"


# ── The real reply through the platform's strict cutover check ────────────────────────────
# Review of #1502: the link between the two services was a text scan. These run the actual
# /v1/learning/updates reply through the platform's _unproven_learning_update_fields, loaded from
# its source (the function is pure, so the platform's dependencies are not needed here).
_PLATFORM_STORE = Path(__file__).resolve().parents[3] / (
    "services/sahool-platform/api/phase_runtime_store.py"
)


def _platform_strict_check():
    tree = ast.parse(_PLATFORM_STORE.read_text(encoding="utf-8"))
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_unproven_learning_update_fields"
    )
    namespace: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(_PLATFORM_STORE), "exec"), namespace)
    return namespace["_unproven_learning_update_fields"]


def _platform_sent(**review):
    # The keys the platform puts in service_payload and later compares (phase_runtime_store.py).
    return {"update_id": "lu_1", **review}


def test_the_real_reply_passes_the_platform_strict_check(monkeypatch, sor):
    sent = _platform_sent(review_status="approved", agronomically_approved=True)
    reply = _send(**sent, agronomic_review=REVIEW).json()
    assert _platform_strict_check()(reply, HEADERS["X-Tenant-Id"], sent) == []


def test_a_stored_review_that_differs_is_refused_by_the_platform(monkeypatch, sor):
    async def stored_unreviewed(**kwargs):
        return {
            "update_id": kwargs["update_id"],
            "replayed": True,
            "write": "unchanged",
            "review_status": "unreviewed",
            "agronomically_approved": False,
        }

    monkeypatch.setattr(main, "persist_learning_update", stored_unreviewed)
    sent = _platform_sent(review_status="approved", agronomically_approved=True)
    reply = _send(**sent, agronomic_review=REVIEW).json()
    assert reply["write"] == "unchanged"
    assert _platform_strict_check()(reply, HEADERS["X-Tenant-Id"], sent) == [
        "review_status",
        "agronomically_approved",
    ]
