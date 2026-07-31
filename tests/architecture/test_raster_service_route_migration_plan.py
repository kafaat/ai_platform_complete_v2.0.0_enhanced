"""Pins the raster-service legacy_unversioned_business baseline (30 routes) and its
ownership-bucket classification established in
docs/architecture/raster_service_route_migration_plan.md (PR-R1 of the raster-service
slice of API-VERSIONING-GUARD-IS-A-MIRROR-01).

A route landing in the wrong bucket, a route silently disappearing, or a new
unversioned route appearing without classification all fail this test -- matching the
falsification discipline used for the Option B classifier fix (PR #722).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import api_versioning_policy_guard as guard  # noqa: E402

pytestmark = pytest.mark.unit

# PR-R2 -- internal and operational routes (8). All require_service_token.
PR_R2 = {
    ("GET", "/jobs/{job_id}"),
    ("GET", "/jobs/{job_id}/result"),
    ("POST", "/upload/raster"),
    ("POST", "/upload/drone"),
    ("GET", "/storage/stats"),
    ("POST", "/storage/cleanup"),
    ("GET", "/offline/packs"),
    ("GET", "/offline/packs/{pack_name}"),
}

# PR-R3 -- imagery/catalog/process routes (20).
PR_R3 = {
    ("POST", "/zones/classify"),
    ("POST", "/change/detect"),
    ("POST", "/fvc/compute"),
    ("POST", "/sar/rvi"),
    ("POST", "/terrain/slope"),
    ("GET", "/cog/validate"),
    ("POST", "/salinity/classify"),
    ("POST", "/salinity/calibrate"),
    ("POST", "/process"),
    ("POST", "/raw/process"),
    ("POST", "/process/batch"),
    ("GET", "/stac"),
    ("GET", "/stac/collections"),
    ("POST", "/stac/mosaicjson"),
    ("GET", "/info/{layer_id}"),
    ("GET", "/indices"),
    ("GET", "/imagery/timeseries"),
    ("POST", "/imagery/timeseries/analyze"),
    ("POST", "/imagery/timeseries/parallel"),
    ("GET", "/gis/admin-boundaries"),
}

# PR-R4 -- tile and rendering routes (2). layer_scoped; no live caller found (see plan doc).
PR_R4 = {
    ("GET", "/tiles/{layer_id}/{z}/{x}/{y}.png"),
    ("GET", "/layers/{layer_id}/tilejson"),
}

ALL_BUCKETED = PR_R2 | PR_R3 | PR_R4

# Routes confirmed to have a real internal service-to-service consumer
# (services/sahool-platform/api/raster_service_client.py) that must be updated in the
# same PR as any path migration -- not deferred to a later slice.
REAL_CONSUMERS = {
    ("GET", "/jobs/{job_id}/result"): "raster_service_client.py:466 get_job_result",
    ("GET", "/indices"): "raster_service_client.py:182 get_indices_sync",
    ("POST", "/process/batch"): "raster_service_client.py:448 process_indicator_batch",
}


def _raster_legacy_routes() -> set[tuple[str, str]]:
    rows = guard.collect()
    return {
        (r["method"], r["path"])
        for r in rows
        if r["service"] == "raster-service" and r["classification"] == "legacy_unversioned_business"
    }


def test_pr_bucket_sets_are_disjoint_and_cover_exactly_thirty_routes():
    assert PR_R2 & PR_R3 == set()
    assert PR_R2 & PR_R4 == set()
    assert PR_R3 & PR_R4 == set()
    assert len(ALL_BUCKETED) == 30, f"expected 30 bucketed routes, got {len(ALL_BUCKETED)}"


def test_measured_baseline_matches_the_bucketed_classification():
    measured = _raster_legacy_routes()
    missing_from_plan = measured - ALL_BUCKETED
    assert not missing_from_plan, (
        f"raster-service legacy_unversioned_business routes not classified in "
        f"docs/architecture/raster_service_route_migration_plan.md: {sorted(missing_from_plan)}"
    )
    no_longer_legacy = ALL_BUCKETED - measured
    assert not no_longer_legacy, (
        f"routes in the migration plan no longer measured as legacy_unversioned_business "
        f"for raster-service (already migrated? update the plan doc and this test): "
        f"{sorted(no_longer_legacy)}"
    )


def test_real_consumers_are_a_subset_of_the_bucketed_routes():
    for route in REAL_CONSUMERS:
        assert route in ALL_BUCKETED, f"{route} has a real consumer but is not bucketed"


def test_real_consumer_call_sites_still_reference_the_bare_path():
    """Falsifies staleness: if raster_service_client.py migrates a call site to /v1/...
    without this test being updated in the same PR, the literal bare-path string search
    below breaks loudly instead of silently describing an already-migrated route as a
    pending real-consumer risk."""
    client = (ROOT / "services" / "sahool-platform" / "api" / "raster_service_client.py").read_text(
        encoding="utf-8"
    )
    assert "/jobs/{job_id}/result" in client
    assert '"/indices"' in client
    assert '"/process/batch"' in client
