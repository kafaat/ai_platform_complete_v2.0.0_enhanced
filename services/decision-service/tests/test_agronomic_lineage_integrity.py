"""AC-6.1: tenant-safe agronomic lineage integrity on real Postgres (+ static contract)."""

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

MIGRATION = (SERVICE_DIR / "migrations/019_agronomic_lineage_integrity.sql").read_text()
PERSISTENCE = (SERVICE_DIR / "persistence.py").read_text()

DB = os.getenv("DATABASE_URL", "").strip()
TENANT = "00000000-0000-0000-0000-000000009161"
OTHER_TENANT = "00000000-0000-0000-0000-000000009162"


def test_migration_uses_tenant_scoped_foreign_keys_and_semantic_trigger():
    assert "FOREIGN KEY (tenant_id, agronomic_context_snapshot_id)" in MIGRATION
    assert "FOREIGN KEY (tenant_id, vegetation_snapshot_id)" in MIGRATION
    assert "FOREIGN KEY (tenant_id, field_historical_context_snapshot_id)" in MIGRATION
    assert "FOREIGN KEY (tenant_id, feature_manifest_id)" in MIGRATION
    assert "decision_validate_agronomic_lineage" in MIGRATION
    assert "agronomic context field/season mismatch" in MIGRATION
    assert "vegetation snapshot field/season mismatch" in MIGRATION
    assert "field history snapshot field/season mismatch" in MIGRATION
    assert "feature manifest hash mismatch" in MIGRATION
    assert "ENABLE ROW LEVEL SECURITY" in MIGRATION


def test_persistence_binds_tenant_and_returns_canonical_snapshot_id():
    decision_fn = PERSISTENCE.split("async def persist_decision_record", 1)[1].split(
        "async def persist_dispatch_decision", 1
    )[0]
    assert "set_config('app.current_tenant'" in decision_fn
    assert "lineage_integrity_violation" in decision_fn
    assert "_canonical_snapshot_id" in PERSISTENCE
    assert "RETURNING snapshot_id" in PERSISTENCE
    assert '"created": canonical == snapshot_id' in PERSISTENCE


# ── real-Postgres proof ──────────────────────────────────────────────────────
pytestmark_pg = pytest.mark.skipif(not DB, reason="requires real Postgres")


def _run(c):
    return asyncio.run(c)


async def _connect():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


def _now():
    return datetime.now(UTC).replace(microsecond=0)


def _veg_payload(field_id: str, digest: str, season: str | None = "s2026"):
    now = _now()
    return SimpleNamespace(
        field_id=field_id,
        season_id=season,
        contract_version="vegetation-snapshot.v2",
        snapshot_hash=digest,
        acquisition_at=now - timedelta(hours=2),
        data_available_at=now - timedelta(hours=1),
        quality_gate={"executable": True},
        feature_manifest={"id": "vegetation-core", "version": "indicator-registry.v1"},
        payload={"indices": {"ndvi": {"value": 0.6}}},
    )


def _compose_payload(field_id: str):
    from agronomic_context.contracts import ContextComposeIn, FeatureEntryIn, HistoricalContextIn

    now = _now()
    return ContextComposeIn(
        field_id=field_id,
        season_id="s2026",
        as_of_time=now,
        decision_cutoff_time=now,
        context={
            "crop": {"crop_id": "wheat", "cultivar_id": "yecora", "crop_card_version": "v3"},
            "soil": {"ph": 7.1},
            "irrigation": {"type": "drip"},
            "weather": {"et0_mm": 5.2},
            "climate": {"drought_index": 0.2},
            "terrain": {"slope_pct": 2.0},
            "operations": {},
        },
        historical=HistoricalContextIn(
            history_from=now - timedelta(days=30),
            history_to=now - timedelta(hours=1),
            history={"ndvi_trend_14d": -0.03},
        ),
        features=[
            FeatureEntryIn(
                name="ndvi_mean",
                value=0.61,
                unit="index",
                source_service="raster-service",
                observed_at=now - timedelta(days=2),
                available_at=now - timedelta(days=2),
                quality_status="verified",
            )
        ],
        idempotency_key="ctx_" + uuid4().hex,
    )


def _decision(field_id, ctx, veg_id, manifest_hash, **over):
    base = dict(
        decision_id=None,
        field_id=field_id,
        season_id="s2026",
        crop_id="wheat",
        cultivar_id="yecora",
        decision_type="irrigation",
        region=None,
        stage="decision",
        decision_value={"minutes": 30},
        confidence=0.8,
        created_by="agent",
        agronomic_context_snapshot_id=ctx["snapshot_id"],
        field_historical_context_snapshot_id=ctx["historical_snapshot_id"],
        feature_manifest_id=ctx["feature_manifest_id"],
        feature_manifest_hash=manifest_hash,
        vegetation_snapshot_id=veg_id,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytestmark_pg
def test_full_lineage_binding_and_semantic_rejections():
    from persistence import (
        compose_agronomic_context,
        persist_decision_record,
        persist_vegetation_snapshot,
    )

    field = "f_" + uuid4().hex[:8]
    digest = uuid4().hex + uuid4().hex  # 64 hex chars

    # 1) content-addressed vegetation evidence: create then replay -> canonical, not duplicate.
    first = _run(
        persist_vegetation_snapshot(
            tenant_id=TENANT,
            payload=_veg_payload(field, digest),
            snapshot_id="veg_" + uuid4().hex[:20],
        )
    )
    assert first["created"] is True
    replay = _run(
        persist_vegetation_snapshot(
            tenant_id=TENANT,
            payload=_veg_payload(field, digest),
            snapshot_id="veg_" + uuid4().hex[:20],
        )
    )
    assert replay["created"] is False and replay["snapshot_id"] == first["snapshot_id"]

    # 2) compose the AC-1 context and read the manifest's stored content hash.
    ctx = _run(
        compose_agronomic_context(
            tenant_id=TENANT, created_by="composer", payload=_compose_payload(field)
        )
    )
    assert ctx["status"] == "ok"

    async def manifest_hash():
        c = await _connect()
        try:
            return await c.fetchval(
                "SELECT content_hash FROM decision_feature_manifests WHERE tenant_id=$1::uuid AND feature_manifest_id=$2",
                TENANT,
                ctx["feature_manifest_id"],
            )
        finally:
            await c.close()

    mh = _run(manifest_hash())

    # 3) full AC-6 lineage binds successfully.
    did = "dec_" + uuid4().hex[:16]
    ok = _run(
        persist_decision_record(
            tenant_id=TENANT,
            payload=_decision(field, ctx, first["snapshot_id"], mh),
            decision_id=did,
        )
    )
    assert ok.get("decision_id") == did

    async def row():
        c = await _connect()
        try:
            return await c.fetchrow(
                "SELECT season_id, crop_id, cultivar_id, vegetation_snapshot_id, feature_manifest_hash,"
                " context_contract_version FROM decision_record WHERE decision_id=$1",
                did,
            )
        finally:
            await c.close()

    r = _run(row())
    assert r["season_id"] == "s2026" and r["crop_id"] == "wheat"
    assert r["vegetation_snapshot_id"] == first["snapshot_id"]
    assert r["feature_manifest_hash"] == mh
    assert r["context_contract_version"] == "ac-1"

    # 4) typed semantic rejections (persistence layer).
    bad_hash = _run(
        persist_decision_record(
            tenant_id=TENANT,
            payload=_decision(field, ctx, first["snapshot_id"], "e" * 64),
            decision_id="dec_" + uuid4().hex[:16],
        )
    )
    assert bad_hash == {"status": "rejected", "reason": "feature_manifest_hash_mismatch"}

    wrong_season = _run(
        persist_decision_record(
            tenant_id=TENANT,
            payload=_decision(field, ctx, first["snapshot_id"], mh, season_id="s2027"),
            decision_id="dec_" + uuid4().hex[:16],
        )
    )
    assert wrong_season == {"status": "rejected", "reason": "context_season_mismatch"}

    unknown_veg = _run(
        persist_decision_record(
            tenant_id=TENANT,
            payload=_decision(field, ctx, "veg_missing", mh),
            decision_id="dec_" + uuid4().hex[:16],
        )
    )
    assert unknown_veg == {"status": "rejected", "reason": "unknown_vegetation_snapshot"}

    # 5) tenant scoping: another tenant can never reference this tenant's evidence.
    cross_tenant = _run(
        persist_decision_record(
            tenant_id=OTHER_TENANT,
            payload=_decision(
                field,
                ctx,
                first["snapshot_id"],
                mh,
                agronomic_context_snapshot_id=ctx["snapshot_id"],
            ),
            decision_id="dec_" + uuid4().hex[:16],
        )
    )
    assert cross_tenant["status"] == "rejected"
    assert cross_tenant["reason"] == "unknown_agronomic_context_snapshot"


@pytestmark_pg
def test_db_trigger_backstop_rejects_direct_mismatched_insert():
    """Bypass persistence: the migration-019 trigger itself must refuse mismatched evidence."""
    from persistence import persist_vegetation_snapshot

    field = "f_" + uuid4().hex[:8]
    digest = uuid4().hex + uuid4().hex
    veg = _run(
        persist_vegetation_snapshot(
            tenant_id=TENANT,
            payload=_veg_payload(field, digest),
            snapshot_id="veg_" + uuid4().hex[:20],
        )
    )

    async def direct_mismatch():
        c = await _connect()
        try:
            await c.execute(
                """
                INSERT INTO decision_record
                  (decision_id, tenant_id, field_id, decision_type, stage, decision_value,
                   vegetation_snapshot_id)
                VALUES ($1, $2::uuid, 'a-different-field', 'irrigation', 'decision', '{}'::jsonb, $3)
                """,
                "dec_" + uuid4().hex[:16],
                TENANT,
                veg["snapshot_id"],
            )
            return "inserted"
        except Exception as exc:  # noqa: BLE001 - the assertion IS about the raised class
            return type(exc).__name__
        finally:
            await c.close()

    assert _run(direct_mismatch()) != "inserted"

    async def tamper():
        c = await _connect()
        try:
            await c.execute(
                "UPDATE decision_vegetation_snapshots SET field_id='tampered' WHERE snapshot_id=$1",
                veg["snapshot_id"],
            )
            return "mutated"
        except Exception as exc:  # noqa: BLE001
            return type(exc).__name__
        finally:
            await c.close()

    assert _run(tamper()) != "mutated"  # append-only evidence
