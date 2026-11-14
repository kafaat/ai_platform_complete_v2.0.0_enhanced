"""Regression: adding a CI skill changes tracked scanner inputs, not domain evidence.

The generated-artifact check is exercised separately by
tests/architecture/test_capability_mapping_engine.py. These tests make the
source-driven accounting contract explicit and guard against silently
excluding skill files to force a green mapping.
"""

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_FILES = (
    ".claude/skills/ci-impact-preflight/SKILL.md",
    ".claude/skills/ci-impact-preflight/PILOT_CASES.md",
    ".claude/skills/ci-impact-preflight/EVALUATION.md",
    ".claude/skills/ci-impact-preflight/trigger_scenarios.json",
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
        # The engine's own reading (raw for Markdown/JSON since #1361), not a copy of it.
        reading = engine.scoring_text(rel, contents, engine.classify(rel))
        for capability in capabilities:
            args = (capability["id"], capability, rel, reading.hay_path, reading.hay)
            score, _ = engine.score_blob(*args, reading.id_text)
            assert score < 8, (rel, capability["id"], score)


def test_skill_documents_existing_generated_sweep_check_flag():
    skill = (ROOT / SKILL_FILES[0]).read_text(encoding="utf-8")
    assert "verify_all_generated.py --check" in skill
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/verify_all_generated.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert "--check" in result.stdout


def test_current_impact_index_binds_workflow_sha256():
    workflow = ROOT / ".github/workflows/capability-governance.yml"
    index_path = ROOT / "docs/capability-registry/generated/impact/impact_index_summary.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    actual = hashlib.sha256(workflow.read_bytes()).hexdigest()
    assert index["inputs"][".github/workflows/capability-governance.yml"] == actual


def _skill_text() -> str:
    return (ROOT / SKILL_FILES[0]).read_text(encoding="utf-8")


def test_skill_paths_and_flags_exist_on_the_current_tree():
    """Every repository path the skill names exists, and every flag it passes to a
    script appears in that script's source. A stale command is how #1354 went stale."""
    spans = re.findall(r"`([^`]+)`", _skill_text())
    path_re = re.compile(
        r"(?<![\w.-])((?:scripts|docs|services|\.claude)/[\w./-]+\.(?:py|sh|json|md))"
    )
    missing, unknown_flags = [], []
    for span in spans:
        missing += [m for m in path_re.findall(span) if not (ROOT / m).is_file()]
        call = re.search(r"(scripts/[\w./-]+\.(?:py|sh))((?:\s+\S+)*)", span)
        if call and (ROOT / call.group(1)).is_file():
            source = (ROOT / call.group(1)).read_text(encoding="utf-8")
            unknown_flags += [
                (call.group(1), flag)
                for flag in re.findall(r"(?<!\S)(--[\w-]+)", call.group(2))
                if flag not in source
            ]
    assert not missing, missing
    assert not unknown_flags, unknown_flags


def test_skill_stays_advisory_and_is_not_wired_into_ci():
    text = _skill_text()
    assert "Not a CI gate." in text
    assert "It does not authorise a push." in text
    assert "not a prediction that CI will pass" in text
    for phrase in ("Merge only after", "guarantees CI", "CI will be green."):
        assert phrase not in text, phrase
    workflows = sorted((ROOT / ".github/workflows").glob("*.y*ml"))
    assert workflows
    wired = [
        p.name
        for p in workflows
        if ".claude/skills/ci-impact-preflight" in p.read_text(encoding="utf-8")
    ]
    assert not wired, wired


def test_skill_description_fits_the_upload_limit_and_parses():
    location = ROOT / ".claude/skills/skill-evaluator/scripts/trigger_eval.py"
    spec = importlib.util.spec_from_file_location("ci_skill_trigger_eval", location)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    skills = module.installed_skills(ROOT / ".claude/skills")
    assert 0 < len(skills["ci-impact-preflight"]) <= 200
    cases = module.load_cases(ROOT / ".claude/skills/ci-impact-preflight/trigger_scenarios.json")
    named = {
        name for case in cases for key in ("required", "any_of", "acceptable") for name in case[key]
    }
    assert named <= set(skills), named - set(skills)
    assert any(not (c["required"] or c["any_of"] or c["acceptable"]) for c in cases)
