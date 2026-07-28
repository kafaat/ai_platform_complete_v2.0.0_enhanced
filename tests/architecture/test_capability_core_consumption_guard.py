"""The capability-core ratchet must be falsifiable, not decorative.

CAPABILITY-CORES-NOT-WIRED exists because passing capability tests proves a module is
correct, not that it entered the production path. This guard is the mechanism that keeps
a wired core from silently drifting back to orphaned, so these tests pin the two ways that
drift actually happens: the consumer quietly stops importing it, or the registry quietly
downgrades it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts/ci/capability_core_consumption_guard.py"
REGISTRY = ROOT / "docs/architecture/capability_core_consumption_registry.json"

pytestmark = pytest.mark.unit


def _run() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD), "--check"], capture_output=True, text=True, cwd=ROOT
    )


@pytest.fixture
def restore_tree():
    """Snapshot the files a case mutates, and put them back however the case ends."""
    saved: dict[Path, str] = {}

    def snapshot(path: Path) -> Path:
        saved[path] = path.read_text(encoding="utf-8")
        return path

    yield snapshot
    for path, text in saved.items():
        path.write_text(text, encoding="utf-8")


def test_guard_passes_on_the_current_tree():
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "capability core consumption guard: PASS" in result.stdout


def test_guard_reports_the_wired_count_and_the_pending_remainder():
    """The count is the ratchet, so it has to be visible rather than implied."""
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    total = len(document["cores"])
    wired = sum(1 for core in document["cores"] if core["status"] == "wired")
    out = _run().stdout
    assert f"({wired}/{total} cores wired)" in out
    if wired < total:
        assert f"{total - wired} core(s) still pending" in out


def test_losing_the_consumer_import_fails(restore_tree):
    """The regression this ratchet exists for: a wired core drifting back to orphaned."""
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    wired = next(c for c in document["cores"] if c["status"] == "wired")
    consumer = restore_tree(ROOT / wired["consumer"])
    module_dotted = wired["module"].split("services/sahool-platform/", 1)[-1][:-3].replace("/", ".")
    text = consumer.read_text(encoding="utf-8")
    consumer.write_text(
        text.replace(f"from {module_dotted} import {wired['consumed_symbol']}", ""),
        encoding="utf-8",
    )
    result = _run()
    assert result.returncode == 1
    assert "must import" in result.stdout


def test_a_docstring_mention_is_not_accepted_as_a_consumer(restore_tree):
    """AST-only: naming the symbol in prose must not satisfy the ratchet."""
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    wired = next(c for c in document["cores"] if c["status"] == "wired")
    consumer = restore_tree(ROOT / wired["consumer"])
    module_dotted = wired["module"].split("services/sahool-platform/", 1)[-1][:-3].replace("/", ".")
    text = consumer.read_text(encoding="utf-8")
    text = text.replace(f"from {module_dotted} import {wired['consumed_symbol']}", "")
    consumer.write_text(
        f'"""Mentions {wired["consumed_symbol"]} from {module_dotted} in prose only."""\n' + text,
        encoding="utf-8",
    )
    result = _run()
    assert result.returncode == 1, "a prose mention must not count as consumption"


def test_downgrading_a_wired_core_to_pending_fails(restore_tree):
    """A core may not lose its wired status while its consumer is still declared."""
    registry = restore_tree(REGISTRY)
    document = json.loads(registry.read_text(encoding="utf-8"))
    next(c for c in document["cores"] if c["status"] == "wired")["status"] = "pending_wiring"
    registry.write_text(json.dumps(document, indent=2), encoding="utf-8")
    result = _run()
    assert result.returncode == 1
    assert "pending_wiring but a consumer is declared" in result.stdout


def test_claiming_wired_without_a_consumer_fails(restore_tree):
    """The inverse bluff: declaring wired with nothing to point at."""
    registry = restore_tree(REGISTRY)
    document = json.loads(registry.read_text(encoding="utf-8"))
    pending = next(c for c in document["cores"] if c["status"] == "pending_wiring")
    pending["status"] = "wired"
    registry.write_text(json.dumps(document, indent=2), encoding="utf-8")
    result = _run()
    assert result.returncode == 1
    assert "no consumer/symbol declared" in result.stdout


def test_a_missing_core_module_fails(restore_tree):
    registry = restore_tree(REGISTRY)
    document = json.loads(registry.read_text(encoding="utf-8"))
    document["cores"][0]["module"] = "services/sahool-platform/core/does_not_exist.py"
    registry.write_text(json.dumps(document, indent=2), encoding="utf-8")
    result = _run()
    assert result.returncode == 1
    assert "core module missing" in result.stdout


def test_registry_tracks_exactly_the_open_gap_cores():
    """Scope check: this ratchet must not drift onto the optional-activation capabilities.

    Those are governed by capability_core_consumer_gate.py and share only the word
    "capability". Conflating them would report CAPABILITY-CORES-NOT-WIRED closed while
    these cores are still orphaned — the exact confusion that produced this guard.
    """
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    modules = {core["module"] for core in document["cores"]}
    assert modules == {
        "services/sahool-platform/core/equipment_intelligence.py",
        "services/sahool-platform/core/canonical_field_state.py",
        "services/sahool-platform/core/yield_intelligence.py",
        "services/sahool-platform/core/economic_scenarios.py",
    }
    # Check the tracked entries only. The registry's prose deliberately NAMES those other
    # capabilities to document the distinction, so scanning the whole file would trip on
    # the very explanation that prevents the confusion.
    tracked = json.dumps(document["cores"])
    for forbidden in ("pest_detector", "yield_estimator", "field_boundary_backends", "aquacrop"):
        assert forbidden not in tracked, (
            f"{forbidden} belongs to optional-capability activation, not to this gap"
        )


def test_guard_is_wired_into_ci():
    workflow = (ROOT / ".github/workflows/capability-governance.yml").read_text(encoding="utf-8")
    assert "capability_core_consumption_guard.py --check" in workflow


def test_importing_the_guard_runs_nothing():
    """Importing must not execute the check — only ``--check`` may, so nothing can
    accidentally pass or fail the ratchet as a side effect of an import."""
    probe = (
        "import importlib.util,sys;"
        f"spec=importlib.util.spec_from_file_location('g',r'{GUARD}');"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        "print('IMPORTED_CLEAN', callable(m.check))"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "IMPORTED_CLEAN True"
    assert "guard:" not in result.stdout, "import must not emit a verdict"
