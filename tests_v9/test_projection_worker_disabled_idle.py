"""Regression guard for the scout-ingest projection worker crash-loop (Finding 4).

When ``SCOUT_INGEST_PROJECTION_ENABLED`` is off the worker used to ``return``
immediately; with ``restart: unless-stopped`` + a ``pgrep`` liveness healthcheck this
produced an endless container restart loop (80+ restarts observed). The fix idles the
disabled worker (stays alive, negligible CPU) instead of exiting. This test proves the
disabled ``loop()`` blocks rather than returning.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "services" / "scout-ingest-service" / "projection_worker.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("projection_worker_under_test", WORKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_disabled_worker_idles_instead_of_exiting(monkeypatch):
    monkeypatch.setenv("SCOUT_INGEST_PROJECTION_ENABLED", "0")
    m = _load_module()
    assert m.enabled() is False

    async def _run():
        # A disabled worker MUST block (idle), not return — else the container
        # crash-loops. wait_for times out iff loop() is still running.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(m.loop(), timeout=0.2)

    asyncio.run(_run())
