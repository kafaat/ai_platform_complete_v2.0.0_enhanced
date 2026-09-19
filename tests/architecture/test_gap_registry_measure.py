from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def mod():
    path = ROOT / "scripts/ci/gap_registry_measure.py"
    spec = importlib.util.spec_from_file_location("gap_registry_measure", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_measure_does_not_guess_noncanonical_states():
    report = mod().measure(
        "| GAP-A-01 | x | **open — detail** |\n| GAP-B-01 | x | **BLOCKED_BY_ENVIRONMENT** |"
    )
    assert report["row_state_counts"] == {"open": 1, "unclassified": 1}
    assert report["unclassified_rows"][0]["id"] == "GAP-B-01"


def test_measure_reports_nonadjacent_duplicate_headings():
    report = mod().measure(
        "## GAP-A-01 — first\n\n"
        "- **الحالة:** fixed\n"
        "text\n"
        "## GAP-A-01 — second\n\n"
        "- **الحالة:** open\n"
    )
    assert report["duplicate_heading_ids"] == {"GAP-A-01": [1, 5]}


def test_measure_keeps_gap_rows_with_label_suffixes():
    report = mod().measure(
        "| HYBRID-FUSION-SCORE-NORMALIZATION-01 (B1a) | x | **open** |\n"
        "| DIRECT-VS-CANONICAL-DENSE-SEMANTICS-01 (B1b) | x | **fixed** |"
    )
    assert report["row_count"] == 2
    assert [row["id"] for row in report["unclassified_rows"]] == []
    assert report["row_state_counts"] == {"fixed": 1, "open": 1}


def test_measure_reports_contradictory_section_states_by_gap_id():
    report = mod().measure(
        "## GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01 — first\n\n"
        "- **الحالة:** fixed\n"
        "historical detail\n"
        "## GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01 — second\n\n"
        "- **الحالة:** open\n"
    )
    conflicts = report["contradictory_sections"]["GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01"]
    assert [item["state"] for item in conflicts] == ["fixed", "open"]
    assert [item["id"] for item in conflicts] == [
        "GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01",
        "GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01",
    ]


def report_job():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/capability-governance.yml").read_text(encoding="utf-8")
    )
    return workflow["jobs"]["gap-registry-report"]


def test_workflow_report_is_independent_nonblocking_and_bound_to_head():
    job = report_job()
    assert "needs" not in job
    assert job["continue-on-error"] is True
    checkout = next(step for step in job["steps"] if "actions/checkout@" in step.get("uses", ""))
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.head.sha || github.sha }}"
    upload = next(
        step for step in job["steps"] if "actions/upload-artifact@" in step.get("uses", "")
    )
    assert "${{ github.event.pull_request.head.sha || github.sha }}" in upload["with"]["name"]
    assert upload["with"]["path"] == "${{ env.EVIDENCE_DIR }}/"
    assert upload["with"]["if-no-files-found"] == "error"


@pytest.mark.parametrize("registry_exists", [True, False])
def test_workflow_command_emits_real_read_only_evidence(tmp_path, registry_exists):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    script = checkout / "scripts/ci/gap_registry_measure.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/ci/gap_registry_measure.py", script)
    registry = checkout / "sahool-brain/gaps/registry.md"
    if registry_exists:
        registry.parent.mkdir(parents=True)
        registry.write_text(
            "| GAP-A-01 | x | BLOCKED_BY_ENVIRONMENT |\n"
            "## GAP-A-01\n- **الحالة:** fixed\n"
            "## GAP-A-01\n- **الحالة:** open\n",
            encoding="utf-8",
        )

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=checkout, check=True, capture_output=True, encoding="utf-8"
        ).stdout.strip()

    git("init", "-q")
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
    evidence = tmp_path / "evidence"
    command = next(step["run"] for step in report_job()["steps"] if step.get("id") == "measure")
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", command],
        cwd=checkout,
        env={**os.environ, "EVIDENCE_DIR": str(evidence)},
        capture_output=True,
        encoding="utf-8",
    )
    assert git("status", "--porcelain") == ""
    if not registry_exists:
        assert result.returncode != 0
        assert "sahool-brain/gaps/registry.md" in result.stderr
        assert not (evidence / "gap-registry.json").exists()
        return

    assert result.returncode == 0, result.stderr
    report = json.loads((evidence / "gap-registry.json").read_text(encoding="utf-8"))
    assert report["row_state_counts"] == {"unclassified": 1}
    assert report["duplicate_heading_ids"] == {"GAP-A-01": [2, 4]}
    assert report["contradictory_section_id_count"] == 1
    assert (evidence / "source-sha.txt").read_text(encoding="utf-8").strip() == git(
        "rev-parse", "HEAD"
    )
    checksums = (evidence / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(checksums) == 2
    for path, line in zip((registry, script), checksums, strict=True):
        assert (
            line == f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(checkout)}"
        )
