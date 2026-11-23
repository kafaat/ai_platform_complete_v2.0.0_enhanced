"""F11: a versioned golden evaluation of the advisor's evidence behaviour.

The cases live in ``advisor_golden_cases.v1.json`` beside this file. Each case gives canned
inputs and structural expectations: abstains, requires_human_review, limitation codes, no dose
or product name in published text, a citation for each published fact. This file runs them
offline against the real service functions:

* ``runtime``: ``POST /v1/chat`` on the real app, so ``build_evidence_response``, the approval
  gate and ``build_advisory_envelope`` all run. Only the edges are canned: HTTP to retrieval,
  the knowledge graph and the platform goes through an ``httpx.MockTransport``, the canonical
  field state is returned by a stub, and the model is never called.
* ``approval_gate``: ``partition_generation_references`` with an in-memory approval index.
* ``structured_advisory``: ``preview_advisory`` against the owner snapshot fixture.
* ``tool_loop``: ``tool_loop.run_tool_calls``, then the envelope over its result.
* ``envelope``: ``build_advisory_envelope`` over a quiet response with one field changed.

A case whose expected behaviour is not on main names the gap in ``known_gap`` and runs as a
strict expected failure: it turns the run red the day the fix lands, and the entry is removed
then. No case holds an agronomic answer; the ``agronomist_review`` slots stay empty until an
agronomist signs them off, and ``test_agronomist_slots_stay_empty_until_signed_off`` holds that.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from services.ai_agronomist import ai_evidence_runtime as runtime
from services.ai_agronomist import tool_loop
from services.ai_agronomist.advisory_contract import build_advisory_envelope
from shared.ai import reference_approvals
from shared.ai.reference_approvals import MANIFEST_SCHEMA, index_approvals
from shared.ai.seed_claims import partition_generation_references
from shared.ai.structured_advisory import (
    SCHEMA as ADVISORY_SCHEMA,
)
from shared.ai.structured_advisory import (
    AdvisoryRejected,
    evidence_fingerprint,
    fact_catalog,
    preview_advisory,
)
from tests_v9.test_b6m4_structured_advisory import FIELD, OTHER, TENANT, state

pytestmark = pytest.mark.unit

CASES_PATH = Path(__file__).with_name("advisor_golden_cases.v1.json")
CASES_SCHEMA = "sahool.advisor_golden_eval"
CASES_SCHEMA_VERSION = 1
LAYERS = frozenset({"runtime", "approval_gate", "structured_advisory", "tool_loop", "envelope"})
# The nine behaviours F11 asked for. Each one needs at least one case that runs green on main.
REQUIRED_CATEGORIES = frozenset(
    {
        "missing_evidence",
        "reference_other_region_or_crop",
        "expired_reference",
        "imagery_date",
        "retrieval_unavailable",
        "audit_not_saved",
        "proposal_vs_execution",
        "numeric_claim_without_source",
        "tenant_mismatch",
    }
)
AGRONOMIST_SLOTS = {
    "status",
    "reference_answer_ar",
    "forbidden_product_terms",
    "reviewer",
    "reviewed_on",
}
PLACEHOLDERS = {"<FIELD>": FIELD, "<TENANT>": TENANT, "<OTHER_TENANT>": OTHER}

GOLDEN_EXCERPT = {
    "chunk_id": "golden:1:0",
    "document_id": "golden:1",
    "source_revision": "golden-rev-1",
    "text": "golden-eval placeholder excerpt; it carries no agronomic content",
}
_RECORDED = {"status": "recorded", "persisted": True}
# A response every check is quiet about (F5's quiet state). Envelope and tool-loop cases change
# one thing on top of it, so a code or a review flag can only come from that change.
_QUIET_RESPONSE = {
    "answer_ar": "golden-eval: evidence-only answer",
    "confidence": 0.82,
    "evidence_ids": ["golden:evidence:1"],
    "pending_approvals": [],
    "generation_provider": "golden-provider",
    "rag_available": True,
    "rag_unavailable_reason": None,
    "audit_event": _RECORDED,
}
# A dose is a number with a mass or volume per area, volume or plant. This is a shape, not a
# list of products or rates: product names come only from an agronomist's signed-off slot.
_DOSE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:kg|g|mg|l|ml|lb|oz|كغ|كجم|كلغ|غم|جم|غرام|ملغ|لتر|مل)\s*/\s*"
    r"(?:ha|hectare|acre|feddan|dunum|donum|l|tree|plant|هكتار|فدان|دونم|لتر|شجرة|نبات)"
    r"|\bdos(?:e|age)\b|جرعة",
    re.IGNORECASE,
)
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _substitute(value):
    if isinstance(value, str):
        return PLACEHOLDERS.get(value, value)
    if isinstance(value, list):
        return [_substitute(v) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v) for k, v in value.items()}
    return value


def load_cases() -> dict:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


# ── canned inputs ────────────────────────────────────────────────────────────────────────────
def _approval_index(spec: dict):
    """An in-memory approval of the placeholder excerpt. Never written to the shipped manifest."""
    record = {
        "approval_id": "golden-eval-approval",
        "content_digest": reference_approvals.content_digest(GOLDEN_EXCERPT["text"]),
        "source_revision": GOLDEN_EXCERPT["source_revision"],
        "source": {
            "title": "golden-eval fixture source",
            "publisher": "golden-eval fixture publisher",
            "publication_date": "2025-01-01",
        },
        "reviewer": {"name": "golden-eval fixture", "identity": "golden-eval-0000"},
        "reviewed_on": spec["reviewed_on"],
        "valid_until": spec["valid_until"],
        "applicability": {
            "crops": spec["crops"],
            "regions": spec["regions"],
            "jurisdiction": "golden-jurisdiction",
        },
    }
    return index_approvals({"schema": MANIFEST_SCHEMA, "schema_version": 1, "approvals": [record]})


def _field_state(kind: str, context: dict | None):
    if kind == "none":
        return None
    body = state()
    if kind == "canonical_with_pack":
        context = context or {}
        dates = [{"date": d} for d in context.get("scene_dates", [])]
        body["ai_context_pack"] = {
            "field_id": FIELD,
            "readiness": context.get("readiness"),
            "imagery_timeline": {
                "available": bool(dates),
                "per_indicator": {"ndvi": {"available": True, "dates": dates, "total": len(dates)}},
                "total_dates": len(dates),
                "unique_scene_dates": len(dates),
            },
        }
    return body


# ── layers ───────────────────────────────────────────────────────────────────────────────────
def _run_runtime(monkeypatch, inp: dict) -> dict:
    rag = inp["rag"]
    calls: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/v1/search":
            if rag.get("transport_error"):
                raise httpx.ConnectError("golden-eval: retrieval unreachable", request=request)
            if rag["status"] != 200:
                return httpx.Response(rag["status"], json={"detail": {"code": rag.get("code")}})
            found = [dict(GOLDEN_EXCERPT)] if rag["annotations"] == "golden_excerpt" else []
            return httpx.Response(200, json={"annotations": found})
        if request.url.path == "/internal/events/ai-advice":
            return httpx.Response(200, json={"persisted": False})
        return httpx.Response(200, json={"edges": []})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(transport), **kw),
    )
    field_state = AsyncMock(
        return_value=_field_state(inp.get("field_state", "none"), inp.get("field_context"))
    )
    monkeypatch.setattr(runtime, "_fetch_canonical_field_state", field_state)

    audit = inp["audit"]
    audit_stub = None
    if "stub_status" in audit:
        audit_stub = AsyncMock(return_value={"status": audit["stub_status"], "persisted": True})
        monkeypatch.setattr(runtime, "_record_ai_advice_event", audit_stub)
    elif audit["real"] == "token_absent":
        monkeypatch.setattr(runtime, "AGENT_TOKEN", "")
    elif audit["real"] == "platform_not_persisted":
        # The real writer runs; the signed tenant headers it needs are supplied, not keys.
        monkeypatch.setattr(runtime, "AGENT_TOKEN", "golden-eval-placeholder")
        monkeypatch.setattr(runtime, "_platform_tenant_headers", lambda *_a: {"X-Golden-Eval": "1"})
    else:
        raise AssertionError(f"unknown audit input {audit!r}")

    if inp.get("approvals"):
        index = _approval_index(inp["approvals"])
        monkeypatch.setattr(reference_approvals, "shipped_approvals", lambda: index)

    generation = inp.get("generation")
    if generation:
        generated = SimpleNamespace(
            text=generation["text"],
            model="golden-model",
            provider="golden-provider",
            tool_calls=[],
            pending_approvals=[],
            tool_calls_truncated=False,
            tool_rounds=0,
        )
        envelope = runtime.policy_envelope
        monkeypatch.setattr(runtime, "_generation_allowed", lambda _tenant: True)
        monkeypatch.setattr(runtime.ai_generation, "resolve_generation", lambda *_a: None)
        monkeypatch.setattr(
            envelope,
            "gate_generation",
            lambda _env, *, external: {"decision": envelope.DECISION_ALLOWED, "reason": "golden"},
        )
        monkeypatch.setattr(runtime.ai_generation, "generate", AsyncMock(return_value=generated))
    else:
        monkeypatch.setattr(runtime, "_generation_allowed", lambda _tenant: False)

    headers = {} if inp.get("headers", {}).get("tenant") == "missing" else {"X-Tenant-Id": TENANT}
    from services.ai_agronomist import main

    resp = TestClient(main.app).post("/v1/chat", json=inp["request"], headers=headers)
    body = resp.json()
    return {
        "status_code": resp.status_code,
        "response": body,
        "envelope": body.get("advisory") if resp.status_code == 200 else None,
        "tool_calls": body.get("tool_calls") if resp.status_code == 200 else None,
        "downstream_calls": len(calls)
        + field_state.await_count
        + (audit_stub.await_count if audit_stub else 0),
        "audit_kwargs": audit_stub.await_args.kwargs
        if audit_stub and audit_stub.await_args
        else None,
    }


def _run_approval_gate(_monkeypatch, inp: dict) -> dict:
    usable, held = partition_generation_references(
        [dict(GOLDEN_EXCERPT)],
        approvals=_approval_index(inp["approval"]),
        as_of=date.fromisoformat(inp["as_of"]),
        **inp["question_scope"],
    )
    return {"usable": usable, "held": held}


def _run_structured_advisory(_monkeypatch, inp: dict) -> dict:
    snapshot = state()
    catalog = fact_catalog(snapshot, field_id=FIELD)
    path = sorted(catalog)[0]
    published = catalog[path]
    claim = {
        "catalog": dict(published),
        "unknown_path": {**published, "path": "/weather/golden_eval_unpublished"},
        "altered_value": {**published, "value": published["value"] + 1},
    }[inp["claim"]]
    text = json.dumps(
        {
            "schema_version": ADVISORY_SCHEMA,
            "field_id": FIELD,
            "evidence_fingerprint": evidence_fingerprint(snapshot, field_id=FIELD),
            "claims": [claim],
            "candidate_ids": [],
        }
    )
    try:
        preview = asyncio.run(
            preview_advisory(text, tenant_id=TENANT, field_id=FIELD, state=snapshot, candidates=[])
        )
    except AdvisoryRejected as exc:
        return {"rejected": str(exc), "catalog": catalog}
    return {"published": preview, "catalog": catalog, "rejected": None}


def _run_tool_loop(_monkeypatch, inp: dict) -> dict:
    audits: list[dict] = []
    saved: list[dict] = []
    result = tool_loop.run_tool_calls(
        inp["tool_calls"],
        allowed_capabilities=inp["allowed_capabilities"],
        fetcher=None,
        tenant_id=TENANT,
        actor="golden-eval",
        timestamp="2026-11-22T00:00:00Z",
        audit_saver=audits.append,
        approval_saver=saved.append,
        allowed_tools=None,
    )
    response = {
        **_QUIET_RESPONSE,
        "tool_calls": result["tool_calls"],
        "pending_approvals": result["pending_approvals"],
    }
    return {
        "tool_calls": result["tool_calls"],
        "pending": result["pending_approvals"],
        "envelope": build_advisory_envelope(response),
        "response": response,
    }


def _run_envelope(_monkeypatch, inp: dict) -> dict:
    response = {**_QUIET_RESPONSE, **inp["response"]}
    return {"envelope": build_advisory_envelope(response), "response": response}


RUNNERS = {
    "runtime": _run_runtime,
    "approval_gate": _run_approval_gate,
    "structured_advisory": _run_structured_advisory,
    "tool_loop": _run_tool_loop,
    "envelope": _run_envelope,
}


# ── checks: one per expectation key; every key in the cases file must be one of these ─────────
def _env(obs: dict) -> dict:
    envelope = obs.get("envelope")
    assert isinstance(envelope, dict), f"no advisory envelope in {obs.get('response')!r}"
    return envelope


def _codes(obs: dict) -> list[str]:
    env = _env(obs)
    return [*env["evidence_missing"], *env["limitations"]]


def _published_texts(obs: dict) -> list[str]:
    texts = []
    response = obs.get("response") or {}
    for key in ("answer_ar", "message"):
        if isinstance(response.get(key), str):
            texts.append(response[key])
    if isinstance(obs.get("envelope"), dict):
        texts.append(obs["envelope"]["summary"])
    validation = response.get("advisory_validation")
    if isinstance(validation, dict) and isinstance(validation.get("answer_ar"), str):
        texts.append(validation["answer_ar"])
    if isinstance(obs.get("published"), dict):
        texts.append(obs["published"]["answer_ar"])
    assert texts, "the case published no text to check"
    return texts


def _golden_pointer(obs: dict) -> dict:
    held = (obs["response"].get("annotations") or {}).get("unverified_seed_references") or []
    pointers = [p for p in held if p.get("chunk_id") == GOLDEN_EXCERPT["chunk_id"]]
    assert len(pointers) == 1, f"the retrieved excerpt is not held exactly once: {held!r}"
    return pointers[0]


def _assert_citable_without_text(pointer: dict) -> None:
    assert pointer.get("document_id") == GOLDEN_EXCERPT["document_id"], pointer
    assert pointer.get("source_revision") == GOLDEN_EXCERPT["source_revision"], pointer
    assert pointer.get("content_digest") == reference_approvals.content_digest(
        GOLDEN_EXCERPT["text"]
    ), pointer
    assert not {"text", "content", "snippet"} & set(pointer), pointer


def check_http_status(obs, expected, _case):
    assert obs["status_code"] == expected, obs["response"]


def check_error_detail(obs, expected, _case):
    assert obs["response"].get("detail") == expected, obs["response"]


def check_downstream_calls(obs, expected, _case):
    assert obs["downstream_calls"] == expected, obs


def check_abstains(obs, expected, _case):
    env = _env(obs)
    response = obs["response"]
    abstained = (
        env["evidence_used"] == []
        and "no_grounding_evidence" in env["evidence_missing"]
        and response.get("generation_surfaced") is False
        and not (response.get("advisory_validation") or {}).get("claims")
    )
    assert abstained is expected, env


def check_requires_human_review(obs, expected, _case):
    assert _env(obs)["requires_human_review"] is expected, _env(obs)


def check_decision(obs, expected, _case):
    assert _env(obs)["decision"] == expected, _env(obs)


def check_evidence_missing_include(obs, expected, _case):
    missing = _env(obs)["evidence_missing"]
    assert set(expected) <= set(missing), missing


def check_limitations_include(obs, expected, _case):
    limitations = _env(obs)["limitations"]
    assert set(expected) <= set(limitations), limitations


def check_names_code_containing(obs, expected, _case):
    codes = _codes(obs)
    for fragment in expected:
        assert any(fragment in code for code in codes), f"no code names {fragment!r}: {codes}"


def check_generation_surfaced(obs, expected, _case):
    assert obs["response"].get("generation_surfaced") is expected, obs["response"]


def check_no_dose_or_product_name(obs, expected, case):
    assert expected is True
    terms = [t.casefold() for t in case["agronomist_review"]["forbidden_product_terms"]]
    for text in _published_texts(obs):
        assert not _DOSE.search(text), f"dose-shaped text was published: {text!r}"
        assert not [t for t in terms if t in text.casefold()], f"product name published: {text!r}"


def check_hold_reason(obs, expected, _case):
    assert obs["usable"] == [], obs
    assert len(obs["held"]) == 1, obs
    assert obs["held"][0]["generation_hold_reason"] == expected, obs["held"]


def check_held_pointer_citable_without_text(obs, expected, _case):
    assert expected is True
    _assert_citable_without_text(obs["held"][0])


def check_runtime_hold_reason(obs, expected, _case):
    pointer = _golden_pointer(obs)
    assert pointer.get("generation_hold_reason") == expected, pointer


def check_held_reference_not_cited(obs, expected, _case):
    assert expected is True
    response = obs["response"]
    _assert_citable_without_text(_golden_pointer(obs))
    assert GOLDEN_EXCERPT["chunk_id"] not in response["evidence_ids"], response["evidence_ids"]
    assert GOLDEN_EXCERPT["text"] not in json.dumps(response, ensure_ascii=False)


def check_selected_imagery_date_carried(obs, expected, _case):
    response = obs["response"]
    assert response["selected_imagery_date"] == expected, response
    assert response["harness"]["sees"]["selected_date"] == expected, response["harness"]
    assert obs["audit_kwargs"]["selected_imagery_date"] == expected, obs["audit_kwargs"]


def check_audit_status(obs, expected, _case):
    assert obs["response"]["audit_event"]["status"] == expected, obs["response"]["audit_event"]


def check_no_tool_executed(obs, expected, _case):
    assert expected is True
    calls = obs["tool_calls"]
    assert calls, "the case expected a tool-call record"
    assert [c for c in calls if c.get("outcome") == "executed"] == [], calls


def check_tool_outcomes(obs, expected, _case):
    assert [c.get("outcome") for c in obs["tool_calls"]] == expected, obs["tool_calls"]


def check_pending_approvals_undecided(obs, expected, _case):
    pending = obs["pending"]
    assert len(pending) == expected, pending
    for request in pending:
        assert request["status"] == "pending", request
        assert request["decided_by"] is None and request["decided_at"] is None, request
    proposed = [c for c in obs["tool_calls"] if c.get("outcome") == "pending_approval"]
    assert len(proposed) == expected and all(c["data"] is None for c in proposed), proposed


def check_rejected_with(obs, expected, _case):
    assert obs["rejected"] == expected, obs


def check_every_published_fact_cited(obs, expected, _case):
    assert expected is True
    published, catalog = obs["published"], obs["catalog"]
    assert published["claims"], "nothing was published"
    for fact in published["claims"]:
        assert set(fact) == {"path", "value", "product_digest"}, fact
        assert catalog.get(fact["path"]) == fact, fact
    lines = published["answer_ar"].splitlines()
    assert len(lines) == len(published["claims"]), lines
    for line, fact in zip(lines, published["claims"], strict=True):
        assert fact["path"] in line, line
    assert published["executes_action"] is False and published["creates_decision"] is False


def check_model_text_not_published(obs, expected, _case):
    for text in _published_texts(obs):
        assert expected not in text, text


CHECKS = {
    name.removeprefix("check_"): fn
    for name, fn in list(globals().items())
    if name.startswith("check_") and callable(fn)
}


# ── the cases ────────────────────────────────────────────────────────────────────────────────
def _params():
    params = []
    for case in load_cases()["cases"]:
        marks = []
        gap = case.get("known_gap")
        if gap:
            marks.append(
                pytest.mark.xfail(
                    strict=True, raises=AssertionError, reason=f"{gap['id']}: {gap['summary']}"
                )
            )
        params.append(pytest.param(case, id=case["id"], marks=marks))
    return params


@pytest.mark.parametrize("case", _params())
def test_golden_case(case, monkeypatch):
    case = {**case, "input": _substitute(case["input"])}
    obs = RUNNERS[case["layer"]](monkeypatch, case["input"])
    for key, expected in case["expect"].items():
        CHECKS[key](obs, expected, case)


# ── the cases file itself ────────────────────────────────────────────────────────────────────
def test_cases_file_is_versioned_and_well_formed():
    document = load_cases()
    assert document["schema"] == CASES_SCHEMA
    assert type(document["schema_version"]) is int
    assert document["schema_version"] == CASES_SCHEMA_VERSION
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", document["cases_revision"])
    assert document["runner"] == "tests_v9/golden_advisor/" + Path(__file__).name
    ids = [case["id"] for case in document["cases"]]
    assert len(ids) == len(set(ids)), "case ids must be unique"
    for case in document["cases"]:
        where = case["id"]
        assert set(case) == {
            "id",
            "category",
            "layer",
            "description",
            "input",
            "expect",
            "known_gap",
            "agronomist_review",
        }, where
        assert case["category"] in REQUIRED_CATEGORIES, where
        assert case["layer"] in LAYERS, where
        assert case["expect"], f"{where} checks nothing"
        unknown = set(case["expect"]) - set(CHECKS)
        assert not unknown, f"{where} expects keys no check reads: {sorted(unknown)}"
        gap = case["known_gap"]
        if gap is not None:
            assert set(gap) == {"id", "summary"}, where
            assert re.fullmatch(r"[A-Z0-9][A-Z0-9-]+", gap["id"]), where
            assert gap["summary"].strip(), where


def test_every_required_behaviour_has_a_case_that_runs_green():
    cases = load_cases()["cases"]
    assert {case["category"] for case in cases} == REQUIRED_CATEGORIES
    green = {case["category"] for case in cases if case["known_gap"] is None}
    assert green == REQUIRED_CATEGORIES, sorted(REQUIRED_CATEGORIES - green)


def test_agronomist_slots_stay_empty_until_signed_off():
    """No gold answer, product list or reviewer is written here without an agronomist."""
    for case in load_cases()["cases"]:
        slot = case["agronomist_review"]
        assert set(slot) == AGRONOMIST_SLOTS, case["id"]
        assert slot["status"] in {"awaiting_sign_off", "signed_off"}, case["id"]
        assert isinstance(slot["forbidden_product_terms"], list), case["id"]
        if slot["status"] == "awaiting_sign_off":
            assert slot["reference_answer_ar"] is None, case["id"]
            assert slot["forbidden_product_terms"] == [], case["id"]
            assert slot["reviewer"] is None and slot["reviewed_on"] is None, case["id"]
        else:
            assert isinstance(slot["reviewer"], str) and slot["reviewer"].strip(), case["id"]
            date.fromisoformat(slot["reviewed_on"])


def test_dose_check_is_not_vacuous():
    """The canned model text carries a dose-shaped token, so a leak would be caught twice."""
    texts = [
        case["input"]["generation"]["text"]
        for case in load_cases()["cases"]
        if case["layer"] == "runtime" and case["input"].get("generation")
    ]
    assert texts and all(_DOSE.search(text) for text in texts)
    assert not _DOSE.search("المصادر المتاحة: RAG، حالة الحقل.")
