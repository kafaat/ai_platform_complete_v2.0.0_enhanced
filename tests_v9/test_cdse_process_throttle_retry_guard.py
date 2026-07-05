"""Guard: CDSE Process API keeps its 429 throttle + bounded retry loop.

CI unit (``pytest -m unit``, ``testpaths = tests_v9``) does not collect the
co-located behavioural test in ``services/raster-service/`` — this static guard
ensures the throttle/retry contract in ``cdse_client.process_index`` cannot
silently regress back to a single un-throttled POST that burns CDSE quota and
loses backfill scenes on 429.

Evidence for the contract:
- services/raster-service/cdse_client.py :: _throttle_process_api / process_index
- services/raster-service/test_cdse_process_rate_limit.py (behavioural)
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_CDSE_CLIENT = (
    Path(__file__).resolve().parents[1] / "services" / "raster-service" / "cdse_client.py"
)


def _source() -> str:
    return _CDSE_CLIENT.read_text(encoding="utf-8")


def test_cdse_client_exists():
    assert _CDSE_CLIENT.is_file(), f"missing {_CDSE_CLIENT}"


def test_process_api_has_cross_thread_throttle():
    src = _source()
    # Process-wide minimum spacing gate + its lock and env knob.
    assert "def _throttle_process_api()" in src
    assert "_PROCESS_RATE_LOCK" in src
    assert "CDSE_PROCESS_MIN_INTERVAL_SECONDS" in src


def test_process_index_retries_on_429_with_bounded_backoff():
    src = _source()
    # The throttle must be invoked from the request path and 429 handled with a
    # bounded, env-tunable retry loop that honours Retry-After.
    assert "_throttle_process_api()" in src
    assert "CDSE_PROCESS_MAX_RETRIES" in src
    assert "CDSE_PROCESS_RETRY_BASE_SECONDS" in src
    assert "CDSE_PROCESS_RETRY_MAX_SECONDS" in src
    assert "429" in src
    assert "Retry-After" in src
    assert "def _retry_after_seconds(" in src


def test_transient_transport_errors_are_retried_not_dropped():
    src = _source()
    # An SSL/connection cut (`UNEXPECTED_EOF_WHILE_READING` ⇒ httpx.TransportError)
    # must NOT fail the pixel-tile fetch on the first blip nor be silently swallowed
    # to an empty scene list: both the Process API COG fetch and the STAC catalog
    # search retry transient transport errors with backoff before giving up.
    assert "except httpx.TransportError" in src
    # It appears in both request paths (process_index COG fetch + search_scenes STAC).
    assert src.count("except httpx.TransportError") >= 2


def test_compose_wires_throttle_env_for_raster_and_worker():
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.v9.yml").read_text(
        encoding="utf-8"
    )
    # Both the raster-service and the standalone backfill scan worker must carry
    # the same account-level throttle env so neither path can burst CDSE alone.
    assert compose.count("CDSE_PROCESS_MIN_INTERVAL_SECONDS") >= 2
    assert compose.count("CDSE_PROCESS_MAX_RETRIES") >= 2
