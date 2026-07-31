"""Pins the raster-service legacy_unversioned_business baseline and its ownership-bucket
classification established in
docs/architecture/raster_service_route_migration_plan.md (raster-service slice of
API-VERSIONING-GUARD-IS-A-MIRROR-01).

A route landing in the wrong bucket, a route silently disappearing, or a new
unversioned route appearing without classification all fail this test -- matching the
falsification discipline used for the Option B classifier fix (PR #722).

PR-R1 classified raster-service's 30 originally-unversioned routes into three
ownership buckets without migrating any of them. PR-R2 (internal/operational, 8
routes), PR-R3 (imagery/catalog/process, 20 routes), and PR-R4 (tile/rendering, 2
routes) each migrated their bucket to /v1/... in turn. All 30 routes are now
versioned -- raster-service's legacy_unversioned_business measurement must be empty.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import api_versioning_policy_guard as guard  # noqa: E402

pytestmark = pytest.mark.unit

# PR-R2 -- internal and operational routes (8), migrated to /v1/... in this slice.
# All require_service_token.
MIGRATED_PR_R2 = {
    ("GET", "/v1/jobs/{job_id}"),
    ("GET", "/v1/jobs/{job_id}/result"),
    ("POST", "/v1/upload/raster"),
    ("POST", "/v1/upload/drone"),
    ("GET", "/v1/storage/stats"),
    ("POST", "/v1/storage/cleanup"),
    ("GET", "/v1/offline/packs"),
    ("GET", "/v1/offline/packs/{pack_name}"),
}

# PR-R3 -- imagery/catalog/process routes (20), migrated to /v1/... in this slice.
# All require_service_token except the three STAC routes and the bare GET
# /imagery/timeseries, which are PUBLIC_CATALOG.
MIGRATED_PR_R3 = {
    ("POST", "/v1/zones/classify"),
    ("POST", "/v1/change/detect"),
    ("POST", "/v1/fvc/compute"),
    ("POST", "/v1/sar/rvi"),
    ("POST", "/v1/terrain/slope"),
    ("GET", "/v1/cog/validate"),
    ("POST", "/v1/salinity/classify"),
    ("POST", "/v1/salinity/calibrate"),
    ("POST", "/v1/process"),
    ("POST", "/v1/raw/process"),
    ("POST", "/v1/process/batch"),
    ("GET", "/v1/stac"),
    ("GET", "/v1/stac/collections"),
    ("POST", "/v1/stac/mosaicjson"),
    ("GET", "/v1/info/{layer_id}"),
    ("GET", "/v1/indices"),
    ("GET", "/v1/imagery/timeseries"),
    ("POST", "/v1/imagery/timeseries/analyze"),
    ("POST", "/v1/imagery/timeseries/parallel"),
    ("GET", "/v1/gis/admin-boundaries"),
}

# PR-R4 -- tile and rendering routes (2), migrated to /v1/... in this slice.
# layer_scoped; no live caller found (see plan doc) -- migration is purely
# internal-reference cleanup, not a lock-step consumer update.
MIGRATED_PR_R4 = {
    ("GET", "/v1/tiles/{layer_id}/{z}/{x}/{y}.png"),
    ("GET", "/v1/layers/{layer_id}/tilejson"),
}

# All 30 originally-classified raster-service routes are now migrated. Nothing is
# still bucketed as pending -- the live legacy_unversioned_business measurement for
# raster-service must be empty.
ALL_BUCKETED: set[tuple[str, str]] = set()

# Routes confirmed to have a real internal service-to-service consumer
# (services/sahool-platform/api/raster_service_client.py), all updated in the same PR
# as their path migration -- kept here as an audit trail, not a pending-work tracker.
REAL_CONSUMERS_MIGRATED = {
    ("GET", "/v1/jobs/{job_id}/result"): "raster_service_client.py:466 get_job_result (PR-R2)",
    ("GET", "/v1/indices"): "raster_service_client.py:191 get_indices_sync (PR-R3)",
    (
        "POST",
        "/v1/process/batch",
    ): "raster_service_client.py:448 process_indicator_batch (PR-R3)",
}


def _raster_legacy_routes() -> set[tuple[str, str]]:
    rows = guard.collect()
    return {
        (r["method"], r["path"])
        for r in rows
        if r["service"] == "raster-service" and r["classification"] == "legacy_unversioned_business"
    }


def _raster_versioned_routes() -> set[tuple[str, str]]:
    rows = guard.collect()
    return {
        (r["method"], r["path"])
        for r in rows
        if r["service"] == "raster-service" and r["classification"] == "versioned"
    }


def test_pr_bucket_sets_are_disjoint_and_cover_no_pending_routes():
    assert MIGRATED_PR_R2 & MIGRATED_PR_R3 == set()
    assert MIGRATED_PR_R2 & MIGRATED_PR_R4 == set()
    assert MIGRATED_PR_R3 & MIGRATED_PR_R4 == set()
    assert ALL_BUCKETED == set(), (
        f"expected zero pending bucketed routes (raster-service migration complete), "
        f"got {sorted(ALL_BUCKETED)}"
    )


def test_measured_baseline_matches_the_bucketed_classification():
    measured = _raster_legacy_routes()
    assert measured == set(), (
        f"raster-service still has legacy_unversioned_business routes after PR-R1..PR-R4 "
        f"(migration plan claims completion): {sorted(measured)}"
    )


def test_pr_r2_pr_r3_pr_r4_routes_stay_versioned_not_legacy():
    """Regression guard: PR-R2's 8 routes, PR-R3's 20 routes, and PR-R4's 2 routes must
    remain versioned. If one reverts to a bare path (merge mishap, accidental revert),
    this fails by naming it."""
    migrated = MIGRATED_PR_R2 | MIGRATED_PR_R3 | MIGRATED_PR_R4
    assert len(migrated) == 30, (
        f"expected all 30 raster-service routes tracked, got {len(migrated)}"
    )
    legacy = _raster_legacy_routes()
    regressed = migrated & legacy
    assert not regressed, (
        f"routes regressed back to legacy_unversioned_business: {sorted(regressed)}"
    )
    versioned = _raster_versioned_routes()
    missing = migrated - versioned
    assert not missing, f"routes not found as versioned: {sorted(missing)}"


def test_real_consumer_call_sites_reference_the_migrated_path():
    """Falsifies staleness: if raster_service_client.py reverts a migrated call site
    back to its bare path without this test being updated, the literal string search
    below breaks loudly instead of silently describing a regressed route as migrated."""
    client = (ROOT / "services" / "sahool-platform" / "api" / "raster_service_client.py").read_text(
        encoding="utf-8"
    )
    assert 'f"/v1/jobs/{job_id}/result"' in client
    assert 'f"/jobs/{job_id}/result"' not in client
    assert '"/v1/indices"' in client
    assert '"/indices"' not in client
    assert '"/v1/process/batch"' in client
    assert '"/process/batch"' not in client


def test_pr_r4_tile_routes_have_no_stale_bare_path_reference():
    """PR-R4 has zero confirmed live external consumers (see plan doc's exhaustive
    search), so there's no lock-step client update to pin -- but the embedded
    self-referential fallback URL in tiles.py must stay migrated."""
    tiles = (ROOT / "services" / "raster-service" / "routers" / "tiles.py").read_text(
        encoding="utf-8"
    )
    assert '@router.get("/v1/tiles/{layer_id}/{z}/{x}/{y}.png")' in tiles
    assert '@router.get("/v1/layers/{layer_id}/tilejson")' in tiles
    assert 'f"/v1/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png"' in tiles
    assert '@router.get("/tiles/{layer_id}/{z}/{x}/{y}.png")' not in tiles
    assert '@router.get("/layers/{layer_id}/tilejson")' not in tiles
