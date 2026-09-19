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
        "| ID | Detail | Status |\n| --- | --- | --- |\n"
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
        "| ID | Detail | Status |\n| --- | --- | --- |\n"
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


def test_status_column_and_quoted_history_do_not_manufacture_a_closure():
    report = mod().measure(
        "| ID | Status | Evidence |\n| --- | --- | --- |\n"
        "| H4 | **open** — HTTP_PENDING | `float | None` |\n"
        "| APPEND-ONLY-GUARD-FORBIDS-ROW-DEDUPLICATION-01 | "
        "implemented / pending final CI; original row: GAP-X \\| **fixed** | #987 |\n"
    )
    assert report["row_state_counts"] == {"open": 1, "unclassified": 1}
    assert report["table_structure_errors"] == []
    pending = report["unclassified_rows"][0]
    assert pending["id"] == "APPEND-ONLY-GUARD-FORBIDS-ROW-DEDUPLICATION-01"
    assert pending["raw_state"].startswith("implemented / pending final CI")


def test_cells_preserve_escaped_pipes_and_exact_matching_code_spans():
    assert mod().table_cells(r"| GAP-X | a\|b | ``a`|b`` and `x|y` | open |") == [
        "GAP-X",
        r"a\|b",
        "``a`|b`` and `x|y`",
        "open",
    ]
    assert mod().table_cells("| GAP-X | unmatched ` | fixed |") == ["GAP-X", "unmatched `", "fixed"]


def test_complete_ids_and_qualifiers_keep_their_original_case():
    report = mod().measure(
        "| ID | Status |\n| --- | --- |\n"
        "| CLASSIFIER-BLIND-TO-GENERATORS-OUTSIDE-generated-DIRS-01 | pending |\n"
        "| SAM2 | pending |\n| H5.1-BINDING-INTEGRITY | pending |\n"
        "## CLASSIFIER-BLIND-TO-GENERATORS-OUTSIDE-generated-DIRS-01\n"
        "- **status:** unknown\n"
    )
    assert [row["id"] for row in report["unclassified_rows"]] == [
        "CLASSIFIER-BLIND-TO-GENERATORS-OUTSIDE-generated-DIRS-01",
        "SAM2",
        "H5.1-BINDING-INTEGRITY",
    ]
    assert report["unclassified_section_states"][0]["id"].endswith("generated-DIRS-01")
    assert mod().classify("**OPEN** — PG_PENDING / #ABC") == ("open", "PG_PENDING / #ABC")


@pytest.mark.parametrize("fence", ["```", "~~~~"])
def test_fenced_examples_and_unrelated_sections_do_not_change_gap_states(fence):
    report = mod().measure(
        "## GAP-A-01\n- **status:** fixed\n"
        f"{fence}markdown\n"
        "## GAP-A-01\n- **status:** open\n"
        "| GAP-X | missing header |\n"
        f"{fence}\n"
        "## Notes\n- **status:** pending\n"
    )
    assert report["heading_count"] == 1
    assert report["row_count"] == 0
    assert report["section_state_count"] == 1
    assert report["contradictory_sections"] == {}
    assert report["unscoped_section_states"][0]["id"] is None


def test_broken_tables_remain_findings_instead_of_guessing_the_last_cell():
    report = mod().measure(
        "| GAP-X | evidence | fixed |\n\n"
        "| ID | Status |\n| --- | --- |\n"
        "| GAP-Y | pending | fixed |\n\n"
        "| ID | Status | Status |\n| --- | --- | --- |\n"
        "| GAP-Z | open | fixed |\n"
    )
    assert report["row_state_counts"] == {"unclassified": 3}
    assert [item["reason"] for item in report["table_structure_errors"]] == [
        "missing_table_header",
        "invalid_table_shape",
        "invalid_table_shape",
    ]


def test_alias_maps_are_visible_but_are_not_state_tables():
    report = mod().measure("| ID | Replacement |\n| --- | --- |\n| GAP-A-01 | GAP-B-01 |\n")
    assert report["row_count"] == 0
    assert report["non_state_table_rows"][0]["id"] == "GAP-A-01"


def test_explicit_non_state_records_keep_their_evidence_separate():
    report = mod().measure(
        "| ID | Status |\n| --- | --- |\n"
        "| GAP-A-01 | <!-- gap-registry: alias --> see GAP-B-01 |\n"
        "| SAM2 | <!-- gap-registry: policy --> by-design |\n"
        "| GAP-C-01 | <!-- gap-registry: adjudicated --> not a defect (#997) |\n"
        "| GAP-D-01 | by-design |\n"
        "## GAP-A-01\n- **status:** <!-- gap-registry: alias --> see GAP-B-01\n"
    )
    assert report["row_count"] == 4
    assert report["gap_row_count"] == 1
    assert report["row_state_counts"] == {"unclassified": 1}
    assert report["non_state_row_counts"] == {"adjudicated": 1, "alias": 1, "policy": 1}
    assert "#997" in report["non_state_rows"][2]["raw_state"]
    assert report["non_state_section_states"][0]["kind"] == "alias"


def test_reviewed_history_remains_visible_without_becoming_a_current_conflict():
    report = mod().measure(
        "## GAP-A-01 — resolved\n<!-- gap-registry: current -->\n- **status:** fixed\n"
        "## GAP-A-01 — original finding\n<!-- gap-registry: historical -->\n- **status:** open\n"
    )
    assert report["duplicate_heading_ids"] == {"GAP-A-01": [1, 4]}
    assert report["unreviewed_duplicate_heading_ids"] == {}
    assert report["contradictory_sections"] == {}
    assert [s["state"] for s in report["historical_state_variations"]["GAP-A-01"]] == [
        "fixed",
        "open",
    ]


@pytest.mark.parametrize(
    "first,second", [("current", "current"), ("historical", "historical"), ("current", None)]
)
def test_incomplete_or_ambiguous_history_review_cannot_hide_a_conflict(first, second):
    annotation = f"<!-- gap-registry: {second} -->\n" if second else ""
    report = mod().measure(
        f"## GAP-A-01\n<!-- gap-registry: {first} -->\n- **status:** fixed\n"
        f"## GAP-A-01\n{annotation}- **status:** open\n"
    )
    assert report["reviewed_heading_sequences"] == {}
    assert "GAP-A-01" in report["unreviewed_duplicate_heading_ids"]
    assert report["contradictory_section_id_count"] == 1


def test_misplaced_or_unknown_annotations_are_reported():
    report = mod().measure(
        "## GAP-A-01\n- **status:** fixed\n<!-- gap-registry: current -->\n"
        "| ID | Status |\n| --- | --- |\n"
        "| GAP-X | <!-- gap-registry: exempt --> pending |\n"
        "| GAP-Y | <!-- gap-registry: alias --><!-- gap-registry: policy --> pending |\n"
    )
    assert [item["line"] for item in report["annotation_errors"]] == [3, 6, 7]
    assert report["gap_row_count"] == 2
    assert report["row_state_counts"] == {"unclassified": 2}


def report_job():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/capability-governance.yml").read_text(encoding="utf-8")
    )
    return workflow["jobs"]["gap-registry-report"]


def test_workflow_report_is_independent_nonblocking_and_bound_to_head():
    job = report_job()
    assert "needs" not in job
    assert job["continue-on-error"] is True
    measure = next(step for step in job["steps"] if step.get("id") == "measure")
    assert measure["env"]["EVIDENCE_DIR"] == "${{ runner.temp }}/gap-registry-measurement"
    checkout = next(step for step in job["steps"] if "actions/checkout@" in step.get("uses", ""))
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.head.sha || github.sha }}"
    upload = next(
        step for step in job["steps"] if "actions/upload-artifact@" in step.get("uses", "")
    )
    assert "${{ github.event.pull_request.head.sha || github.sha }}" in upload["with"]["name"]
    assert upload["with"]["path"] == measure["env"]["EVIDENCE_DIR"] + "/"
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
            "| ID | Detail | Status |\n| --- | --- | --- |\n"
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
    assert report["duplicate_heading_ids"] == {"GAP-A-01": [4, 6]}
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
