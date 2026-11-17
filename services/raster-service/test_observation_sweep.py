"""W1-11 hardening — the reconciliation sweep of published assets with no outbox row.

Unit level: the switch, the explicit tenant partition, the bound, the digest check, the
idempotent enqueue it reuses, and what it reports without secrets. Its SQL (published assets
whose stored payload has no outbox row, under RLS FORCE on the restricted role) and the crash
cases are measured on PostgreSQL in ``tests_v9/test_canonical_observations_live_pg.py``.
"""

from __future__ import annotations

import asyncio

import db_persist
import observation_outbox
import observation_sweep
import pytest

pytestmark = pytest.mark.unit

TENANT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def _payload(tenant=TENANT, scene="scene_1"):
    return observation_outbox.build_payload(
        tenant_id=tenant,
        field_id="fld_sweep",
        indicator="ndvi",
        scene_id=scene,
        capture_datetime="2026-09-01T10:00:00Z",
        stats={"mean": 0.5},
        quality={"valid_pixel_ratio": 0.9},
        algorithm_version="a",
        qa_mask_version=None,
        product_identity_key=f"pik_{scene}",
        geometry_revision=1,
        data_available_at=None,
        processing_job_id="job",
        cog_uri="s3://b/x.tif",
    )


@pytest.fixture
def sweep(monkeypatch):
    state = {"missing": {}, "enqueued": [], "limits": [], "enqueue_ok": True, "read_raises": False}

    async def _missing(tenant, limit, after_id=0):
        # The SQL's contract: assets above ``after_id`` with no outbox row, in id order.
        state["limits"].append((tenant, limit))
        state.setdefault("after_ids", []).append(after_id)
        if state["read_raises"]:
            raise observation_outbox.OutboxUnavailable("down")
        queued = {p["product_identity_key"] for p in state["enqueued"]}
        rows = [
            item
            for item in state["missing"].get(tenant, [])
            if item["asset_id"] > after_id and item["product_identity_key"] not in queued
        ]
        return sorted(rows, key=lambda item: item["asset_id"])[:limit]

    async def _enqueue(payload):
        if not state["enqueue_ok"]:
            return None
        state["enqueued"].append(payload)
        return (len(state["enqueued"]), "pending")

    monkeypatch.setattr(observation_sweep, "missing_entries", _missing)
    monkeypatch.setattr(observation_outbox, "enqueue", _enqueue)
    monkeypatch.setattr(db_persist, "DATABASE_URL", "postgresql://stub/for-tests")
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_ENABLED", "true")
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_TENANTS", f"{TENANT}, not-a-uuid")
    monkeypatch.setattr(observation_sweep, "_STATE", dict(observation_sweep._STATE))
    observation_sweep._STATE["counters"] = dict.fromkeys(observation_sweep.RESULTS, 0)
    observation_sweep._STATE["cursors"] = {}
    return state


_IDS = iter(range(1, 1_000_000))


def _item(payload, digest=None, asset_id=None):
    return {
        "asset_id": asset_id if asset_id is not None else next(_IDS),
        "product_identity_key": payload["product_identity_key"],
        "payload": payload,
        "digest": digest or observation_outbox.payload_sha256(payload),
    }


def test_a_published_asset_with_no_outbox_row_is_queued_from_its_stored_payload(sweep):
    payload = _payload()
    sweep["missing"][TENANT] = [_item(payload)]
    result = asyncio.run(observation_sweep.run_once())
    assert result["tenants"][TENANT]["enqueued"] == 1, result
    assert sweep["enqueued"] == [payload], "the stored bytes, not a rebuilt payload"
    assert observation_sweep.state()["counters"]["enqueued"] == 1
    assert observation_sweep.state()["last_run_ok"] is True


@pytest.mark.parametrize(
    ("flag", "tenants", "reason"),
    [
        ("false", TENANT, "disabled"),
        ("true", "", "no_tenants"),
        ("true", "not-a-uuid", "no_tenants"),
    ],
)
def test_the_switch_and_the_partition_gate_the_sweep(sweep, monkeypatch, flag, tenants, reason):
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_ENABLED", flag)
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_TENANTS", tenants)
    sweep["missing"][TENANT] = [_item(_payload())]
    assert asyncio.run(observation_sweep.run_once()) == {"skipped": reason}
    assert sweep["enqueued"] == [] and sweep["limits"] == []
    assert observation_sweep.state()["last_skip_reason"] == reason


def test_without_a_database_the_sweep_idles(sweep, monkeypatch):
    monkeypatch.setattr(db_persist, "DATABASE_URL", "")
    assert asyncio.run(observation_sweep.run_once()) == {"skipped": "database_not_configured"}


def test_only_the_partition_is_swept_one_tenant_at_a_time(sweep, monkeypatch):
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_TENANTS", f"{OTHER},{TENANT}")
    asyncio.run(observation_sweep.run_once())
    assert sorted(t for t, _ in sweep["limits"]) == sorted([TENANT, OTHER])


def test_a_run_is_bounded_per_tenant(sweep, monkeypatch):
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_BATCH", "2")
    sweep["missing"][TENANT] = [_item(_payload(scene=f"s{n}")) for n in range(5)]
    first = asyncio.run(observation_sweep.run_once())
    assert first["tenants"][TENANT]["enqueued"] == 2 and sweep["limits"] == [(TENANT, 2)]


@pytest.mark.parametrize(("value", "expected"), [("0", 1), ("5000", 1000), ("x", 100)])
def test_the_bound_is_clamped(monkeypatch, value, expected):
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_BATCH", value)
    assert observation_sweep.batch_size() == expected


def test_a_payload_that_does_not_match_its_digest_is_never_queued(sweep):
    sweep["missing"][TENANT] = [_item(_payload(), digest="0" * 64)]
    result = asyncio.run(observation_sweep.run_once())
    assert result["tenants"][TENANT]["digest_mismatch"] == 1 and sweep["enqueued"] == []


def test_a_payload_of_another_tenant_is_never_queued(sweep):
    sweep["missing"][TENANT] = [_item(_payload(tenant=OTHER))]
    result = asyncio.run(observation_sweep.run_once())
    assert result["tenants"][TENANT]["tenant_mismatch"] == 1 and sweep["enqueued"] == []


def test_an_unwritable_outbox_stops_the_tenant_and_the_run_reports_it(sweep):
    sweep["missing"][TENANT] = [_item(_payload(scene="a")), _item(_payload(scene="b"))]
    sweep["enqueue_ok"] = False
    result = asyncio.run(observation_sweep.run_once())
    assert result["tenants"][TENANT]["enqueue_failed"] == 1, "stops at the first failure"
    assert observation_sweep.state()["last_run_ok"] is False


def test_mismatched_rows_cannot_hide_a_missing_asset_behind_them(sweep, monkeypatch):
    """A mismatched row never gets an outbox row, so it matches on every run. With a full batch
    of them at lower ids than a genuinely missing asset, the keyset cursor still reaches the
    missing asset within a bounded number of runs, and the runs that met them are not ok."""
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_BATCH", "3")
    bad = [_item(_payload(scene=f"bad{n}"), digest="0" * 64, asset_id=n + 1) for n in range(3)] + [
        _item(_payload(tenant=OTHER, scene="other"), asset_id=4)
    ]
    missing = _payload(scene="missing")
    sweep["missing"][TENANT] = [*bad, _item(missing, asset_id=10)]
    for _ in range(3):
        asyncio.run(observation_sweep.run_once())
        if sweep["enqueued"]:
            break
    assert sweep["enqueued"] == [missing], sweep["after_ids"]
    assert sweep["after_ids"][:2] == [0, 3], "the second pass resumes after the first one"
    state = observation_sweep.state()
    assert state["last_run_ok"] is False and state["last_run_mismatches"] == 1, state
    # The short pass wrapped: the next run starts again from the first asset.
    asyncio.run(observation_sweep.run_once())
    assert sweep["after_ids"][-1] == 0, sweep["after_ids"]
    assert observation_sweep.state()["last_run_mismatches"] == 3


def test_a_run_with_only_mismatches_is_not_ok(sweep):
    sweep["missing"][TENANT] = [_item(_payload(), digest="0" * 64)]
    asyncio.run(observation_sweep.run_once())
    assert observation_sweep.state()["last_run_ok"] is False
    assert observation_sweep.state()["last_run_mismatches"] == 1


def test_a_failed_enqueue_keeps_the_cursor(sweep, monkeypatch):
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_BATCH", "1")
    sweep["missing"][TENANT] = [_item(_payload(scene="a"), asset_id=5)]
    sweep["enqueue_ok"] = False
    asyncio.run(observation_sweep.run_once())
    sweep["enqueue_ok"] = True
    asyncio.run(observation_sweep.run_once())
    assert sweep["after_ids"] == [0, 0] and len(sweep["enqueued"]) == 1


def test_an_unreadable_outbox_is_counted_not_raised(sweep):
    sweep["read_raises"] = True
    result = asyncio.run(observation_sweep.run_once())
    assert result["tenants"][TENANT]["read_failed"] == 1
    assert observation_sweep.state()["last_run_ok"] is False


def test_the_state_carries_no_payload_or_secret(sweep):
    sweep["missing"][TENANT] = [_item(_payload())]
    asyncio.run(observation_sweep.run_once())
    text = repr(observation_sweep.state())
    assert TENANT not in text and "fld_sweep" not in text and "postgresql" not in text


def test_the_sweep_reuses_the_publish_path_identity():
    """The sweep's SQL matches an outbox row by the identity ``enqueue`` writes (the payload's
    product identity, or its digest) and the stored digest, and reads only published assets."""
    sql = observation_sweep._MISSING
    assert "asset_status = 'ready'" in sql
    assert "a.tenant_id = $1::uuid" in sql and "o.tenant_id = $1::uuid" in sql
    assert "'product_identity_key'" in sql and "'observation_payload_sha256'" in sql
    assert "LIMIT $2" in sql
    assert "a.id > $3" in sql and "ORDER BY a.id" in sql, "a keyset cursor, not an offset"
    assert observation_outbox.PROVENANCE_PAYLOAD_KEY in sql
    assert observation_outbox.PROVENANCE_DIGEST_KEY in sql


# ── configuration parsing: bad values fall back to safe defaults, never crash the sweep ───────
def test_the_sweep_tenant_partition_ignores_values_that_are_not_uuids(monkeypatch):
    good = "22222222-2222-4222-8222-222222222222"
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_TENANTS", f"bogus,{good}, ,{good}")
    assert observation_sweep.tenants() == (good,)


def test_an_unparseable_sweep_interval_falls_back_and_has_a_floor(monkeypatch):
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_INTERVAL_SECONDS", "later")
    assert observation_sweep.interval_seconds() == 300.0
    monkeypatch.setenv("RASTER_OBSERVATION_SWEEP_INTERVAL_SECONDS", "1")
    assert observation_sweep.interval_seconds() == 5.0
