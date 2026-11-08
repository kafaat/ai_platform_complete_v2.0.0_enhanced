"""Regression: adding a CI skill changes tracked scanner inputs, not domain evidence.

The generated-artifact check is exercised separately by
tests/architecture/test_capability_mapping_engine.py. These tests make the
source-driven accounting contract explicit and guard against silently
excluding skill files to force a green mapping.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_FILES = (
    ".claude/skills/ci-impact-preflight/SKILL.md",
    ".claude/skills/ci-impact-preflight/PILOT_CASES.md",
)


def _engine():
    location = ROOT / "scripts/ci/capability_mapping_engine.py"
    spec = importlib.util.spec_from_file_location("ci_skill_mapping_engine", location)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_files_are_scanned_and_counted_without_hidden_exclusion():
    engine = _engine()
    paths = [p.relative_to(ROOT).as_posix() for p in engine.iter_files()]
    for path in SKILL_FILES:
        assert path in paths
        assert engine.classify(path) == "other"
    output = json.loads(
        (engine.OUT / "capability_mapping.json").read_text(encoding="utf-8")
    )
    assert output["summary"]["files_scanned"] == len(paths)
    assert output["summary"]["files_by_kind"]["other"] == sum(
        engine.classify(path) == "other" for path in paths
    )


def test_pilot_skill_documentation_is_not_promoted_to_domain_implementation():
    engine = _engine()
    capabilities = engine.load_registry()
    for rel in SKILL_FILES:
        contents = (ROOT / rel).read_text(encoding="utf-8")
        hay = engine.norm(contents[:250_000])
        hay_path = engine.norm(rel)
        for capability in capabilities:
            score, _ = engine.score_blob(
                capability["id"], capability, rel, hay_path, hay, contents
            )
            assert score < 8, (rel, capability["id"], score)
