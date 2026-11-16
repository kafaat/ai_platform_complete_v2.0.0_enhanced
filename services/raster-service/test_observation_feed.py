"""W1-11 (pull form) — raster's internal feed of published observations.

Owner decision of 2026-11-16: indicators-service pulls; raster-service exposes its outbox on two
service-to-service routes (``routers/observation_feed.py``) and never calls indicators-service.
Unit level, through the real app factory (its tenant middleware and router registration): the
service token, the tenant asserted in ``X-Tenant-Id`` reaching the store functions (and nothing
else), the acknowledgement contract and its request validation, and 503 when there is no
database. The outbox functions are stubbed at their function level here; their SQL (tenant
isolation under RLS FORCE, idempotent acknowledgement, payload mismatch, nothing deleted) is
measured on PostgreSQL in ``tests_v9/test_canonical_observations_live_pg.py``.
"""

from __future__ import annotations

import db_persist
import observation_outbox
import pytest
import raster_settings
from fastapi.testclient import TestClient
from raster_app_factory import create_raster_app

pytestmark = pytest.mark.unit

TENANT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
TOKEN = "svc-token"
DIGEST = "a" * 64
FEED = "/internal/v1/observation-outbox"
ACK = f"{FEED}/acknowledgements"


@pytest.fixture
def feed(monkeypatch):
    state = {"pending_calls": [], "ack_calls": [], "raise": None, "entries": []}

    async def _pending(tenant_id, *, limit, after_id):
        state["pending_calls"].append((tenant_id, limit, after_id))
        if state["raise"] is not None:
            raise state["raise"]
        return state["entries"]

    async def _ack(tenant_id, entries):
        state["ack_calls"].append((tenant_id, entries))
        if state["raise"] is not None:
            raise state["raise"]
        return [{"id": e["id"], "result": "acknowledged", "status": e["outcome"]} for e in entries]

    monkeypatch.setattr(raster_settings, "AGENT_TOKEN", TOKEN)
    monkeypatch.setattr(db_persist, "DATABASE_URL", "postgresql://stub/for-tests")
    monkeypatch.setattr(observation_outbox, "pending_entries", _pending)
    monkeypatch.setattr(observation_outbox, "acknowledge", _ack)
    app = create_raster_app(title="t", version="v", lifespan=None, cors_origins=[])
    state["client"] = TestClient(app)
    return state


def _headers(tenant=TENANT, token=TOKEN):
    headers = {}
    if tenant is not None:
        headers["X-Tenant-Id"] = tenant
    if token is not None:
        headers["X-Agent-Token"] = token
    return headers


def _ack_body(**overrides):
    entry = {"id": 7, "payload_sha256": DIGEST, "outcome": "delivered"}
    entry.update(overrides)
    return {"entries": [entry]}


def test_both_routes_are_on_the_auto_registered_router():
    from routers import observation_feed

    paths = {(next(iter(r.methods)), r.path) for r in observation_feed.router.routes}
    assert paths == {("GET", FEED), ("POST", ACK)}, paths


@pytest.mark.parametrize("token", [None, "guessed"])
def test_the_feed_and_the_acknowledgement_require_the_service_token(feed, token):
    client = feed["client"]
    assert client.get(FEED, headers=_headers(token=token)).status_code == 401
    assert client.post(ACK, json=_ack_body(), headers=_headers(token=token)).status_code == 401
    assert feed["pending_calls"] == [] and feed["ack_calls"] == [], "nothing reached the outbox"


def test_an_unconfigured_service_token_fails_closed(feed, monkeypatch):
    monkeypatch.setattr(raster_settings, "AGENT_TOKEN", "")
    assert feed["client"].get(FEED, headers=_headers(token="")).status_code == 503
    assert feed["pending_calls"] == []


def test_a_tenant_must_be_asserted_and_be_a_uuid(feed):
    client = feed["client"]
    assert client.get(FEED, headers=_headers(tenant=None)).status_code == 403
    assert client.post(ACK, json=_ack_body(), headers=_headers(tenant=None)).status_code == 403
    assert client.get(FEED, headers=_headers(tenant="not-a-uuid")).status_code == 400
    assert feed["pending_calls"] == [] and feed["ack_calls"] == []


def test_a_query_tenant_hint_cannot_switch_tenant(feed):
    response = feed["client"].get(FEED, params={"tenant_id": OTHER}, headers=_headers())
    assert response.status_code == 403, "the middleware refuses a hint for another tenant"
    assert feed["pending_calls"] == []


def test_the_feed_reads_only_the_asserted_tenant(feed):
    feed["entries"] = [
        {"id": 3, "payload": {"tenant_id": TENANT}, "payload_sha256": DIGEST, "created_at": "x"}
    ]
    response = feed["client"].get(
        FEED, params={"limit": 5, "after_id": 2}, headers=_headers(tenant=OTHER)
    )
    assert response.status_code == 200, response.text
    assert feed["pending_calls"] == [(OTHER, 5, 2)], "the asserted tenant, no other"
    body = response.json()
    assert body["tenant_id"] == OTHER and body["next_after_id"] == 3, body


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"after_id": -1}])
def test_the_feed_is_bounded(feed, params):
    assert feed["client"].get(FEED, params=params, headers=_headers()).status_code == 422
    assert feed["pending_calls"] == []


def test_an_acknowledgement_names_entries_for_the_asserted_tenant(feed):
    body = {
        "entries": [
            {"id": 7, "payload_sha256": DIGEST, "outcome": "delivered"},
            {"id": 8, "payload_sha256": "b" * 64, "outcome": "conflict", "detail": "stored x"},
        ]
    }
    response = feed["client"].post(ACK, json=body, headers=_headers())
    assert response.status_code == 200, response.text
    [(tenant, entries)] = feed["ack_calls"]
    assert tenant == TENANT, tenant
    assert [(e["id"], e["outcome"]) for e in entries] == [(7, "delivered"), (8, "conflict")]
    assert [r["result"] for r in response.json()["results"]] == ["acknowledged"] * 2


@pytest.mark.parametrize(
    "body",
    [
        {"entries": []},
        _ack_body(outcome="pending"),  # only a settled outcome may be set
        _ack_body(outcome="deleted"),
        _ack_body(payload_sha256="not-a-digest"),
        _ack_body(id=0),
        _ack_body(unexpected=1),
        {"entries": [{"id": 7, "outcome": "delivered"}]},  # the content must be named
        {
            "entries": [
                {"id": 7, "payload_sha256": DIGEST, "outcome": "delivered"},
                {"id": 7, "payload_sha256": DIGEST, "outcome": "conflict"},
            ]
        },
    ],
)
def test_an_invalid_acknowledgement_settles_nothing(feed, body):
    response = feed["client"].post(ACK, json=body, headers=_headers())
    assert response.status_code == 422, (body, response.status_code)
    assert feed["ack_calls"] == [], "nothing reached the outbox"


def test_without_a_database_both_routes_answer_503(feed, monkeypatch):
    monkeypatch.setattr(db_persist, "DATABASE_URL", "")
    client = feed["client"]
    assert client.get(FEED, headers=_headers()).status_code == 503
    assert client.post(ACK, json=_ack_body(), headers=_headers()).status_code == 503
    assert feed["pending_calls"] == [] and feed["ack_calls"] == []


def test_an_unavailable_outbox_is_503_never_an_empty_success(feed):
    feed["raise"] = observation_outbox.OutboxUnavailable("down")
    client = feed["client"]
    assert client.get(FEED, headers=_headers()).status_code == 503
    assert client.post(ACK, json=_ack_body(), headers=_headers()).status_code == 503


# ── how an acknowledgement that changed nothing is reported ─────────────────────────────────
@pytest.mark.parametrize(
    ("row", "outcome", "expected"),
    [
        (None, "delivered", "not_found"),
        ({"status": "delivered", "payload_sha256": DIGEST}, "delivered", "already_acknowledged"),
        ({"status": "conflict", "payload_sha256": DIGEST}, "delivered", "status_mismatch"),
        ({"status": "pending", "payload_sha256": "b" * 64}, "delivered", "payload_mismatch"),
    ],
)
def test_an_acknowledgement_that_changed_nothing_says_why(row, outcome, expected):
    result = observation_outbox._ack_result(7, outcome, row, DIGEST)
    assert result["result"] == expected, result
