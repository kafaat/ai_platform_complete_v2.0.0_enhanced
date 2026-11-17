"""W1-11 (pull form, owner decision 2026-11-16) — the canonical observation drain.

indicators-service pulls each tenant's pending published observations from raster-service's
outbox feed, stores each one through the one store path, and acknowledges only what it settled.
Unit level: raster's feed is an in-memory HTTP stand-in (``httpx.MockTransport``) that applies the
feed contract (pending only, acknowledgement from pending at the named digest), and
``observation_store.insert_observation`` is stubbed at its function level. The same pull runs
against the real raster routes and a real PostgreSQL in
``tests_v9/test_canonical_observations_live_pg.py``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

MODULE_PATH = Path(__file__).resolve().parents[1] / "main.py"
spec = importlib.util.spec_from_file_location("indicators_service_main_drain", MODULE_PATH)
assert spec and spec.loader
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)

import observation_drain  # noqa: E402  (main.py put the service dir on sys.path)
import observation_store  # noqa: E402

TENANT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
TOKEN = "test-mesh-token"
RASTER = "http://raster.test"
PUBLISHED = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)


def _payload(tenant=TENANT, **overrides):
    body = {
        "schema_version": "sahool.published_observation/1",
        "tenant_id": tenant,
        "field_id": "fld_a",
        "indicator": "ndvi",
        "scene_id": "S2A_TEST_SCENE",
        "acquired_at": "2026-10-15T07:35:29+00:00",
        "stats": {"mean": 0.61},
        "valid_pixel_ratio": 0.91,
        "quality_gate_passed": True,
        "algorithm_version": "2.1.0",
        "qa_mask_version": "scl-v1",
        "product_identity_key": "pik_1",
        "geometry_revision": 3,
    }
    body.update(overrides)
    return body


class FakeRasterFeed:
    """raster's two feed routes over an in-memory outbox, per tenant."""

    def __init__(self):
        self.rows: dict[str, list[dict]] = {}
        self.requests: list[httpx.Request] = []
        self.fail_feed: int | None = None
        self.fail_ack: int | None = None
        self.next_id = 1

    def add(self, tenant, payload, digest=None):
        row = {
            "id": self.next_id,
            "payload": payload,
            "payload_sha256": digest or f"{self.next_id:064x}",
            "status": "pending",
            "detail": None,
        }
        self.next_id += 1
        self.rows.setdefault(tenant, []).append(row)
        return row

    def status(self, tenant):
        return [(r["id"], r["status"]) for r in self.rows.get(tenant, [])]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        tenant = request.headers.get("X-Tenant-Id")
        if request.headers.get("X-Agent-Token") != TOKEN:
            return httpx.Response(401)
        if request.url.path == observation_drain.FEED_PATH and request.method == "GET":
            if self.fail_feed is not None:
                return httpx.Response(self.fail_feed)
            limit = int(request.url.params["limit"])
            after = int(request.url.params["after_id"])
            entries = [
                {k: r[k] for k in ("id", "payload", "payload_sha256")}
                for r in self.rows.get(tenant, [])
                if r["status"] == "pending" and r["id"] > after
            ][:limit]
            return httpx.Response(200, json={"tenant_id": tenant, "entries": entries})
        if request.url.path == observation_drain.ACK_PATH and request.method == "POST":
            if self.fail_ack is not None:
                return httpx.Response(self.fail_ack)
            results = []
            for ack in json.loads(request.content)["entries"]:
                row = next((r for r in self.rows.get(tenant, []) if r["id"] == ack["id"]), None)
                if row is None:
                    results.append({"id": ack["id"], "result": "not_found"})
                elif row["payload_sha256"] != ack["payload_sha256"]:
                    results.append({"id": ack["id"], "result": "payload_mismatch"})
                elif row["status"] == "pending":
                    row["status"], row["detail"] = ack["outcome"], ack.get("detail")
                    results.append({"id": ack["id"], "result": "acknowledged"})
                elif row["status"] == ack["outcome"]:
                    results.append({"id": ack["id"], "result": "already_acknowledged"})
                else:
                    results.append({"id": ack["id"], "result": "status_mismatch"})
            return httpx.Response(200, json={"results": results})
        return httpx.Response(404)

    def acks(self):
        return [json.loads(r.content)["entries"] for r in self.requests if r.method == "POST"]


@pytest.fixture
def drain(monkeypatch):
    """Drain on, one tenant, token and store configured; the store stubbed."""
    raster = FakeRasterFeed()
    store = {"calls": [], "stored": {}, "down": False}

    async def _insert(record):
        store["calls"].append(record)
        if store["down"]:
            raise observation_store.StoreUnavailable("down")
        key = (str(record.tenant_id), record.observation_id(), record.revision_key())
        digest = record.content_sha256()
        if key not in store["stored"]:
            store["stored"][key] = digest
            status = "created"
        else:
            status = "replayed" if store["stored"][key] == digest else "conflict"
        return {
            "status": status,
            "observation_id": record.observation_id(),
            "revision_key": record.revision_key(),
            "payload_sha256": digest,
            "stored_payload_sha256": store["stored"][key],
            "published_at": PUBLISHED,
        }

    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_ENABLED", "true")
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_TENANTS", TENANT)
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_BATCH", "50")
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setenv("RASTER_SERVICE_URL", RASTER)
    monkeypatch.setenv("DATABASE_URL", "postgresql://stub/for-tests")
    monkeypatch.setattr(observation_store, "insert_observation", _insert)
    return raster, store


def _cycle(raster):
    return asyncio.run(observation_drain.run_cycle(transport=httpx.MockTransport(raster.handler)))


# ── the pull: store, then acknowledge what was stored ──────────────────────────────────────
def test_a_pending_entry_is_stored_then_acknowledged_delivered(drain):
    raster, store = drain
    row = raster.add(TENANT, _payload())
    assert _cycle(raster) == {"tenants": {TENANT: True}}
    assert len(store["calls"]) == 1, "one store call through the one store path"
    assert raster.acks() == [
        [{"id": row["id"], "payload_sha256": row["payload_sha256"], "outcome": "delivered"}]
    ], "the acknowledgement names the entry at the digest it read"
    assert raster.status(TENANT) == [(row["id"], "delivered")]
    assert _cycle(raster) == {"tenants": {TENANT: True}}
    assert len(store["calls"]) == 1, "nothing pending: nothing stored again"


def test_the_same_content_again_is_a_replay_and_still_delivered(drain):
    raster, store = drain
    raster.add(TENANT, _payload())
    raster.add(TENANT, _payload(cog_uri="s3://bucket/rewritten.tif"))  # delivery metadata only
    _cycle(raster)
    assert [s for _, s in raster.status(TENANT)] == ["delivered", "delivered"]
    assert observation_drain.state()["counters"]["replayed"] >= 1


def test_other_content_under_the_same_id_is_a_conflict_never_a_success(drain):
    raster, _store = drain
    first = raster.add(TENANT, _payload())
    clash = raster.add(TENANT, _payload(stats={"mean": 0.7}))
    before = observation_drain.state()["counters"]["conflict"]
    _cycle(raster)
    assert raster.status(TENANT) == [(first["id"], "delivered"), (clash["id"], "conflict")]
    [acks] = raster.acks()
    assert acks[1]["outcome"] == "conflict" and "observation_conflict" in acks[1]["detail"], acks
    assert observation_drain.state()["counters"]["conflict"] == before + 1


def test_an_unavailable_store_acknowledges_nothing_and_the_entry_stays_pending(drain):
    raster, store = drain
    row = raster.add(TENANT, _payload())
    store["down"] = True
    before = observation_drain.state()["counters"]["store_unavailable"]
    assert _cycle(raster) == {"tenants": {TENANT: False}}
    assert raster.acks() == [], "no acknowledgement for what was not stored"
    assert raster.status(TENANT) == [(row["id"], "pending")], "retried next cycle"
    state = observation_drain.state()
    assert state["counters"]["store_unavailable"] == before + 1
    assert state["last_cycle_ok"] is False, "the failure is visible on /readyz"
    store["down"] = False
    assert _cycle(raster) == {"tenants": {TENANT: True}}
    assert raster.status(TENANT) == [(row["id"], "delivered")], "the next cycle delivers it"


def test_only_the_entries_stored_are_acknowledged(drain, monkeypatch):
    raster, store = drain
    ok = raster.add(TENANT, _payload())
    later = raster.add(TENANT, _payload(scene_id="S2B_OTHER"))
    original = observation_store.insert_observation

    async def _fail_second(record):
        if record.scene_id == "S2B_OTHER":
            raise observation_store.StoreUnavailable("down")
        return await original(record)

    monkeypatch.setattr(observation_store, "insert_observation", _fail_second)
    _cycle(raster)
    assert [[a["id"] for a in batch] for batch in raster.acks()] == [[ok["id"]]]
    assert raster.status(TENANT) == [(ok["id"], "delivered"), (later["id"], "pending")]


def test_a_payload_the_store_refuses_is_rejected_and_the_page_goes_on(drain, monkeypatch):
    """A permanent refusal (``StoreRejected``: a data error or a constraint) settles the entry
    ``rejected`` with its detail; the next entry of the same page is still delivered, so one
    bad payload cannot hold the tenant's drain."""
    raster, store = drain
    bad = raster.add(TENANT, _payload(scene_id="S2B_BAD"))
    good = raster.add(TENANT, _payload())
    original = observation_store.insert_observation

    async def _refuse_bad(record):
        if record.scene_id == "S2B_BAD":
            raise observation_store.StoreRejected(
                "store refused the payload: CheckViolationError sqlstate=23514"
            )
        return await original(record)

    monkeypatch.setattr(observation_store, "insert_observation", _refuse_bad)
    before = observation_drain.state()["counters"]
    assert _cycle(raster) == {"tenants": {TENANT: True}}
    assert raster.status(TENANT) == [(bad["id"], "rejected"), (good["id"], "delivered")]
    [acks] = raster.acks()
    assert acks[0]["outcome"] == "rejected" and "CheckViolationError" in acks[0]["detail"], acks
    after = observation_drain.state()["counters"]
    assert after["rejected"] == before["rejected"] + 1
    assert after["store_unavailable"] == before["store_unavailable"], "not counted as down"


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        (_payload(stats={"mean": "0.61"}), "invalid payload"),  # decimal text never stored
        (_payload(acquired_at="2026-10-15T07:35:29"), "invalid payload"),
        (_payload(tenant=OTHER), "tenant_mismatch"),
    ],
)
def test_an_entry_that_is_not_a_valid_observation_is_rejected_unstored(drain, payload, detail):
    raster, store = drain
    row = raster.add(TENANT, payload)
    _cycle(raster)
    assert store["calls"] == [], "nothing invalid reaches the store"
    assert raster.status(TENANT) == [(row["id"], "rejected")]
    [[ack]] = raster.acks()
    assert ack["detail"].startswith(detail), ack
    assert "0.61" not in ack["detail"], "the offered values stay out of the detail"


@pytest.mark.parametrize("failure", ["status", "transport"])
def test_a_feed_that_cannot_answer_stores_nothing_and_is_counted(drain, failure):
    raster, store = drain
    raster.add(TENANT, _payload())
    before = observation_drain.state()["counters"]["fetch_failed"]
    if failure == "status":
        raster.fail_feed = 503
        transport = httpx.MockTransport(raster.handler)
    else:

        def boom(request):
            raise httpx.ConnectError("refused", request=request)

        transport = httpx.MockTransport(boom)
    result = asyncio.run(observation_drain.run_cycle(transport=transport))
    assert result == {"tenants": {TENANT: False}}
    assert store["calls"] == []
    assert observation_drain.state()["counters"]["fetch_failed"] == before + 1


def test_a_failed_acknowledgement_leaves_entries_pending_and_the_next_cycle_replays(drain):
    raster, store = drain
    row = raster.add(TENANT, _payload())
    raster.fail_ack = 503
    before = observation_drain.state()["counters"]["ack_failed"]
    assert _cycle(raster) == {"tenants": {TENANT: False}}
    assert raster.status(TENANT) == [(row["id"], "pending")]
    assert observation_drain.state()["counters"]["ack_failed"] == before + 1
    raster.fail_ack = None
    _cycle(raster)
    assert raster.status(TENANT) == [(row["id"], "delivered")]
    assert len(store["calls"]) == 2, "stored again: the idempotent store answers a replay"


def test_each_request_carries_the_token_and_only_its_tenant(drain, monkeypatch):
    raster, _store = drain
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_TENANTS", f"{OTHER},{TENANT}")
    mine = raster.add(TENANT, _payload())
    theirs = raster.add(OTHER, _payload(tenant=OTHER))
    _cycle(raster)
    for request in raster.requests:
        assert request.headers["X-Agent-Token"] == TOKEN
        assert str(request.url).startswith(RASTER)
    tenants = {r.headers["X-Tenant-Id"] for r in raster.requests}
    assert tenants == {TENANT, OTHER}
    assert raster.status(TENANT) == [(mine["id"], "delivered")]
    assert raster.status(OTHER) == [(theirs["id"], "delivered")]


def test_a_backlog_is_read_page_by_page(drain, monkeypatch):
    raster, store = drain
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_BATCH", "2")
    for n in range(5):
        raster.add(TENANT, _payload(scene_id=f"S{n}"))
    _cycle(raster)
    gets = [r for r in raster.requests if r.method == "GET"]
    assert [r.url.params["after_id"] for r in gets] == ["0", "2", "4"], gets
    assert all(s == "delivered" for _, s in raster.status(TENANT))


# ── the switches ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("env", "reason"),
    [
        ({"INDICATORS_OBSERVATION_DRAIN_ENABLED": "false"}, "disabled"),
        ({"INDICATORS_OBSERVATION_DRAIN_TENANTS": ""}, "no_tenants"),
        ({"SAHOOL_AGENT_TOKEN": "", "RASTER_SERVICE_TOKEN": ""}, "token_not_configured"),
        ({"DATABASE_URL": ""}, "store_not_configured"),
    ],
)
def test_a_drain_that_cannot_run_sends_nothing_and_says_why(drain, monkeypatch, env, reason):
    raster, store = drain
    raster.add(TENANT, _payload())
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert _cycle(raster) == {"skipped": reason}
    assert raster.requests == [] and store["calls"] == []
    assert observation_drain.state()["last_skip_reason"] == reason


def test_the_tenant_partition_is_explicit_uuids_only(monkeypatch):
    monkeypatch.setenv(
        "INDICATORS_OBSERVATION_DRAIN_TENANTS", f" {TENANT.upper()} ,not-a-uuid,{TENANT},,"
    )
    assert observation_drain.tenants() == (TENANT,)
    monkeypatch.delenv("INDICATORS_OBSERVATION_DRAIN_TENANTS")
    assert observation_drain.tenants() == (), "unset: no tenant is guessed"


def test_the_interval_and_batch_are_bounded(monkeypatch):
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_BATCH", "5000")
    assert observation_drain.interval_seconds() == 1.0
    assert observation_drain.batch_size() == 200


# ── observable, without secrets ───────────────────────────────────────────────────────────
def test_readyz_and_metrics_report_the_drain_without_secrets(drain):
    raster, _store = drain
    raster.add(TENANT, _payload())
    _cycle(raster)
    client = TestClient(main.app)
    ready = client.get("/readyz")
    assert ready.status_code == 200, ready.text
    state = ready.json()["observation_drain"]
    assert state["enabled"] is True and state["tenants"] == 1 and state["token_configured"]
    assert state["counters"]["acknowledged"] >= 1, state
    assert TOKEN not in ready.text and TENANT not in ready.text, "no token, no tenant id"
    metrics = client.get("/metrics").text
    assert 'sahool_indicators_observation_drain_total{result="acknowledged"}' in metrics


@pytest.mark.parametrize(
    ("env", "reason"),
    [
        ({"INDICATORS_OBSERVATION_DRAIN_ENABLED": "false"}, "disabled"),
        ({"INDICATORS_OBSERVATION_DRAIN_TENANTS": ""}, "no_tenants"),
    ],
)
def test_readyz_says_a_drain_that_is_off_or_has_no_tenants_is_not_ready_for_delivery(
    drain, monkeypatch, env, reason
):
    """Owner condition (2026-11-17): a disabled drain or an empty partition is reported as not
    enabled, never as ready for delivery; and it settles nothing, so raster's pending entries
    stay pending (no acknowledgement request is ever sent)."""
    raster, store = drain
    raster.add(TENANT, _payload())
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    client = TestClient(main.app)
    ready = client.get("/readyz").json()
    assert ready["observation_delivery"] == "not_enabled", ready
    state = ready["observation_drain"]
    assert state["ready_for_delivery"] is False and state["not_enabled_reason"] == reason, state
    assert _cycle(raster) == {"skipped": reason}
    assert raster.requests == [] and store["calls"] == []
    assert raster.status(TENANT) == [(1, "pending")], "nothing pending was settled or removed"


def test_readyz_says_a_drain_that_can_run_is_ready_for_delivery(drain):
    ready = TestClient(main.app).get("/readyz").json()
    assert ready["observation_delivery"] == "enabled", ready
    assert ready["observation_drain"]["ready_for_delivery"] is True
    assert ready["observation_drain"]["not_enabled_reason"] is None


def test_the_lifespan_starts_the_drain_only_when_it_can_run(drain, monkeypatch):
    started: list = []

    async def _serve():
        started.append(True)
        await asyncio.sleep(3600)

    monkeypatch.setattr(observation_drain, "serve", _serve)
    _stub_role_guard(monkeypatch)
    with TestClient(main.app):
        pass
    assert started == [True], "on with a partition, a token and a store: the loop starts"
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_ENABLED", "false")
    with TestClient(main.app):
        pass
    assert started == [True], "off: no loop"
    assert observation_drain.state()["last_skip_reason"] == "disabled"


def _stub_role_guard(monkeypatch, outcome=None):
    import shared.db_role_guard as role_guard

    calls: list = []

    async def _guard(dsn, *, service=""):
        calls.append((dsn, service))
        if outcome is not None:
            raise outcome

    monkeypatch.setattr(role_guard, "assert_dsn_role_rls_safe", _guard)
    return calls


def test_the_lifespan_checks_the_database_role_before_anything_starts(drain, monkeypatch):
    """A second layer under RLS FORCE, as raster-service: with ``DATABASE_URL`` set, a role that
    can bypass row security refuses startup, and the drain never starts."""
    started: list = []

    async def _serve():
        started.append(True)
        await asyncio.sleep(3600)

    monkeypatch.setattr(observation_drain, "serve", _serve)
    calls = _stub_role_guard(monkeypatch)
    with TestClient(main.app):
        pass
    assert calls == [("postgresql://stub/for-tests", "indicators-service")], calls

    refused = _stub_role_guard(monkeypatch, RuntimeError("role can bypass row security"))
    with pytest.raises(RuntimeError, match="bypass row security"), TestClient(main.app):
        pass
    assert len(refused) == 1 and started == [True], "refused before the drain started again"


# ── configuration parsing: bad values fall back to safe defaults, never crash the worker ──────
def test_the_tenant_partition_ignores_values_that_are_not_uuids(monkeypatch):
    good = "11111111-1111-4111-8111-111111111111"
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_TENANTS", f" not-a-uuid , {good},,{good} ")
    assert observation_drain.tenants() == (good,)


def test_an_unparseable_interval_falls_back_and_never_drops_below_one_second(monkeypatch):
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_INTERVAL_SECONDS", "soon")
    assert observation_drain.interval_seconds() == 30.0
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_INTERVAL_SECONDS", "0.01")
    assert observation_drain.interval_seconds() == 1.0


def test_the_batch_size_is_parsed_and_clamped(monkeypatch):
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_BATCH", "many")
    assert observation_drain.batch_size() == 50
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_BATCH", "0")
    assert observation_drain.batch_size() == 1
    monkeypatch.setenv("INDICATORS_OBSERVATION_DRAIN_BATCH", "10000")
    assert observation_drain.batch_size() == 200


def test_a_zero_count_changes_no_counter():
    before = dict(observation_drain._STATE["counters"])
    observation_drain._count("delivered", 0)
    assert observation_drain._STATE["counters"] == before
