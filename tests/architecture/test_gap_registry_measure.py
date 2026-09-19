from __future__ import annotations

import importlib.util
from pathlib import Path

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
        "| GAP-A-01 | x | **open — detail** |\n"
        "| GAP-B-01 | x | **BLOCKED_BY_ENVIRONMENT** |"
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
    conflicts = report["contradictory_sections"][
        "GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01"
    ]
    assert [item["state"] for item in conflicts] == ["fixed", "open"]
    assert [item["id"] for item in conflicts] == [
        "GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01",
        "GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01",
    ]
