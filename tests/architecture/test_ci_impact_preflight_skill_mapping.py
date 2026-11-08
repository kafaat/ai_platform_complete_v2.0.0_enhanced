"""Regression: adding a CI skill changes tracked scanner inputs, not domain evidence.

The generated-artifact check is exercised separately by
tests/architecture/test_capability_mapping_engine.py. These tests make the
source-driven accounting contract explicit and guard against silently
excluding skill files to force a green mapping.
"""

import hashlib
import importlib.util
import json
import subprocess
import sys
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
    output_path = engine.OUT / "capability_mapping.json"
    output = json.loads(output_path.read_text(encoding="utf-8"))
    summary = output["summary"]
    assert summary["files_scanned"] == len(paths)
    other_count = sum(engine.classify(path) == "other" for path in paths)
    assert summary["files_by_kind"]["other"] == other_count


def test_pilot_skill_documentation_is_not_promoted_to_domain_implementation():
    engine = _engine()
    capabilities = engine.load_registry()
    for rel in SKILL_FILES:
        contents = (ROOT / rel).read_text(encoding="utf-8")
        hay = engine.norm(contents[:250_000])
        hay_path = engine.norm(rel)
        for capability in capabilities:
            args = (capability["id"], capability, rel, hay_path, hay, contents)
            score, _ = engine.score_blob(*args)
            assert score < 8, (rel, capability["id"], score)


def test_skill_documents_existing_generated_sweep_check_flag():
    skill = (ROOT / SKILL_FILES[0]).read_text(encoding="utf-8")
    assert "verify_all_generated.py --check" in skill
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/verify_all_generated.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--check" in result.stdout


def test_current_impact_index_binds_workflow_sha256():
    workflow = ROOT / ".github/workflows/capability-governance.yml"
    index_path = ROOT / "docs/capability-registry/generated/impact/impact_index_summary.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    actual = hashlib.sha256(workflow.read_bytes()).hexdigest()
    assert index["inputs"][".github/workflows/capability-governance.yml"] == actual
