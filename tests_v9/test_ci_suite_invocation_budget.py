"""No CI job may run the same test suite twice.

``UNIT-SUITE-RUN-TWICE-01``. Measured 2026-08-05: the *Unit Tests* job ran
``pytest -m unit --cov=services`` twice — once for the report and once for the coverage
floor — and that duplication was **half the critical path of every pull request**:

    19:09  measured in CI on #788
     6:35  the same suite locally with coverage
     6:35 x ~1.45 (runner) x 2 = 19:06

Nothing about it looks wrong in review. Both steps are individually correct, they sit
eleven lines apart with a comment block between them, and neither says "this is the second
time". The cost lives in their conjunction, which is exactly the shape a line-by-line
review cannot see — so it is pinned here as data instead.

The check is deliberately narrow: it counts *suite invocations* per job, where a suite
invocation is a pytest command with no explicit test paths (an unmarked-file step that
names its four paths is not a second run of the suite). A job that legitimately needs two
different selections will name them.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"

_MARKER = re.compile(r"(?:^|\s)-m\s+(\S+)")
# Options whose value is a separate token, so the value must not be read as a test path.
_TAKES_A_VALUE = {"-m", "-k", "-p", "-n", "-o", "--rootdir", "--junitxml", "--deselect"}
# `pytest …` or `python -m pytest …` at the start of a command, possibly after `run: >-`.
_INVOCATION = re.compile(r"^(?:[\w./-]*python[\d.]*\s+-m\s+)?pytest(?:\s|$)")


def _commands(job: dict) -> list[str]:
    """Each step's shell lines, with backslash continuations rejoined.

    Splitting on newlines alone is wrong and this check measured it: the four-file step
    is written as `pytest -v \\` with its paths on the following lines, so a per-line
    reader sees a bare `pytest -v` and calls it a whole-suite run.
    """
    out: list[str] = []
    for step in job.get("steps") or []:
        run = step.get("run")
        if not isinstance(run, str):
            continue
        joined: list[str] = []
        buffer = ""
        for raw in run.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.endswith("\\"):
                buffer += line[:-1].strip() + " "
                continue
            joined.append((buffer + line).strip())
            buffer = ""
        if buffer:
            joined.append(buffer.strip())
        out.extend(joined)
    return out


def _suite_invocations(commands: list[str]) -> list[str]:
    """pytest calls that select by marker alone — i.e. that run a whole suite.

    Must be the command being *run*, not any line mentioning the word: `pip install -r
    requirements.txt pytest-asyncio` contains "pytest" and installs a package. This check
    caught that on its own first run.
    """
    found = []
    for command in commands:
        stripped = command.lstrip()
        if stripped.startswith("#") or not _INVOCATION.match(stripped):
            continue
        tokens = _INVOCATION.sub("", stripped, count=1).split()
        skip_next = False
        has_path = False
        for token in tokens:
            if skip_next:
                skip_next = False
                continue
            if token.startswith("-"):
                skip_next = token in _TAKES_A_VALUE
                continue
            if token in {"||", "&&", "|", ";", ">", ">>"}:
                break  # shell plumbing, not a selection
            has_path = True
            break
        if not has_path:
            found.append(command)
    return found


def _jobs():
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, job in (document.get("jobs") or {}).items():
            if isinstance(job, dict):
                yield path.name, name, job


def test_no_job_runs_the_same_suite_twice():
    offenders: dict[tuple[str, str], list[str]] = defaultdict(list)
    for workflow, job_name, job in _jobs():
        invocations = _suite_invocations(_commands(job))
        by_marker: dict[str, list[str]] = defaultdict(list)
        for command in invocations:
            marker = _MARKER.search(command)
            by_marker[marker.group(1) if marker else "<no marker>"].append(command)
        for marker, commands in by_marker.items():
            if len(commands) > 1:
                offenders[(workflow, job_name)].append(
                    f"marker {marker}: {len(commands)} runs\n      " + "\n      ".join(commands)
                )
    assert not offenders, "\n".join(
        f"{workflow}:{job}\n    " + "\n    ".join(details)
        for (workflow, job), details in sorted(offenders.items())
    )


def test_the_check_would_catch_the_defect_it_was_written_for():
    """Without this, the assertion above also passes for a check that finds nothing."""
    duplicated = [
        "pytest -v -m unit --cov=services --cov-report=xml",
        "pytest -m unit --cov=services --cov-fail-under=43 -q",
    ]
    assert len(_suite_invocations(duplicated)) == 2


def test_a_step_that_names_its_paths_is_not_a_second_suite_run():
    """The Unit Tests job legitimately runs four unmarked files by explicit path."""
    explicit = [
        "pytest -v tests_v9/test_field_forms_api_integration.py",
        "pytest -m unit -p no:cacheprovider tests_v9/test_erp_bridge_fail_closed.py",
        "pytest ../model-registry-adapter/tests -q",
    ]
    assert _suite_invocations(explicit) == []


def test_a_line_continuation_is_one_command_not_a_bare_suite_run():
    """Measured on this check's first run: it read `pytest -v \\` as a whole-suite run."""
    job = {
        "steps": [
            {
                "run": "pytest -v \\\n  tests_v9/test_field_forms_api_integration.py \\\n"
                "  tests_v9/test_erp_bridge_fail_closed.py\n"
            }
        ]
    }
    assert _suite_invocations(_commands(job)) == []


def test_a_line_that_merely_mentions_pytest_is_not_an_invocation():
    """`pip install … pytest-asyncio` contains the word and runs no tests."""
    assert _suite_invocations(["pip install -r reqs.txt pytest-asyncio httpx"]) == []
    assert _suite_invocations(["python -m pytest -m unit"]) == ["python -m pytest -m unit"]


def test_the_unit_job_still_enforces_the_coverage_floor():
    """Merging the two runs must not drop the ratchet — that would be a silent weakening."""
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    runs = [
        line
        for line in text.splitlines()
        if "--cov-fail-under" in line and not line.strip().startswith("#")
    ]
    assert runs, "the coverage floor disappeared from ci.yml"
    assert any("43" in line for line in runs), f"the ratchet is no longer 43: {runs}"


def test_the_coverage_report_still_reaches_codecov():
    """coverage.xml is produced by the run; dropping the report would break the upload."""
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert "--cov-report=xml" in text
    assert "files: coverage.xml" in text


def test_no_step_translates_a_pytest_failure_into_a_coverage_diagnosis():
    """pytest exits 1 for a failed test AND for a missed coverage floor.

    The removed wrapper printed "التغطية انهارت دون الأرضيّة 43%" on either. Measured:
    100% coverage that cleared the floor plus one failing test still printed it. A wrong
    diagnosis costs more than none — it sends the reader to the wrong file.
    """
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "--cov-fail-under" in stripped:
            assert "||" not in stripped, (
                "a `||` fallback after a coverage run cannot tell a failed test from a "
                f"missed floor: {stripped}"
            )
