"""Phase 2 P2-c — static bypass guard for the satellite_cdse restricted adapter (proof #6).

The activation gate only means something if there is exactly ONE way for raster-service to select
CDSE as the historical imagery source. This guard enforces that:

  1. The two provider-selection chokepoints (scene search + the CDSE processing route) consult
     ``imagery_source_gate`` before choosing CDSE.
  2. The set of modules that touch the raw CDSE scene-selection primitives
     (``search_scenes(`` / ``stac_search_cdse(`` / ``get_client()``) is a fixed, reviewed
     allowlist — a NEW module reaching those primitives fails this guard, forcing a reviewer to
     confirm it routes through the gate rather than silently bypassing it.
  3. The adapter's fail-closed path returns the Element84 fallback, never CDSE.

Scope honesty: this slice gates the SEARCH and PROCESSING pipeline. The on-demand CDSE
tile-render path (``routers/cdse_tiles.py`` / ``raster_cdse_tile_runtime.py``) is a distinct
surface and is a documented remainder (``TILE_PATH_REMAINDER``) for a follow-up slice — it is not
silently claimed as covered.

Static source scan — no runtime, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SERVICE_DIR = Path(__file__).resolve().parent

# Chokepoints that MUST route CDSE selection through the gate.
GATE_CONSULTING_CHOKEPOINTS = {
    "stac_search.py": ("imagery_source_gate", "resolve_active_source"),
    "routers/fields.py": ("imagery_source_gate", "resolve_active_source"),
}

# Modules permitted to touch the raw CDSE scene-selection primitives. Each is either the client
# itself, the gate-guarded search dispatch, or a step that runs AFTER authorization at a chokepoint.
DIRECT_CDSE_ALLOWLIST = {
    "cdse_client.py",  # the client library itself
    "stac_search.py",  # gate-guarded search dispatch (chokepoint)
    "raster_cdse_processing.py",  # runs under a job authorized at the process-cdse chokepoint
    "raster_backfill_scene_processing.py",  # backfill worker, runs under an authorized scan
    "raster_cdse_tile_runtime.py",  # on-demand tile render — see TILE_PATH_REMAINDER
}

# Explicit, non-silent remainder: the live tile-render surface is not gated by this slice.
TILE_PATH_REMAINDER = {"raster_cdse_tile_runtime.py", "routers/cdse_tiles.py"}

_SELECTION_PRIMITIVES = ("search_scenes(", "stac_search_cdse(", "get_client()")


def _iter_modules():
    for path in SERVICE_DIR.rglob("*.py"):
        name = path.name
        rel = str(path.relative_to(SERVICE_DIR))
        if name.startswith("test_") or "/tests/" in rel or rel.startswith("tests/"):
            continue
        yield rel, path.read_text(encoding="utf-8")


def test_chokepoints_consult_the_gate():
    for rel, (needle_a, needle_b) in GATE_CONSULTING_CHOKEPOINTS.items():
        src = (SERVICE_DIR / rel).read_text(encoding="utf-8")
        assert needle_a in src, f"{rel} must import the restricted adapter ({needle_a})"
        assert needle_b in src, f"{rel} must consult the gate ({needle_b})"


def test_no_new_module_bypasses_the_restricted_adapter():
    offenders = set()
    for rel, src in _iter_modules():
        if any(prim in src for prim in _SELECTION_PRIMITIVES):
            offenders.add(rel)
    unexpected = offenders - DIRECT_CDSE_ALLOWLIST
    assert not unexpected, (
        "New module(s) reach the raw CDSE selection primitives without review: "
        f"{sorted(unexpected)}. Route them through imagery_source_gate.resolve_active_source(), "
        "then add to DIRECT_CDSE_ALLOWLIST with justification."
    )


def test_adapter_fail_closed_returns_element84_never_cdse():
    src = (SERVICE_DIR / "imagery_source_gate.py").read_text(encoding="utf-8")
    # The fail-closed helper must hard-code the fallback source, not the primary.
    fc = src.split("def _fail_closed(")[1].split("\ndef ")[0]
    assert "provider=FALLBACK_SOURCE" in fc
    assert "provider=PRIMARY_SOURCE" not in fc


def test_tile_path_remainder_is_recorded_honestly():
    # This is a scope marker, not a coverage claim: the tile-render modules exist and are
    # deliberately excluded from this slice's search/processing gating.
    for rel in TILE_PATH_REMAINDER:
        assert (SERVICE_DIR / rel).exists(), f"documented remainder path missing: {rel}"
