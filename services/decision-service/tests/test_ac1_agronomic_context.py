"""AC-1: agronomic context composer + mandatory decision binding on real Postgres."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres")
TENANT = "00000000-0000-0000-0000-000000009131"


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


def _now():
    return datetime.now(UTC).replace(microsecond=0)


def _compose_payload(field_id: str, key: str, leak: bool = False, now: datetime | None = None):
    from agronomic_context.contracts import ContextComposeIn, FeatureEntryIn, HistoricalContextIn

    # `now` must be pinned by tests that assert content-addressed reuse across calls —
    # a second-boundary crossing between two composes would change the content hash.
    now = now or _now()
    return ContextComposeIn(
        field_id=field_id,
        season_id="s2026",
        as_of_time=now,
        decision_cutoff_time=now,
        context={
            "crop": {"crop_id": "wheat", "cultivar_id": "yecora", "crop_card_version": "v3"},
            "soil": {"ph": 7.1, "texture": "loam"},
            "irrigation": {"type": "drip", "efficiency": 0.9},
            "weather": {"weather_snapshot_id": "wx1", "et0_mm": 5.2},
            "climate": {"drought_index": 0.2},
            "terrain": {"slope_pct": 2.0},
            "operations": {"last_irrigation_at": (now - timedelta(days=1)).isoformat()},
        },
        historical=HistoricalContextIn(
            history_from=now - timedelta(days=30),
            history_to=now - timedelta(hours=1),
            history={"ndvi_trend_14d": -0.03, "irrigation_events_30d": 6},
        ),
        features=[
            FeatureEntryIn(
                name="ndvi_mean",
                value=0.61,
                unit="index",
                source_service="raster-service",
                source_snapshot_id="scene-1",
                observed_at=now - timedelta(days=2),
                # leak=True simulates a value that only became available AFTER the cutoff.
                available_at=(now + timedelta(hours=2)) if leak else (now - timedelta(days=2)),
                quality_status="verified",
                formula_version="ndvi-v2",
            ),
            FeatureEntryIn(
                name="et0_mm",
                value=5.2,
                unit="mm",
                source_service="weather-service",
                observed_at=now - timedelta(hours=1),
                available_at=now - timedelta(hours=1),
                quality_status="verified",
            ),
        ],
        idempotency_key=key,
    )


def test_compose_is_deterministic_reusable_and_replayable():
    from persistence import compose_agronomic_context

    field = "f_" + uuid4().hex[:8]
    key = "ctx_" + uuid4().hex
    now = _now()
    first = _run(
        compose_agronomic_context(
            tenant_id=TENANT, created_by="composer", payload=_compose_payload(field, key, now=now)
        )
    )
    assert first["status"] == "ok" and first["feature_count"] == 2
    # identical retry => replay of the same snapshot.
    replay = _run(
        compose_agronomic_context(
            tenant_id=TENANT, created_by="composer", payload=_compose_payload(field, key, now=now)
        )
    )
    assert replay["status"] == "ok" and replay.get("replay") is True
    assert replay["snapshot_id"] == first["snapshot_id"]
    # the manifest hash a decision must pin is returned, equal on replay, and is the stored one
    assert len(first["feature_manifest_hash"]) == 64
    assert replay["feature_manifest_hash"] == first["feature_manifest_hash"]

    async def stored_manifest_hash():
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT content_hash FROM decision_feature_manifests WHERE feature_manifest_id=$1",
                first["feature_manifest_id"],
            )
        finally:
            await c.close()

    assert _run(stored_manifest_hash()) == first["feature_manifest_hash"]
    # same content, different idempotency key => the snapshot is REUSED (content-addressed).
    again = _run(
        compose_agronomic_context(
            tenant_id=TENANT,
            created_by="composer",
            payload=_compose_payload(field, "ctx_" + uuid4().hex, now=now),
        )
    )
    assert again["status"] == "ok" and again["snapshot_id"] == first["snapshot_id"]


def test_future_leakage_is_a_typed_fail_closed_rejection():
    from persistence import compose_agronomic_context

    res = _run(
        compose_agronomic_context(
            tenant_id=TENANT,
            created_by="composer",
            payload=_compose_payload("f_" + uuid4().hex[:8], "ctx_" + uuid4().hex, leak=True),
        )
    )
    assert res["status"] == "rejected" and res["reason"] == "point_in_time_policy"
    codes = {v["code"] for v in res["violations"]}
    assert "future_leakage" in codes

    async def none_persisted():
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT count(*) FROM decision_feature_manifest_entries WHERE tenant_id=$1::uuid AND name='ndvi_mean' AND available_at > now()",
                TENANT,
            )
        finally:
            await c.close()

    assert _run(none_persisted()) == 0  # nothing written on rejection


def test_decision_binding_validates_and_records_contract_version():
    from persistence import compose_agronomic_context, persist_decision_record

    field = "f_" + uuid4().hex[:8]
    ctx = _run(
        compose_agronomic_context(
            tenant_id=TENANT,
            created_by="composer",
            payload=_compose_payload(field, "ctx_" + uuid4().hex),
        )
    )
    assert ctx["status"] == "ok"

    def _decision(**over):
        base = dict(
            decision_id=None,
            field_id=field,
            decision_type="irrigation",
            region=None,
            stage="decision",
            decision_value={"minutes": 30},
            confidence=0.8,
            created_by="agent",
            agronomic_context_snapshot_id=ctx["snapshot_id"],
            field_historical_context_snapshot_id=ctx["historical_snapshot_id"],
            feature_manifest_id=ctx["feature_manifest_id"],
        )
        base.update(over)
        return SimpleNamespace(**base)

    did = "dec_" + uuid4().hex[:16]
    ok = _run(persist_decision_record(tenant_id=TENANT, payload=_decision(), decision_id=did))
    assert ok.get("decision_id") == did

    async def version():
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT context_contract_version FROM decision_record WHERE decision_id=$1", did
            )
        finally:
            await c.close()

    assert _run(version()) == "ac-1"

    # unknown snapshot => typed rejection, nothing persisted.
    bad = _run(
        persist_decision_record(
            tenant_id=TENANT,
            payload=_decision(agronomic_context_snapshot_id="agctx_missing"),
            decision_id="dec_" + uuid4().hex[:16],
        )
    )
    assert bad["status"] == "rejected" and bad["reason"] == "unknown_agronomic_context_snapshot"

    # partial binding (only one ID) is rejected — all three or none.
    partial = _run(
        persist_decision_record(
            tenant_id=TENANT,
            payload=_decision(field_historical_context_snapshot_id=None, feature_manifest_id=None),
            decision_id="dec_" + uuid4().hex[:16],
        )
    )
    assert partial["status"] == "rejected" and partial["reason"] == "partial_context_binding"

    # a decision without any context IDs still records (legacy_unbound) while enforcement is off.
    legacy_id = "dec_" + uuid4().hex[:16]
    legacy = _run(
        persist_decision_record(
            tenant_id=TENANT,
            payload=_decision(
                agronomic_context_snapshot_id=None,
                field_historical_context_snapshot_id=None,
                feature_manifest_id=None,
            ),
            decision_id=legacy_id,
        )
    )
    assert legacy.get("decision_id") == legacy_id

    async def legacy_version():
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT context_contract_version FROM decision_record WHERE decision_id=$1",
                legacy_id,
            )
        finally:
            await c.close()

    assert _run(legacy_version()) == "legacy_unbound"


def test_snapshot_read_and_append_only():
    from persistence import compose_agronomic_context, get_context_snapshot

    field = "f_" + uuid4().hex[:8]
    ctx = _run(
        compose_agronomic_context(
            tenant_id=TENANT,
            created_by="composer",
            payload=_compose_payload(field, "ctx_" + uuid4().hex),
        )
    )
    got = _run(get_context_snapshot(tenant_id=TENANT, snapshot_id=ctx["snapshot_id"]))
    assert got["status"] == "ok" and got["snapshot"]["context"]["crop"]["crop_id"] == "wheat"
    assert got["snapshot"]["content_hash"] == ctx["content_hash"]

    async def try_mutate():
        c = await _connect()
        try:
            await c.execute(
                "UPDATE decision_agronomic_context_snapshots SET field_id='tampered' WHERE snapshot_id=$1",
                ctx["snapshot_id"],
            )
            return "mutated"
        except Exception as exc:
            return type(exc).__name__
        finally:
            await c.close()

    assert _run(try_mutate()) != "mutated"  # append-only trigger blocks tampering


# ── AC-6 point-in-time vegetation read (producers pin vegetation evidence by the cutoff) ──
def _main():
    import main

    return main


def _call(**kw):
    m = _main()
    return asyncio.run(
        m.read_latest_vegetation_snapshot(
            field_id=kw.get("field_id", "f1"),
            available_before=kw.get("available_before", datetime(2026, 7, 10, tzinfo=UTC)),
            season_id=kw.get("season_id"),
            x_tenant_id=TENANT,
        )
    )


def test_the_read_is_refused_when_decision_service_is_not_authoritative(monkeypatch):
    m = _main()
    monkeypatch.setattr(m, "sor_enabled", lambda: False)
    with pytest.raises(HTTPException) as exc:
        _call()
    assert exc.value.status_code == 503


def test_a_cutoff_without_a_timezone_is_refused(monkeypatch):
    m = _main()
    monkeypatch.setattr(m, "sor_enabled", lambda: True)
    with pytest.raises(HTTPException) as exc:
        _call(available_before=datetime(2026, 7, 10))
    assert exc.value.status_code == 422


def test_no_snapshot_is_a_404_never_a_substitute(monkeypatch):
    m = _main()
    monkeypatch.setattr(m, "sor_enabled", lambda: True)

    async def _none(**_kw):
        return {"status": "not_found"}

    monkeypatch.setattr(m, "latest_vegetation_snapshot", _none)
    with pytest.raises(HTTPException) as exc:
        _call()
    assert exc.value.status_code == 404


def test_the_read_passes_the_cutoff_through_and_returns_the_snapshot(monkeypatch):
    m = _main()
    monkeypatch.setattr(m, "sor_enabled", lambda: True)
    seen = {}

    async def _one(**kw):
        seen.update(kw)
        return {"status": "ok", "snapshot_id": "veg_1", "quality_gate": {"executable": True}}

    monkeypatch.setattr(m, "latest_vegetation_snapshot", _one)
    cutoff = datetime(2026, 7, 10, 6, tzinfo=UTC)
    out = _call(available_before=cutoff, season_id="s1")
    assert out["snapshot_id"] == "veg_1" and "status" not in out
    assert seen == {
        "tenant_id": TENANT,
        "field_id": "f1",
        "season_id": "s1",
        "available_before": cutoff,
    }


def test_live_pg_only_snapshots_available_by_the_cutoff_are_returned():
    from main import VegetationSnapshotIn
    from persistence import latest_vegetation_snapshot, persist_vegetation_snapshot

    field = "f_" + uuid4().hex[:8]
    base = datetime.now(UTC).replace(microsecond=0) - timedelta(days=2)

    def snap(hours: int, tag: str):
        return VegetationSnapshotIn(
            field_id=field,
            season_id="s2026",
            snapshot_hash=uuid4().hex + uuid4().hex,
            acquisition_at=base + timedelta(hours=hours - 1),
            data_available_at=base + timedelta(hours=hours),
            quality_gate={"executable": True, "reasons": []},
            feature_manifest={"tag": tag},
            payload={"tag": tag},
        )

    early = asyncio.run(
        persist_vegetation_snapshot(
            tenant_id=TENANT, payload=snap(1, "early"), snapshot_id="veg_" + uuid4().hex[:12]
        )
    )
    asyncio.run(
        persist_vegetation_snapshot(
            tenant_id=TENANT, payload=snap(30, "late"), snapshot_id="veg_" + uuid4().hex[:12]
        )
    )
    cutoff = base + timedelta(hours=10)
    got = asyncio.run(
        latest_vegetation_snapshot(
            tenant_id=TENANT, field_id=field, season_id="s2026", available_before=cutoff
        )
    )
    assert got["status"] == "ok" and got["snapshot_id"] == early["snapshot_id"]
    none = asyncio.run(
        latest_vegetation_snapshot(
            tenant_id=TENANT, field_id=field, season_id="s2026", available_before=base
        )
    )
    assert none == {"status": "not_found"}
