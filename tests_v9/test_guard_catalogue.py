"""The guard catalogue must be derived from its sources, or it is another stale list.

Asked twice whether the session's failures were documented where a developer would find
them, I measured instead of answering. Eleven of twenty-eight lessons were missing from
the runbook, and **no document said what any individual guard enforces** — §1 lists CI
jobs, §3 lists failure classes, neither is a catalogue.

Writing one by hand would go stale on the first guard added. So it is generated from three
sources that are already authoritative — the workflows, the mutation registry, and each
guard's own docstring — and this file pins that it stays derived.

The first generation produced a number nobody had: **218 guards block in CI and 8 are
proven by falsification**. That is not an accusation; it is a measure of what is known
about them, and it is only visible because the catalogue counts rather than describes.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts/ci/guard_catalogue.py"
OUTPUT = ROOT / "docs/runbooks/GUARD_CATALOGUE.md"
REGISTRY = ROOT / "docs/architecture/guard_mutation_registry.json"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load(TOOL, "_guard_catalogue")


def test_the_committed_catalogue_matches_its_sources(tool):
    assert OUTPUT.exists(), "the catalogue was never generated"
    assert OUTPUT.read_text(encoding="utf-8") == tool.render(), (
        "GUARD_CATALOGUE.md drifted; regenerate with python scripts/ci/guard_catalogue.py"
    )


def test_where_each_guard_blocks_is_read_from_the_workflows_not_declared(tool):
    """A hand-written 'runs in' column is the drift this catalogue exists to avoid."""
    invocations = tool.discover_invocations()
    assert invocations, "no guard invocation discovered — the catalogue would be vacuous"
    # A guard everyone knows blocks, discovered rather than listed.
    assert any("verify_all_generated.py" in path for path in invocations)
    source = TOOL.read_text(encoding="utf-8")
    for path in list(invocations)[:20]:
        assert path not in source, f"{path} is hardcoded in the generator"


def test_the_job_attribution_is_parsed_not_pattern_matched(tool):
    """`run:` blocks nest under jobs; a line scanner cannot say which job owns a step.

    This repository has measured the cost of matching text where structure was required
    twice — a compose guard that found a service under `networks:`, and a suite-duplication
    guard that read `pip install ... pytest-asyncio` as a pytest invocation.
    """
    source = TOOL.read_text(encoding="utf-8")
    assert "yaml.safe_load" in source
    for workflow, job in next(iter(tool.discover_invocations().values())):
        assert workflow.endswith((".yml", ".yaml"))
        assert job and " " not in job


def test_what_each_guard_catches_comes_from_the_mutation_registry(tool):
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["mutated"]
    rendered = tool.render()
    for name, spec in registry.items():
        if f"`{name}`" not in rendered:
            continue  # not invoked by any workflow; reported in its own section
        for mutation in spec["mutations"]:
            assert mutation["why"] in rendered, (
                f"{name}: the registry's own wording must appear, not a paraphrase"
            )
            assert mutation["expect"] in rendered


def test_the_unproven_guards_are_counted_not_hidden(tool):
    """The uncomfortable number is the point; a catalogue that omitted it would flatter."""
    rendered = tool.render()
    invocations = tool.discover_invocations()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["mutated"]
    unproven = sum(1 for path in invocations if Path(path).name not in registry)
    assert str(unproven) in rendered, "the count of unfalsified guards must be stated"
    assert unproven > 0, "if this ever reaches zero, delete this assertion and celebrate"


def test_check_mode_fails_on_drift(tool, tmp_path, monkeypatch):
    """Without this, `--check` could return 0 unconditionally and nobody would notice."""
    probe = tmp_path / "catalogue.md"
    probe.write_text("stale", encoding="utf-8")
    monkeypatch.setattr(tool, "OUTPUT", probe)
    assert tool.main(["--check"]) == 1
    probe.write_text(tool.render(), encoding="utf-8")
    assert tool.main(["--check"]) == 0


def test_the_catalogue_states_what_it_does_not_cover():
    """A guard invoked via pytest or bash is invisible here, and saying so is the honesty.

    §1 of the runbook counts more gates than this file lists. Without the stated limit a
    reader would take 218 as the total and conclude the rest do not exist.
    """
    text = OUTPUT.read_text(encoding="utf-8")
    assert "حدّ الصدق" in text
    assert "pytest" in text and "bash" in text


def test_the_sweep_discovers_the_catalogue_on_its_own():
    """`verify_all_generated` reads its steps from the workflows; no manual registration."""
    sweep = _load(ROOT / "scripts/ci/verify_all_generated.py", "_sweep_probe")
    discovered = [step for step in sweep.discover() if "guard_catalogue" in step[0]]
    assert discovered, "the sweep must pick the catalogue up from the workflow"
    assert discovered[0][1] == ["--check"]
