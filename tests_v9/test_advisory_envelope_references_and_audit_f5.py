"""F5 — the advisory envelope must not say "no human review" over absent references
or an audit record that was not confirmed saved.

The runtime knows both facts before it builds the envelope (``rag_available`` /
``rag_unavailable_reason`` and ``audit_event.status``), but the envelope read neither:
a grounded, confident answer produced while rag-retrieval was down and the audit write
failed still came out ``requires_human_review: false`` with nothing named.

Only "references available" (``rag_available is True``) and "audit recorded"
(``audit_event.status == "recorded"``) are the quiet states. Every other state —
including a key that is absent or malformed — is named with a stable code and forces
review. No network, database or model is used.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from services.ai_agronomist import ai_evidence_runtime as runtime
from services.ai_agronomist.advisory_contract import build_advisory_envelope
from services.ai_agronomist.decision_contracts import has_decision_keys
from tests_v9.test_b6m4_structured_advisory import FIELD, TENANT, state

pytestmark = pytest.mark.unit

_RECORDED = {"status": "recorded", "persisted": True}
_GOOD = {
    "answer_ar": "الحقل ضمن المدى الطبيعيّ لمؤشّر NDVI مع رطوبة كافية.",
    "confidence": 0.82,
    "evidence_ids": ["ndvi:2026-06", "weather:nasa_power"],
    "pending_approvals": [],
    "generation_provider": "openrouter",
    "rag_available": True,
    "rag_unavailable_reason": None,
    "audit_event": _RECORDED,
}


def test_references_available_and_audit_recorded_is_the_only_quiet_state():
    env = build_advisory_envelope(_GOOD)
    assert env["evidence_missing"] == [], env
    assert env["limitations"] == [], env
    assert env["requires_human_review"] is False, env


def test_claim_absent_references_and_unsaved_audit_force_review():
    """The audit's witness: both facts known to the runtime, neither reached the envelope."""
    env = build_advisory_envelope(
        {
            **_GOOD,
            "rag_available": False,
            "rag_unavailable_reason": "TENANT_CORPUS_EMPTY",
            "audit_event": {"status": "not_persisted", "persisted": False},
        }
    )
    assert env["requires_human_review"] is True, env
    assert env["evidence_missing"] == [
        "references_unavailable",
        "references_unavailable:TENANT_CORPUS_EMPTY",
    ], env
    assert env["limitations"] == ["references_unavailable", "audit_record_not_persisted"], env


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("TENANT_CORPUS_EMPTY", ["references_unavailable:TENANT_CORPUS_EMPTY"]),
        ("rag_retrieval_unavailable", ["references_unavailable:rag_retrieval_unavailable"]),
        ("rag_upstream_http_503", ["references_unavailable:rag_upstream_http_503"]),
        ("rag_transport_unavailable", ["references_unavailable:rag_transport_unavailable"]),
        # No reason, or text that is not a code (a body, a URL), is never echoed.
        (None, []),
        ("", []),
        ("http://user:secret@rag:8000/v1/search failed", []),
        ({"code": "x"}, []),
    ],
)
def test_absent_references_are_named_with_a_bounded_reason(reason, expected):
    env = build_advisory_envelope(
        {**_GOOD, "rag_available": False, "rag_unavailable_reason": reason}
    )
    assert env["evidence_missing"] == ["references_unavailable", *expected], env
    assert "references_unavailable" in env["limitations"], env
    assert env["requires_human_review"] is True, env


@pytest.mark.parametrize("value", [None, "true", 1, 0, "false"])
def test_reference_state_that_is_not_a_boolean_is_unverified_not_available(value):
    env = build_advisory_envelope({**_GOOD, "rag_available": value})
    assert env["evidence_missing"] == ["references_unverified"], env
    assert "references_unverified" in env["limitations"], env
    assert env["requires_human_review"] is True, env


def test_missing_reference_key_is_unverified():
    response = {k: v for k, v in _GOOD.items() if k != "rag_available"}
    env = build_advisory_envelope(response)
    assert env["evidence_missing"] == ["references_unverified"], env
    assert env["requires_human_review"] is True, env


@pytest.mark.parametrize(
    "audit_event,code",
    [
        ({"status": "not_persisted", "persisted": False}, "audit_record_not_persisted"),
        ({"status": "unconfirmed"}, "audit_record_unconfirmed"),
        ({"status": "failed", "http_status": 503}, "audit_record_failed"),
        ({"status": "failed", "reason": "ConnectError"}, "audit_record_failed"),
        (
            {"status": "skipped", "reason": "SAHOOL_AGENT_TOKEN not configured"},
            "audit_record_skipped",
        ),
        # Anything the runtime does not define is "not confirmed", never "recorded".
        ({"status": "ok"}, "audit_record_unconfirmed"),
        ({"status": "RECORDED"}, "audit_record_unconfirmed"),
        ({"persisted": True}, "audit_record_unconfirmed"),
        ({}, "audit_record_unconfirmed"),
        (None, "audit_record_unconfirmed"),
        ("recorded", "audit_record_unconfirmed"),
    ],
)
def test_audit_record_not_confirmed_saved_is_named_and_forces_review(audit_event, code):
    env = build_advisory_envelope({**_GOOD, "audit_event": audit_event})
    assert env["limitations"] == [code], env
    assert env["requires_human_review"] is True, env
    # The audit record is not agronomic evidence: it does not enter evidence_missing.
    assert env["evidence_missing"] == [], env


def test_missing_audit_key_is_unconfirmed():
    response = {k: v for k, v in _GOOD.items() if k != "audit_event"}
    env = build_advisory_envelope(response)
    assert env["limitations"] == ["audit_record_unconfirmed"], env
    assert env["requires_human_review"] is True, env


def test_new_codes_do_not_turn_references_into_decision_evidence():
    """RAG stays reference context: its absence adds codes, never evidence or a decision."""
    available = build_advisory_envelope(_GOOD)
    absent = build_advisory_envelope({**_GOOD, "rag_available": False, "audit_event": None})
    assert absent["evidence_used"] == available["evidence_used"] == _GOOD["evidence_ids"]
    assert absent["decision"] == available["decision"] == "advisory_only"
    assert absent["confidence"] == available["confidence"]
    assert set(absent) == set(available), "the envelope shape is unchanged"
    assert has_decision_keys(absent) is False


# ── the runtime: the envelope is built from the response that carries both facts ──
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _chat(monkeypatch, *, rag_response, audit_event):
    def transport(request):
        if request.url.path == "/v1/search":
            return rag_response()
        return httpx.Response(200, json={"edges": []})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(transport), **kw),
    )
    monkeypatch.setattr(runtime, "_fetch_canonical_field_state", AsyncMock(return_value=state()))
    monkeypatch.setattr(runtime, "_generation_allowed", lambda _: False)
    monkeypatch.setattr(runtime, "_record_ai_advice_event", AsyncMock(return_value=audit_event))
    from services.ai_agronomist import main

    resp = TestClient(main.app).post(
        "/v1/chat",
        json={"question": "ما حالة الحقل؟", "field_id": FIELD, "crop": "wheat"},
        headers={"X-Tenant-Id": TENANT},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _corpus_empty():
    return httpx.Response(424, json={"detail": {"code": "TENANT_CORPUS_EMPTY"}})


def _healthy():
    return httpx.Response(200, json={"annotations": []})


def test_runtime_empty_corpus_reaches_the_envelope(monkeypatch):
    body = _chat(monkeypatch, rag_response=_corpus_empty, audit_event=_RECORDED)
    assert body["rag_available"] is False
    advisory = body["advisory"]
    assert "references_unavailable" in advisory["evidence_missing"], advisory
    assert "references_unavailable:TENANT_CORPUS_EMPTY" in advisory["evidence_missing"], advisory
    assert "references_unavailable" in advisory["limitations"], advisory
    assert not [c for c in advisory["limitations"] if c.startswith("audit_record_")], advisory
    assert advisory["requires_human_review"] is True, advisory


@pytest.mark.parametrize(
    "audit_event,code",
    [
        ({"status": "not_persisted", "persisted": False}, "audit_record_not_persisted"),
        ({"status": "unconfirmed"}, "audit_record_unconfirmed"),
        ({"status": "failed", "http_status": 500}, "audit_record_failed"),
        ({"status": "skipped", "reason": "x"}, "audit_record_skipped"),
    ],
)
def test_runtime_unsaved_audit_reaches_the_envelope(monkeypatch, audit_event, code):
    body = _chat(monkeypatch, rag_response=_healthy, audit_event=audit_event)
    assert body["rag_available"] is True
    assert body["audit_event"]["status"] == audit_event["status"]
    advisory = body["advisory"]
    assert code in advisory["limitations"], advisory
    assert not [c for c in advisory["evidence_missing"] if c.startswith("references_")], advisory
    assert advisory["requires_human_review"] is True, advisory


def test_runtime_recorded_audit_and_available_references_add_no_code(monkeypatch):
    body = _chat(monkeypatch, rag_response=_healthy, audit_event=_RECORDED)
    advisory = body["advisory"]
    named = [*advisory["evidence_missing"], *advisory["limitations"]]
    assert not [c for c in named if c.startswith(("references_", "audit_record_"))], advisory
