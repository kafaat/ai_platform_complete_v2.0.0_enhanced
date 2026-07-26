"""Regression guard for the scout-ingest projection worker crash-loop (Finding 4).

When ``SCOUT_INGEST_PROJECTION_ENABLED`` is off the worker used to ``return``
immediately; with ``restart: unless-stopped`` + a ``pgrep`` liveness healthcheck this
produced an endless container restart loop (80+ restarts observed). The fix idles the
disabled worker (stays alive, negligible CPU) instead of exiting.

Static source scan (no import): the worker module imports ``shared.*`` at top, which is
a known high-collision package under the unit runner, so we assert the fix on the source
text rather than executing it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "services" / "scout-ingest-service" / "projection_worker.py"


@pytest.mark.unit
def test_disabled_worker_idles_instead_of_exiting():
    src = WORKER.read_text(encoding="utf-8")
    tree = ast.parse(src)

    loop_fn = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "loop"
        ),
        None,
    )
    assert loop_fn is not None, "async loop() not found in projection_worker"

    # The disabled branch is the `if not enabled():` block at the top of loop().
    disabled_branch = next(
        (n for n in loop_fn.body if isinstance(n, ast.If)),
        None,
    )
    assert disabled_branch is not None, "disabled-guard `if not enabled():` not found"

    # It must NOT exit immediately (a bare `return` re-triggers the restart loop)...
    assert not any(isinstance(n, ast.Return) for n in ast.walk(disabled_branch)), (
        "disabled branch must idle, not return (would crash-loop the container)"
    )

    # ...it must idle via an await-sleep loop instead.
    has_idle_sleep = any(
        isinstance(n, ast.While)
        and any(
            isinstance(a, ast.Await)
            and isinstance(a.value, ast.Call)
            and isinstance(a.value.func, ast.Attribute)
            and a.value.func.attr == "sleep"
            for a in ast.walk(n)
        )
        for n in ast.walk(disabled_branch)
    )
    assert has_idle_sleep, "disabled branch must idle via `while True: await asyncio.sleep(...)`"
