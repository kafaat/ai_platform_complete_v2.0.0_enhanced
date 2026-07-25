"""Canonical imagery product identity across backfill + single-scene (V8-05 PR1-b).

One value object (ImageryProductIdentity) is the single path to build identity across:
bulk backfill idempotency, single_scene idempotency, ready-asset preflight, and the raster
product identity/dedup. Adds processing_version to the backfill key and provider to the
product identity. Deterministic serialization + SHA-256 (never python hash()). Dual-read /
single-write: new writes use canonical v2 only; legacy keys stay discoverable when provable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services" / "raster-service"
if str(RASTER) not in sys.path:
    sys.path.insert(0, str(RASTER))

import imagery_product_identity as I  # noqa: E402
from indicator_product_identity import ProductIdentity  # noqa: E402

BASE = dict(
    tenant_id="t1",
    field_id="f1",
    geometry_revision=3,
    provider="cdse",
    scene_id="S2A_MSIL2A_X",
    product="ndvi",
    processing_version="sahool.band_math/1",
)


def _id(**over):
    d = {**BASE, **over}
    return I.ImageryProductIdentity.create(**d)


# ── #1 bulk and single_scene produce the SAME canonical key for the same inputs ──────────
def test_1_bulk_and_single_scene_same_key():
    # bulk builds via _identity(...); single_scene (enqueue) via ImageryProductIdentity.create.
    # Both normalize provider/product, so equivalent inputs collapse to one key.
    bulk = I.ImageryProductIdentity.create(
        tenant_id="t1",
        field_id="f1",
        geometry_revision=3,
        provider="CDSE",
        scene_id="S2A_MSIL2A_X",
        product="NDVI",
        processing_version="sahool.band_math/1",
    )
    single = I.ImageryProductIdentity.create(
        tenant_id="t1",
        field_id="f1",
        geometry_revision=3,
        provider="sentinel-2",
        scene_id="S2A_MSIL2A_X",
        product="ndvi",
        processing_version="sahool.band_math/1",
    )
    assert bulk.to_canonical_key() == single.to_canonical_key()
    assert bulk.to_canonical_key().startswith("v2:")


def test_1b_both_call_sites_route_through_value_object():
    worker = (RASTER / "backfill_scan_worker.py").read_text(encoding="utf-8")
    dbp = (RASTER / "db_persist.py").read_text(encoding="utf-8")
    assert "ImageryProductIdentity" in worker and "to_canonical_key()" in worker
    assert "ImageryProductIdentity" in dbp and "to_canonical_key()" in dbp
    # no hand-reassembled f-string key survives in enqueue
    assert 'f"{tenant_id}:{field_id}:{geometry_revision' not in dbp, (
        "enqueue must not hand-reassemble the idempotency key"
    )


# ── #2 processing_version discriminates identity ─────────────────────────────────────────
def test_2_processing_version_changes_identity():
    assert (
        _id().to_canonical_key() != _id(processing_version="sahool.band_math/2").to_canonical_key()
    )
    assert _id().content_hash() != _id(processing_version="sahool.band_math/2").content_hash()


# ── #3 provider discriminates identity ───────────────────────────────────────────────────
def test_3_provider_changes_identity():
    assert _id().to_canonical_key() != _id(provider="landsat").to_canonical_key()
    # and on the asset product identity (rip_ hash) too
    a = ProductIdentity("t", "g", "s", "ndvi", "1", "m", provider="cdse").key()
    b = ProductIdentity("t", "g", "s", "ndvi", "1", "m", provider="landsat-element84").key()
    assert a != b


# ── #4 repeat request → same key (so live item is reused, not duplicated) ────────────────
def test_4_repeat_same_inputs_same_key():
    assert _id().to_canonical_key() == _id().to_canonical_key()
    # enqueue reuses a live item by this key (structural)
    dbp = (RASTER / "db_persist.py").read_text(encoding="utf-8")
    assert '"reused_existing_job": True' in dbp
    assert "idempotency_key=$2" in dbp


# ── #5/#6 cross-path ready-asset reuse is column-based (bulk <-> process-date) ───────────
def test_5_6_ready_asset_preflight_is_column_based_both_paths():
    dbp = (RASTER / "db_persist.py").read_text(encoding="utf-8")
    worker = (RASTER / "backfill_scan_worker.py").read_text(encoding="utf-8")
    # both preflights match a ready asset by the same columns (tenant/field/index/date/geom)
    for src in (dbp, worker):
        assert "FROM raster_assets" in src
        assert "asset_status" in src and "ready" in src
        assert "geometry_revision" in src


# ── #7 legacy keys discoverable + dual-read forward-migration present ────────────────────
def test_7_legacy_dual_read_present():
    idn = _id()
    assert idn.legacy_backfill_key() == "t1:f1:3:cdse:S2A_MSIL2A_X:ndvi"
    assert idn.legacy_matches_baseline() is True  # current version == canonical baseline
    # a non-baseline processing_version must NOT dual-read-reuse legacy (ambiguous)
    assert _id(processing_version="other/9").legacy_matches_baseline() is False
    worker = (RASTER / "backfill_scan_worker.py").read_text(encoding="utf-8")
    dbp = (RASTER / "db_persist.py").read_text(encoding="utf-8")
    for src in (worker, dbp):
        assert "legacy_backfill_key()" in src
        assert "legacy_matches_baseline()" in src
    # asset forward-repair (legacy no-provider hash -> v2 hash), single row
    assert "legacy_product_identity_key" in dbp
    assert "legacy_key()" in (RASTER / "raster_asset_persistence.py").read_text(encoding="utf-8")


# ── #8 no reuse across ANY differing field of the 7 ──────────────────────────────────────
def test_8_every_field_discriminates():
    base_key = _id().to_canonical_key()
    variants = {
        "tenant_id": "t2",
        "field_id": "f2",
        "geometry_revision": 4,
        "provider": "landsat",
        "scene_id": "OTHER_SCENE",
        "product": "ndmi",
        "processing_version": "sahool.band_math/9",
    }
    for field, val in variants.items():
        assert _id(**{field: val}).to_canonical_key() != base_key, f"{field} must discriminate"


# ── #9 deterministic serialization, independent of field order ───────────────────────────
def test_9_serialization_stable_and_order_independent():
    k1 = _id().content_hash()
    k2 = _id().content_hash()
    assert k1 == k2 and k1.startswith("ipk2_")
    # canonical key is a fixed field order (not dict/py-hash dependent)
    assert _id().to_canonical_key() == "v2:t1:f1:3:cdse:S2A_MSIL2A_X:ndvi:sahool.band_math/1"
    # never python builtin hash() — deterministic sha256 only. Check actual call sites in
    # code lines (ignore docstrings/comments that merely mention hash()).
    src = (RASTER / "imagery_product_identity.py").read_text(encoding="utf-8")
    assert "hashlib.sha256" in src
    code_lines = [
        ln for ln in src.splitlines() if not ln.lstrip().startswith(("#", '"""', "*", "•"))
    ]
    for pat in ("return hash(", "= hash(", " hash(self", "hash(json", "hash(raw"):
        assert not any(pat in ln for ln in code_lines), f"builtin hash() call found: {pat}"


# ── #10 v144/v213 state machine unchanged (no new migration touches item/run status) ─────
def test_10_state_machine_unchanged():
    v144 = (ROOT / "migrations" / "v144_backfill_runs.sql").read_text(encoding="utf-8")
    v213 = (ROOT / "migrations" / "v213_backfill_runs_single_scene.sql").read_text(encoding="utf-8")
    # the canonical status sets are intact
    assert "('planned', 'searching', 'queued', 'processing', 'completed', 'failed')" in v144
    assert "('queued', 'processing', 'persisted', 'skipped', 'failed')" in v144
    assert "run_kind IN ('backfill', 'single_scene')" in v213
    # PR1-b introduced NO migration altering backfill status/state (identity is app-level).
    migrations = {p.name for p in (ROOT / "migrations").glob("v*.sql")}
    assert "v214_backfill_runs.sql" not in migrations
