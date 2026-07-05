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
- services/raster-service/main.py :: _cdse_lock / _cdse_key_lock
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_TILES = _ROOT / "services" / "raster-service" / "routers" / "cdse_tiles.py"
_MAIN = _ROOT / "services" / "raster-service" / "main.py"


def test_latest_window_is_wide_and_env_tunable():
    src = _TILES.read_text(encoding="utf-8")
    # env-tunable, and the default must NOT be the regressing 60-day window.
    assert 'os.getenv("CDSE_LATEST_WINDOW_DAYS"' in src
    assert "LATEST_WINDOW_DAYS = int(" in src
    assert "LATEST_WINDOW_DAYS = 60" not in src


def test_tile_fetch_single_flights_per_key_not_under_global_lock():
    main_src = _MAIN.read_text(encoding="utf-8")
    tiles_src = _TILES.read_text(encoding="utf-8")
    # per-key lock helper exists and is used by the tile fetch path.
    assert "def _cdse_key_lock(" in main_src
    assert "_cdse_key_locks" in main_src
    assert "main._cdse_key_lock(" in tiles_src
    # the network fetch (process_index via run_in_executor) must run under the
    # per-key lock, so the global lock is not held across the CDSE call.
    assert "async with key_lock:" in tiles_src
