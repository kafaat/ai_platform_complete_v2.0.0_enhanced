"""Two tools answering "what does my change affect?" must give one answer.

``scripts/ci/capability_impact.py`` is what ``docs/capabilities/CAPABILITY_GOVERNANCE.md``
tells a contributor to run before writing a PR's ``Capability-Impact:`` line.
``scripts/ci/pr_capability_impact_gate.py`` is what blocks the merge. When they disagree,
the contributor is told one number and judged by another — and if the smaller number is
the one anyone acts on, a change escapes impact declaration entirely.

They did disagree. Measured on the fixture below before the fix:

    direct      legacy=0   gate=5
    affected    legacy=0   gate=12

The legacy walk read only the hand-maintained ``capabilities/registry`` lists; the gate
also reads the generated ``capability_mapping.json``, which maps real repository paths to
capabilities by dimension. Every missed capability came through that map, so the gap grew
with the diff rather than being one stray identifier.

The fix was one engine, not a patched second one. These tests hold that shape.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CI_DIR = ROOT / "scripts" / "ci"
if str(CI_DIR) not in sys.path:
    sys.path.insert(0, str(CI_DIR))

# One fixed fixture, deliberately spanning dimensions a single-registry walk cannot see:
# platform API, a migration, a worker, e2e scripts, compose, and the frontend.
FIXTURE = (
    "scripts/workers/canonical_execution_learning_worker.py",
    "services/sahool-platform/api/persisted_canonical_repositories.py",
    "services/sahool-platform/api/learning_feedback.py",
    "services/sahool-platform/api/irrigation_closed_loop_runtime.py",
    "scripts/e2e/canonical_projection_jetstream_roundtrip.py",
    "tests_v9/test_canonical_event_emission_contracts.py",
    "docker-compose.v9.yml",
    "migrations/v11_events_bus.sql",
    "frontend/src/sections/MapHub.tsx",
)


def _load(module_name: str):
    """Import by name, not by spec.

    Loading these by ``spec_from_file_location`` without registering the result in
    ``sys.modules`` breaks ``@dataclass``: it resolves field types through
    ``sys.modules[cls.__module__]``, which is ``None`` for an unregistered module, and
    the gate's ``Reference``/``Snapshot`` blow up at import time.
    """
    return importlib.import_module(module_name)


def test_the_advisory_tool_and_the_blocking_gate_return_the_same_verdict():
    gate = _load("pr_capability_impact_gate")
    tool = _load("capability_impact")

    expected = gate.impact(list(FIXTURE), gate.current_snapshot())
    actual = tool.compute(list(FIXTURE))

    for key in ("direct", "transitive", "affected"):
        assert actual[key] == expected[key], (
            f"{key} diverged — advisory={actual[key]} gate={expected[key]}"
        )


def test_the_fixture_is_wide_enough_for_a_divergence_to_show():
    """A fixture that maps to nothing would make the parity test vacuously green.

    This is the failure mode the parity check itself must not have: two tools agreeing
    on an empty answer prove nothing. The pre-fix measurement is the calibration — the
    gate found 5 direct and 12 affected here.
    """
    gate = _load("pr_capability_impact_gate")
    result = gate.impact(list(FIXTURE), gate.current_snapshot())

    assert len(result["direct"]) >= 4, (
        f"fixture no longer exercises direct edges: {result['direct']}"
    )
    assert len(result["affected"]) > len(result["direct"]), (
        "fixture no longer exercises dependency traversal"
    )
    dimensions = {
        source
        for sources in result["matched_sources"].values()
        for source in sources
        if source.startswith("mapping:")
    }
    assert len(dimensions) >= 3, (
        f"fixture must span several mapping dimensions; spans only {sorted(dimensions)}"
    )


def test_the_advisory_tool_holds_no_second_implementation_of_the_engine():
    """It must call the gate's engine, not re-derive capabilities from the registry.

    The divergence was never a wrong line — it was a second walk over a narrower source.
    A tool that rebuilds its own reference index will drift again the next time the gate
    learns a dimension, and the parity test above would only notice after the fact.
    """
    text = (ROOT / "scripts/ci/capability_impact.py").read_text(encoding="utf-8")
    assert "from pr_capability_impact_gate import" in text
    assert "capabilities/registry" not in text.split('"""', 2)[-1], (
        "the advisory tool must not read the registry directly; the engine owns that"
    )
