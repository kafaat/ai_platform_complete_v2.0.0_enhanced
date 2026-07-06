"""Guard: CDSE live-tile regressions stay fixed.

Two regressions turned previously-rendering pixel tiles blank:

1. The "latest" scene window was narrowed from year-to-date to a fixed 60 days
   (``LATEST_WINDOW_DAYS = 60``). If the newest ≤40%-cloud Sentinel-2 scene over a
   field was older than 60 days, the Process API returned an empty/all-NaN result
   and every tile went transparent. The window must be wide (≥180d) and env-tunable.

2. The tile COG fetch (Process API + throttle + transport/429 retry) ran under a
   single **global** asyncio lock, so one slow/failing fetch blocked EVERY field's
   tiles (map-wide blank). It must single-flight per cache key instead — the global
   lock only guards the cache dict + lock registry, never the network fetch.

Evidence:
- services/raster-service/routers/cdse_tiles.py :: LATEST_WINDOW_DAYS / _ensure_clipped_cog
- services/raster-service/cdse_singleflight.py :: cdse_lock / cdse_key_lock
  (re-exported by services/raster-service/main.py as _cdse_lock / _cdse_key_lock)
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_TILES = _ROOT / "services" / "raster-service" / "routers" / "cdse_tiles.py"
# The latest-window knob and the per-key single-flight tile-fetch path were
# extracted from the thin router into raster_cdse_tile_runtime.py (phase16).
_RUNTIME = _ROOT / "services" / "raster-service" / "raster_cdse_tile_runtime.py"
_MAIN = _ROOT / "services" / "raster-service" / "main.py"
# Single-flight lock state/helpers were decomposed out of main.py into this
# sibling module; main.py keeps thin _cdse_* alias re-exports of these.
_SINGLEFLIGHT = _ROOT / "services" / "raster-service" / "cdse_singleflight.py"


def test_latest_window_is_wide_and_env_tunable():
    # LATEST_WINDOW_DAYS now lives in the extracted runtime module.
    src = _TILES.read_text(encoding="utf-8") + "\n" + _RUNTIME.read_text(encoding="utf-8")
    # env-tunable, and the default must NOT be the regressing 60-day window.
    assert 'os.getenv("CDSE_LATEST_WINDOW_DAYS"' in src
    assert "LATEST_WINDOW_DAYS = int(" in src
    assert "LATEST_WINDOW_DAYS = 60" not in src


def test_tile_fetch_single_flights_per_key_not_under_global_lock():
    main_src = _MAIN.read_text(encoding="utf-8")
    # The tile-fetch path (which acquires the per-key lock and prunes stale locks)
    # was extracted from the router into raster_cdse_tile_runtime.py; read both so
    # the contract follows the moved code.
    tiles_src = _TILES.read_text(encoding="utf-8") + "\n" + _RUNTIME.read_text(encoding="utf-8")
    singleflight_src = _SINGLEFLIGHT.read_text(encoding="utf-8")
    # The single-flight state/helpers were moved into cdse_singleflight.py (renamed
    # without the leading underscore) and re-exported by main under the historical
    # _cdse_* names. Read the combined source so the contract follows the moved code.
    combined = main_src + "\n" + singleflight_src
    # per-key lock helper exists (in the module) and is re-exported + used by the
    # tile fetch path via main's alias.
    assert "def cdse_key_lock(" in combined
    assert "_cdse_key_lock = cdse_singleflight.cdse_key_lock" in main_src
    assert "cdse_key_locks" in combined
    # stale key-locks are pruned so the registry doesn't grow unbounded.
    assert "def cdse_prune_key_locks_locked(" in combined
    # Extraction dropped the leading-underscore aliases in the tile-fetch path: the
    # runtime calls the bare cdse_singleflight helpers directly. The bare names are
    # substrings of the old _cdse_* needles, so the contract is unchanged.
    assert "cdse_prune_key_locks_locked()" in tiles_src
    assert "cdse_singleflight.cdse_key_lock(" in tiles_src
    # the network fetch (process_index via run_in_executor) must run under the
    # per-key lock, so the global lock is not held across the CDSE call.
    assert "async with key_lock:" in tiles_src
