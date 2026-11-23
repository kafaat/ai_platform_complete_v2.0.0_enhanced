"""F8 — the advisor chat shows stored owner-engine proposals, for specialist review only.

Audit L157: ``model_selection_context`` received ``candidates=[]`` and the platform's
owner-candidate loader returned ``[]``, so the chat never showed an engine proposal.
Owner decision: link the advisor to the existing irrigation/fertiliser engines for REVIEW
ONLY. These tests pin that:

* flag off (the default) → an empty list with ``feature_flag_off``, and no platform read;
* a stored, current owner proposal → returned with its full provenance and
  ``requires_human_review: true``, amounts copied from the stored record;
* another tenant's / expired / malformed / blocked records → withheld with reason codes;
* no stored proposal → an empty list with reason codes;
* the model still receives no candidate catalog (it cannot choose or alter an amount).

No database stand-in: rows are plain mappings fed to the pure projection, and the chat runs
through ``httpx.MockTransport``. The SQL path is proven on a live Postgres in
``test_f8_engine_proposals_live_pg.py``.
"""

from __future__ import annotations

import ast
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from services.ai_agronomist import ai_evidence_runtime as runtime
from services.ai_agronomist import engine_proposal_client as client
from tests_v9.test_b6m4_structured_advisory import FIELD, TENANT, state

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CORE = str(ROOT / "services" / "sahool-platform")
OTHER_TENANT = "00000000-0000-0000-0000-000000000202"
_REAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.fixture(scope="module")
def review_mod():
    from shared.ai import engine_proposal_review as module

    return module


@pytest.fixture(scope="module")
def internal_service():
    added = CORE not in sys.path
    if added:
        sys.path.insert(0, CORE)
    import api.main  # noqa: F401 — main first: it registers the routers it imports last
    from api.routers import internal_service as module

    yield module
    if added and CORE in sys.path:
        sys.path.remove(CORE)


def stored_row(tenant=TENANT, field=FIELD, *, now=None, **over):
    """One row shaped as ``hourly_irrigation_mpc_schedules`` returns it (values are fixtures)."""
    now = now or datetime.now(UTC)
    digest = over.pop("schedule_digest", "b" * 64)
    payload = {
        "schema_version": "hourly_energy_aware_irrigation_mpc.v1",
        "solver_version": "hourly-lex-mpc.v1",
        "tenant_id": tenant,
        "field_id": field,
        "decision": "irrigate",
        "status": "verified",
        "recommendation_only": True,
        "execution_allowed": False,
        "initial_depletion_mm": 12.5,
        "taw_mm": 80.0,
        "raw_mm": 40.0,
        "limitations": ["fixture_limitation"],
        "source_digests": {"water_state_digest": "a" * 64},
        "actions": [
            {
                "hour": "2026-11-22T10:00:00Z",
                "irrigation_depth_mm": 4.0,
                "irrigation_volume_m3": 40.0,
                "runtime_minutes": 30.0,
                "energy_cost": 1.5,
            }
        ],
        "schedule_digest": digest,
    }
    payload.update(over.pop("payload_over", {}))
    row = {
        "schedule_id": str(uuid.uuid4()),
        "tenant_id": tenant,
        "field_id": field,
        "season_id": "season-fixture",
        "solver_version": "hourly-lex-mpc.v1",
        "status": "verified",
        "recommendation_only": True,
        "execution_allowed": False,
        "horizon_start": now - timedelta(hours=1),
        "horizon_hours": 48,
        "initial_depletion_mm": 12.5,
        "required_refill_mm": 4.0,
        "scheduled_irrigation_mm": 4.0,
        "scheduled_volume_m3": 40.0,
        "schedule_digest": digest,
        "payload": json.dumps(payload),
        "created_at": now - timedelta(minutes=30),
    }
    row.update(over)
    return row


def platform_review(review_mod, rows, *, tenant=TENANT, field=FIELD):
    """What the platform branch returns for these rows (projection + envelope, no I/O)."""
    now = datetime.now(UTC)
    proposals, reasons = [], []
    for row in rows:
        proposal, reason = review_mod.project_irrigation_schedule(
            row, tenant_id=tenant, field_id=field, now=now
        )
        (proposals.append(proposal) if proposal else reasons.append(reason))
    if not rows:
        reasons.append("no_stored_owner_proposal")
    return {
        "engine_proposals": review_mod.review_envelope(
            tenant_id=tenant,
            field_id=field,
            enabled=True,
            proposals=proposals,
            reason_codes=reasons,
        )
    }


# ── The chat path (failing-first: before F8 there is no engine_proposals in the response) ──
def _chat(monkeypatch, platform_reply, seen):
    real = _REAL_ASYNC_CLIENT

    def transport(request):
        seen.append((request.url.path, dict(request.url.params)))
        if request.url.path == f"/internal/fields/{FIELD}/state":
            return httpx.Response(200, json=platform_reply)
        if request.url.path == "/v1/search":
            return httpx.Response(200, json={"annotations": []})
        return httpx.Response(200, json={"edges": []})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(transport), **kw)
    )
    monkeypatch.setattr(runtime, "AGENT_TOKEN", "agent-token-for-test")
    monkeypatch.setenv("PLATFORM_TENANT_ASSERTION_KEY", "k" * 32)
    monkeypatch.setattr(runtime, "_fetch_canonical_field_state", AsyncMock(return_value=state()))
    monkeypatch.setattr(runtime, "_generation_allowed", lambda _: False)
    monkeypatch.setattr(
        runtime, "_record_ai_advice_event", AsyncMock(return_value={"persisted": True})
    )
    from fastapi.testclient import TestClient

    from services.ai_agronomist import main

    resp = TestClient(main.app).post(
        "/v1/chat",
        json={"question": "ما حالة الحقل؟", "field_id": FIELD, "crop": "wheat"},
        headers={"X-Tenant-Id": TENANT},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_chat_shows_a_stored_owner_proposal_for_specialist_review(monkeypatch, review_mod):
    monkeypatch.setenv("SAHOOL_ADVISOR_ENGINE_PROPOSALS", "true")
    seen: list = []
    row = stored_row()
    body = _chat(monkeypatch, platform_review(review_mod, [row]), seen)
    review = body["engine_proposals"]
    assert review["enabled"] is True and review["read_only"] is True, review
    assert review["requires_human_review"] is True
    assert review["model_may_alter_amounts"] is False
    [proposal] = review["proposals"]
    assert proposal["status"] == "awaiting_specialist_review"
    assert proposal["requires_human_review"] is True
    assert proposal["approved"] is False and proposal["executable"] is False
    assert proposal["computed_in_request"] is False
    for key in (
        "input_snapshot",
        "units",
        "timestamps",
        "method",
        "limitations",
        "validity",
        "owning_service",
    ):
        assert proposal[key], key
    assert proposal["method"]["version"] == "hourly-lex-mpc.v1"
    assert proposal["owning_service"] == "sahool-platform"
    assert proposal["source_record"]["record_id"] == row["schedule_id"]
    # Amounts are the stored record's, verbatim — not recomputed, not model-chosen.
    assert proposal["amounts"] == {
        "scheduled_irrigation_mm": 4.0,
        "scheduled_volume_m3": 40.0,
        "required_refill_mm": 4.0,
    }
    assert proposal["units"]["scheduled_volume_m3"] == "m3"
    assert "energy_cost" not in proposal["actions"][0]
    # One read of the stored proposals; the request asks for nothing to be computed.
    asked = [p for path, p in seen if path == f"/internal/fields/{FIELD}/state"]
    assert asked == [{"tenant_id": TENANT, "engine_proposals": "true"}], seen


def test_flag_off_by_default_shows_nothing_and_reads_nothing(monkeypatch, review_mod):
    monkeypatch.delenv("SAHOOL_ADVISOR_ENGINE_PROPOSALS", raising=False)
    seen: list = []
    body = _chat(monkeypatch, platform_review(review_mod, [stored_row()]), seen)
    review = body["engine_proposals"]
    assert review["enabled"] is False
    assert review["proposals"] == []
    assert review["reason_codes"] == ["feature_flag_off"]
    assert not [s for s in seen if s[0] == f"/internal/fields/{FIELD}/state"], seen


def test_no_stored_proposal_is_an_empty_list_with_reason_codes(monkeypatch, review_mod):
    monkeypatch.setenv("SAHOOL_ADVISOR_ENGINE_PROPOSALS", "1")
    review = _chat(monkeypatch, platform_review(review_mod, []), [])["engine_proposals"]
    assert review["proposals"] == []
    assert "no_stored_owner_proposal" in review["reason_codes"], review


def test_the_model_still_receives_no_candidate_catalog():
    """The model must not choose an action: the selection context stays candidate-free."""
    tree = ast.parse(
        (ROOT / "services/ai_agronomist/ai_evidence_runtime.py").read_text(encoding="utf-8")
    )
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "model_selection_context"
    ]
    assert calls, "model_selection_context call site moved"
    for call in calls:
        candidates = {kw.arg: kw.value for kw in call.keywords}["candidates"]
        assert isinstance(candidates, ast.List) and not candidates.elts


# ── Platform projection (pure, plain-mapping rows) ──
def test_projection_withholds_records_that_are_not_reviewable(review_mod):
    now = datetime.now(UTC)
    cases = {
        "owner_record_scope_mismatch": stored_row(tenant=OTHER_TENANT, now=now),
        "owner_status_blocked": stored_row(now=now, status="blocked"),
        "owner_record_expired": stored_row(now=now, horizon_start=now - timedelta(hours=49)),
        "owner_record_integrity_mismatch": stored_row(now=now, payload_over={"field_id": "x"}),
        "owner_record_provenance_incomplete": stored_row(
            now=now, payload_over={"limitations": None}
        ),
        "owner_record_validity_missing": stored_row(now=now, horizon_start=None),
        "owner_record_not_recommendation_only": stored_row(now=now, execution_allowed=True),
    }
    for expected, row in cases.items():
        proposal, reason = review_mod.project_irrigation_schedule(
            row, tenant_id=TENANT, field_id=FIELD, now=now
        )
        assert proposal is None and reason == expected, (expected, reason)


async def test_platform_branch_with_flag_off_returns_before_any_database(
    monkeypatch, internal_service
):
    monkeypatch.delenv("SAHOOL_ADVISOR_ENGINE_PROPOSALS", raising=False)
    out = await internal_service._stored_engine_proposals(TENANT, FIELD)
    assert out["enabled"] is False and out["proposals"] == []
    assert out["reason_codes"] == ["feature_flag_off"]


def test_loader_sql_is_a_tenant_bound_select(internal_service):
    sql = internal_service._STORED_IRRIGATION_PROPOSALS_SQL
    assert sql.lstrip().upper().startswith("SELECT ")
    for word in ("INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE"):
        assert word not in sql.upper()
    assert "tenant_id = $1::uuid AND field_id = $2" in sql


# ── Runtime client contract (re-checks what the platform sends) ──
def test_client_drops_another_tenants_or_unreviewable_proposal(review_mod):
    now = datetime.now(UTC)
    mine = platform_review(review_mod, [stored_row(now=now)])["engine_proposals"]["proposals"][0]
    theirs = platform_review(review_mod, [stored_row(OTHER_TENANT, now=now)], tenant=OTHER_TENANT)
    theirs = theirs["engine_proposals"]["proposals"][0]
    approved = {**mine, "approved": True}
    no_review = {**mine, "requires_human_review": False}
    expired = {**mine, "validity": {**mine["validity"], "valid_until": "2000-01-01T00:00:00Z"}}
    payload = {
        "engine_proposals": review_mod.review_envelope(
            tenant_id=TENANT,
            field_id=FIELD,
            enabled=True,
            proposals=[theirs, approved, no_review, expired, mine],
        )
    }
    out = client.accept_review(payload, tenant_id=TENANT, field_id=FIELD, now=now)
    assert [p["proposal_id"] for p in out["proposals"]] == [mine["proposal_id"]]
    assert set(out["reason_codes"]) == {"owner_proposal_contract_invalid", "owner_proposal_expired"}


def test_client_rejects_an_envelope_for_another_tenant(review_mod):
    payload = platform_review(review_mod, [stored_row(OTHER_TENANT)], tenant=OTHER_TENANT)
    out = client.accept_review(payload, tenant_id=TENANT, field_id=FIELD, now=datetime.now(UTC))
    assert out["proposals"] == []
    assert out["reason_codes"] == ["owner_proposal_contract_invalid"]


async def test_client_degrades_on_platform_failure_without_reflecting_it(monkeypatch):
    monkeypatch.setenv("SAHOOL_ADVISOR_ENGINE_PROPOSALS", "on")
    real = _REAL_ASYNC_CLIENT
    transport = httpx.MockTransport(lambda r: httpx.Response(503, text="SECRET_UPSTREAM"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    out = await client.fetch_engine_proposals(
        tenant_id=TENANT,
        field_id=FIELD,
        endpoint_mode="chat",
        platform_url="http://platform",
        agent_token="t",
        sign=lambda *_: {"X-Sig": "s"},
    )
    assert out["proposals"] == [] and out["reason_codes"] == ["owner_proposal_store_unavailable"]
    assert "SECRET_UPSTREAM" not in json.dumps(out)


async def test_client_only_reads_on_the_chat_endpoint(monkeypatch):
    monkeypatch.setenv("SAHOOL_ADVISOR_ENGINE_PROPOSALS", "true")
    out = await client.fetch_engine_proposals(
        tenant_id=TENANT,
        field_id=FIELD,
        endpoint_mode="query",
        platform_url="http://platform",
        agent_token="t",
        sign=lambda *_: pytest.fail("no read outside chat"),
    )
    assert out["reason_codes"] == ["endpoint_mode_not_chat"]


def test_flag_default_is_off(monkeypatch, review_mod):
    monkeypatch.delenv("SAHOOL_ADVISOR_ENGINE_PROPOSALS", raising=False)
    assert client.flag_enabled() is False
    assert review_mod.flag_enabled() is False
    assert client.FLAG_ENV == review_mod.FLAG_ENV == "SAHOOL_ADVISOR_ENGINE_PROPOSALS"


async def test_client_reads_nothing_for_the_voice_channel(monkeypatch):
    monkeypatch.setenv("SAHOOL_ADVISOR_ENGINE_PROPOSALS", "true")
    out = await client.fetch_engine_proposals(
        tenant_id=TENANT,
        field_id=FIELD,
        endpoint_mode="chat",
        platform_url="http://platform",
        agent_token="t",
        sign=lambda *_: pytest.fail("no read on the voice channel"),
        voice_read_only=True,
    )
    assert out["proposals"] == [] and out["reason_codes"] == ["voice_read_only_excluded"]
