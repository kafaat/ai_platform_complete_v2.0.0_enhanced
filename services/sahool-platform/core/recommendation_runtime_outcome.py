"""Outcome of the guarded recommendation runtime path (F7).

Moved out of ``api/routers/recommendations.py`` to keep the router under the size ceiling
(``tests/architecture/test_router_size_ratchet.py``); the router re-exports these names.
The path refuses rather than computing without the canonical field state it read, and its
answer never reports process-local events or reviews as published or saved.
"""

from __future__ import annotations

#: Status the guarded path answers with while the engine cannot take the canonical state.
RUNTIME_REFUSAL_STATUS = "refused_canonical_state_not_passed_to_engine"


class CanonicalStateNotPassedToEngine(RuntimeError):
    """The guarded path read ``canonical_field_state`` but the engine has no input for it."""


def _runtime_engine(req, api_req):
    """The engine callable handed to the guarded pipeline — it refuses instead of computing.

    The pipeline hands it ``prepared["canonical_field_state"]``, the state read on the
    tenant connection. The production engine cannot take that state: neither
    ``handle_recommendation_request`` nor ``orchestrate_recommendation`` has an input for
    it (pinned by ``test_the_refusal_precondition_still_holds``). Calling the engine with
    ``api_req`` therefore computed a recommendation WITHOUT the state that was read —
    ``depletion_mm`` 10 or 120 gave an identical engine input — while the path presented
    it as the guarded, state-backed result. Until the engine gains such an input, this
    callable raises before the engine runs, so no recommendation and no event is produced.
    """
    del req, api_req  # kept in the signature: the engine call they feed is not wired yet

    def _engine(prepared: dict) -> dict:
        raise CanonicalStateNotPassedToEngine(
            "the recommendation engine has no input for canonical_field_state; "
            "refusing rather than computing without the state that was read"
        )

    return _engine


def _runtime_refusal_outcome() -> tuple[int, dict]:
    """The explicit answer when the engine could not be given the state that was read."""
    return 501, {
        "runtime_pipeline": {
            "status": RUNTIME_REFUSAL_STATUS,
            "canonical_field_state_passed_to_engine": False,
            "review_id": None,
            "review_persistence": None,
            "events_published": 0,
            "event_delivery": "not_published",
        },
        "detail": (
            "The guarded recommendation path read the canonical field state, but the "
            "recommendation engine has no input for it, so no recommendation was computed."
        ),
    }


def _runtime_pipeline_outcome(result) -> tuple[int, dict]:
    """Map a pipeline result to the HTTP status and body this path returns.

    Events count as published only when the publisher handed them to a broker, and a
    review id is reported only when the review store is durable. With the process-local
    defaults the body says ``not_published`` / ``not_persisted`` instead of claiming
    ``events_published=2`` and a ``review_id`` that no other process can find.
    """
    recommendation = result.recommendation or {}
    published = result.event_delivery == "published"
    persisted = result.review_persistence == "persisted"
    payload = {
        "runtime_pipeline": {
            "status": result.status,
            "review_id": result.review_id if persisted else None,
            "review_persistence": result.review_persistence,
            "events_published": result.events_published if published else 0,
            "event_delivery": result.event_delivery,
        },
        **(recommendation.get("body") or {}),
    }
    status_code = int(recommendation.get("status_code") or 200)
    if result.status == "blocked_missing_field_state":
        status_code = 422
    return status_code, payload
