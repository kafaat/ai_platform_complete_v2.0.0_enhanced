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


def _compose_payload(field_id: str, key: str, leak: bool = False):
    from agronomic_context.contracts import ContextComposeIn, FeatureEntryIn, HistoricalContextIn

    now = _now()
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
    first = _run(
        compose_agronomic_context(
            tenant_id=TENANT, created_by="composer", payload=_compose_payload(field, key)
        )
    )
    assert first["status"] == "ok" and first["feature_count"] == 2
    # identical retry => replay of the same snapshot.
    replay = _run(
        compose_agronomic_context(
            tenant_id=TENANT, created_by="composer", payload=_compose_payload(field, key)
        )
    )
    assert replay["status"] == "ok" and replay.get("replay") is True
    assert replay["snapshot_id"] == first["snapshot_id"]
    # same content, different idempotency key => the snapshot is REUSED (content-addressed).
    again = _run(
        compose_agronomic_context(
            tenant_id=TENANT,
            created_by="composer",
            payload=_compose_payload(field, "ctx_" + uuid4().hex),
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
