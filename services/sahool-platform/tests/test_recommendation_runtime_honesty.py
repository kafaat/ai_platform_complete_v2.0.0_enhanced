"""The guarded recommendation path must not claim what it did not do (unit F7).

Two audit findings on ``api/routers/recommendations.py::_run_guarded_runtime_pipeline``
(flag ``ENABLE_RUNTIME_PIPELINE_CONSUMER``, OFF by default):

A. The path read ``canonical_field_state`` on the tenant connection and then called the
   engine with the ORIGINAL request. Changing ``depletion_mm`` from 10 to 120 left the
   engine input identical — the state that was read never reached the computation.
B. The pipeline was built with its in-memory defaults (an event publisher that keeps a
   list and returns success, an in-memory review repository) and the path reported
   ``events_published=2`` and a ``review_id`` although nothing was sent or stored.

These tests run the real pipeline and the router's own engine/outcome helpers. No
connection, pool or connection supplier is replaced: the DB read is the caller's job,
and the helpers under test receive the state as a plain value.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from api.routers import recommendations as rec_router
from core.api_adapter import ApiRequest, ApiResponse
from core.canonical_schemas import UserRole, UserSchema

from shared.ai.recommendation_runtime.human_review_repository import InMemoryReviewRepository
from shared.ai.recommendation_runtime.recommendation_events import RecommendationEventPublisher
from shared.ai.recommendation_runtime.recommendation_runtime_pipeline import (
    RecommendationRuntimePipeline,
)

pytestmark = pytest.mark.unit

ROUTER = Path(__file__).resolve().parents[1] / "api" / "routers" / "recommendations.py"
TENANT = "t-f7"
FIELD = "fld-f7"


def _state(depletion_mm: float) -> dict:
    return {
        "schema_version": "canonical_field_state.v1",
        "tenant_id": TENANT,
        "field_id": FIELD,
        "water": {"depletion_mm": depletion_mm},
    }


def _api_request() -> ApiRequest:
    user = UserSchema(user_id="u-f7", tenant_id=TENANT, role=UserRole.AGRONOMIST, name_ar="م")
    return ApiRequest(
        user=user,
        payload={
            "tenant_id": TENANT,
            "farm_id": "farm-f7",
            "field_id": FIELD,
            "crop": "wheat",
            "validation": {"quality_grade": "READY"},
        },
        path="/api/v1/recommendations/for-field",
        method="POST",
    )


async def _run_router_engine(monkeypatch, depletion_mm: float) -> tuple[list[dict], list]:
    """Run the real pipeline with the router's engine; return engine inputs and errors."""
    engine_inputs: list[dict] = []

    def _recording_engine(api_req):
        engine_inputs.append(dict(api_req.payload))
        return ApiResponse(status_code=200, body={"id": "rec-f7", "delivered": True})

    monkeypatch.setattr(rec_router, "handle_recommendation_request", _recording_engine)
    errors: list = []
    try:
        await RecommendationRuntimePipeline().execute(
            tenant_id=TENANT,
            field_id=FIELD,
            context={
                "canonical_field_state": _state(depletion_mm),
                "signals": {},
                "tool_outputs": {},
            },
            recommendation_engine=rec_router._runtime_engine(
                SimpleNamespace(crop="wheat", field_id=FIELD), _api_request()
            ),
            intent="general",
        )
    except Exception as exc:  # noqa: BLE001 — recorded, then asserted on below
        errors.append(exc)
    return engine_inputs, errors


# ── Claim A: the engine computes from the state that was read, or the path refuses ──


async def test_the_engine_never_computes_without_the_state_that_was_read(monkeypatch) -> None:
    low_inputs, low_errors = await _run_router_engine(monkeypatch, 10)
    high_inputs, high_errors = await _run_router_engine(monkeypatch, 120)

    for depletion, inputs in ((10, low_inputs), (120, high_inputs)):
        for payload in inputs:
            assert payload.get("canonical_field_state") == _state(depletion), (
                f"the engine computed without the canonical state that was read "
                f"(depletion_mm={depletion}); engine input keys: {sorted(payload)}"
            )
    if low_inputs and high_inputs:
        assert low_inputs != high_inputs, (
            "depletion_mm 10 -> 120 left the engine input identical: "
            "the state that was read does not reach the computation"
        )
        return
    # The engine was not invoked: that is only acceptable as an explicit refusal.
    refusal = rec_router.CanonicalStateNotPassedToEngine
    assert not low_inputs and not high_inputs
    assert [type(e) for e in (*low_errors, *high_errors)] == [refusal, refusal]


async def test_a_refused_run_publishes_no_event(monkeypatch) -> None:
    """The refusal happens before the pipeline's ``created`` event, so none is recorded."""
    publisher = RecommendationEventPublisher()
    monkeypatch.setattr(
        rec_router,
        "handle_recommendation_request",
        lambda _req: ApiResponse(status_code=200, body={"id": "rec-f7"}),
    )
    with pytest.raises(rec_router.CanonicalStateNotPassedToEngine):
        await RecommendationRuntimePipeline(event_publisher=publisher).execute(
            tenant_id=TENANT,
            field_id=FIELD,
            context={"canonical_field_state": _state(10), "signals": {}, "tool_outputs": {}},
            recommendation_engine=rec_router._runtime_engine(
                SimpleNamespace(crop="wheat", field_id=FIELD), _api_request()
            ),
        )
    assert publisher.published == []


def test_the_refusal_says_the_state_was_not_passed_and_claims_nothing() -> None:
    status_code, payload = rec_router._runtime_refusal_outcome()
    runtime = payload["runtime_pipeline"]
    assert status_code == 501
    assert runtime["status"] == "refused_canonical_state_not_passed_to_engine"
    assert runtime["canonical_field_state_passed_to_engine"] is False
    assert runtime["events_published"] == 0
    assert runtime["event_delivery"] == "not_published"
    assert runtime["review_id"] is None
    assert "recommendation" not in payload and "delivered" not in payload


def test_the_refusal_is_answered_not_swallowed_into_the_legacy_fallback() -> None:
    """The refusal handler comes before the generic fallback that returns ``None``."""
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    helper = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_run_guarded_runtime_pipeline"
    )
    handlers = [
        handler
        for node in ast.walk(helper)
        if isinstance(node, ast.Try)
        for handler in node.handlers
    ]
    names = [ast.unparse(h.type) if h.type is not None else "" for h in handlers]
    assert names and names[0] == "CanonicalStateNotPassedToEngine", names
    assert "Exception" in names[1:], names


def test_the_refusal_precondition_still_holds() -> None:
    """The refusal exists because the engine has no input for the canonical state.

    If ``orchestrate_recommendation`` or the adapter gains one, this goes red: pass the
    state to it in ``_runtime_engine`` and lift the refusal in the same change.
    """
    from core import api_adapter
    from core.internal_orchestrator import orchestrate_recommendation

    assert "canonical_field_state" not in inspect.signature(orchestrate_recommendation).parameters
    assert "canonical_field_state" not in inspect.getsource(
        api_adapter.handle_recommendation_request
    )


# ── Claim B: in-memory defaults report nothing published and nothing persisted ──


def _high_risk_engine(_prepared: dict) -> dict:
    return {"id": "rec-f7", "type": "general", "risk_level": "high", "status_code": 200, "body": {}}


async def test_in_memory_defaults_report_nothing_published_or_persisted() -> None:
    result = await RecommendationRuntimePipeline().execute(
        tenant_id=TENANT,
        field_id=FIELD,
        context={"canonical_field_state": _state(10), "signals": {}, "tool_outputs": {}},
        recommendation_engine=_high_risk_engine,
    )
    _status, payload = rec_router._runtime_pipeline_outcome(result)
    runtime = payload["runtime_pipeline"]
    assert runtime["events_published"] == 0, (
        f"events_published={runtime['events_published']} with no broker client: "
        "the in-memory publisher only appended to a list"
    )
    assert runtime.get("event_delivery") == "not_published", runtime
    assert runtime["review_id"] is None, (
        "a review_id was reported for a review held only in process memory"
    )
    assert runtime.get("review_persistence") == "not_persisted", runtime


async def test_the_pipeline_result_carries_delivery_and_persistence_states() -> None:
    result = await RecommendationRuntimePipeline().execute(
        tenant_id=TENANT,
        field_id=FIELD,
        context={"canonical_field_state": _state(10), "signals": {}, "tool_outputs": {}},
        recommendation_engine=_high_risk_engine,
    )
    assert result.event_delivery == "not_published"
    assert result.review_persistence == "not_persisted"
    # The witness: the review lives only in the instance that created it.
    assert InMemoryReviewRepository().get_review(result.review_id) is None


async def test_a_wired_broker_client_is_reported_as_published() -> None:
    """The state is derived from the publisher, not hard-coded to ``not_published``."""
    sent: list[str] = []

    class _BrokerClient:
        async def publish(self, subject: str, data: bytes) -> None:
            sent.append(subject)

    publisher = RecommendationEventPublisher(client=_BrokerClient(), enabled=True)
    result = await RecommendationRuntimePipeline(event_publisher=publisher).execute(
        tenant_id=TENANT,
        field_id=FIELD,
        context={"canonical_field_state": _state(10), "signals": {}, "tool_outputs": {}},
        recommendation_engine=_high_risk_engine,
    )
    _status, payload = rec_router._runtime_pipeline_outcome(result)
    assert sent == ["recommendation.created", "recommendation.review_required"]
    assert payload["runtime_pipeline"]["event_delivery"] == "published"
    assert payload["runtime_pipeline"]["events_published"] == 2
    # The review store is still in memory, so the review is still not persisted.
    assert payload["runtime_pipeline"]["review_persistence"] == "not_persisted"
    assert payload["runtime_pipeline"]["review_id"] is None
