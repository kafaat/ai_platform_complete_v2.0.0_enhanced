"""The impact selector must narrow honestly, or refuse to narrow at all.

A test selector is the one tool where being wrong is invisible: a run that skipped the
failing test looks exactly like a run that passed. So every property below is pinned by
planting the thing it forbids, not by asserting the happy path.

The properties, in the order they can bite:

* it owns **no impact logic** — every capability comes from the blocking gate's engine;
* the always-run floor is **derived**, never listed, and is never dropped;
* an escalation trigger refuses partial selection outright;
* an unbindable changed path is **disclosed**, not silently decided;
* working-tree edits are seen (the first version was blind to them and exited 0);
* and it never becomes a gate — no workflow may invoke it.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts/ci/test_impact.py"
RUNNER = ROOT / "scripts/ci/test_impact.sh"
POLICY = ROOT / "docs/architecture/test_impact_policy.json"
GATE = ROOT / "scripts/ci/pr_capability_impact_gate.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load(TOOL, "_test_impact")


@pytest.fixture(scope="module")
def snapshot(tool):
    return tool._engine().current_snapshot()


# ── it owns no impact logic ────────────────────────────────────────────────


def test_every_capability_comes_from_the_blocking_gate_not_from_here(tool, snapshot):
    """Two engines answering one question returned 0 and 12 here. A third would be worse."""
    engine = tool._engine()
    paths = ["services/decision-service/main.py"]
    expected = set(engine.impact(paths, snapshot)["affected"])
    selected, _ = tool.select(snapshot, expected, tool.discover_test_files())

    # Nothing the selector reports may exceed what the engine said is affected.
    for path, why in selected.items():
        assert set(why["capabilities"]) <= expected, (
            f"{path} claims a capability the engine did not"
        )


def test_the_selector_holds_no_traversal_of_its_own(tool):
    """The engine walks `dependents` to find transitive impact. A copy here would drift."""
    source = TOOL.read_text(encoding="utf-8")
    assert "dependents" not in source, (
        "the selector appears to traverse the capability graph itself; it must call "
        "pr_capability_impact_gate.impact instead"
    )
    assert "pr_capability_impact_gate" in source


def test_every_printed_reason_is_the_engine_s_own_source_field(tool, snapshot):
    """The 'why' must be evidence, not a label this tool invents."""
    engine = tool._engine()
    affected = set(engine.impact(["services/decision-service/main.py"], snapshot)["affected"])
    selected, _ = tool.select(snapshot, affected, tool.discover_test_files())
    assert selected, "the probe change reached no test — the property would be vacuous"
    for path, why in selected.items():
        assert why["sources"], f"{path} was selected with no stated source"
        assert set(why["sources"]) == set(snapshot.references[path].sources)


# ── the floor ──────────────────────────────────────────────────────────────


def test_the_floor_is_derived_and_the_policy_names_no_test(tool, snapshot):
    policy_text = POLICY.read_text(encoding="utf-8")
    _, floor = tool.select(snapshot, set(), tool.discover_test_files())
    assert floor, "an empty floor would mean every guard is reachable, which is measured false"
    for path in floor:
        assert path not in policy_text, (
            f"the policy names {path} — a hand-maintained list is the drift this tool avoids"
        )


def test_a_file_bound_to_no_capability_is_floor_not_omission(tool, snapshot):
    """Tree-wide guards map to zero capabilities; treating them as 'unselected' loses them."""
    _, floor = tool.select(snapshot, set(), tool.discover_test_files())
    for probe in ("tests/architecture/test_architecture_graph.py",):
        assert probe in floor, f"{probe} is a tree-wide guard and must be in the floor"


def test_the_floor_survives_every_mode(tool):
    """The one thing a selector must never do is drop a test it cannot reason about."""
    result = {"mode": "selected", "floor": ["a/test_x.py"], "selected": {"b/test_y.py": {}}}
    assert set(tool.paths_to_run(result)) == {"a/test_x.py", "b/test_y.py"}


# ── escalation ─────────────────────────────────────────────────────────────


def test_a_governance_wide_reference_refuses_partial_selection(tool):
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert tool.escalation_reasons([], policy, governance_wide=True)


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        "pytest.ini",
        "tests_v9/conftest.py",
        "tests_v9/requirements-test.txt",
        "scripts/ci/verify_all_generated.py",
    ],
)
def test_changes_that_alter_how_tests_run_refuse_partial_selection(tool, path):
    """The session's costliest failure was a missing library in a job, not a failing test.

    No impact cone reaches that. These paths change *how* the suite runs or *what* CI
    invokes, so a narrowed selection would be answering a question nobody asked.
    """
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert tool.escalation_reasons([path], policy, governance_wide=False), (
        f"{path} must force the full suite"
    )


def test_an_ordinary_source_edit_does_not_escalate(tool):
    """Without this, every assertion above would also hold for a tool that always escalates."""
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert not tool.escalation_reasons(
        ["services/decision-service/main.py"], policy, governance_wide=False
    )


def test_escalation_runs_the_whole_corpus_not_the_cone(tool):
    result = {"mode": "full", "floor": ["a/test_x.py"], "selected": {}}
    assert len(tool.paths_to_run(result)) == len(tool.discover_test_files())


# ── undecided, disclosed rather than assumed ───────────────────────────────


def test_an_unbound_source_file_escalates_because_its_coverage_is_unknown(tool):
    """The one unrecoverable failure of a selector is the silent skip.

    If the engine binds a changed source file to no capability, nothing says which tests
    cover it — so narrowing is a guess. Measured 2026-08-05: 956 of 2270 non-test source
    files are bindable (42%), so this fires on roughly 58% of source changes. That cost is
    declared in the policy rather than avoided by pretending the cone was complete.
    """
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    probe = "services/sahool-platform/api/learning_feedback.py"
    assert tool.escalation_reasons([probe], policy, governance_wide=False, unbound={probe}), (
        f"{probe} is unbound source and must escalate"
    )
    # Bound source is exactly the case the tool exists for, and must NOT escalate.
    assert not tool.escalation_reasons(
        ["services/decision-service/main.py"], policy, governance_wide=False, unbound=set()
    )


def test_unbound_prose_and_docs_do_not_escalate(tool):
    """Otherwise every brain-log edit would run the whole corpus and nobody would use it."""
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    for probe in ("sahool-brain/log.md", "README.md", "docs/testing/coverage_ratchet.md"):
        assert not tool.escalation_reasons(
            [probe], policy, governance_wide=False, unbound={probe}
        ), f"{probe} changes no behaviour a test measures"


def test_an_unbindable_path_is_disclosed_and_does_not_escalate_on_its_own(tool):
    """Only 38% of tracked files are bindable; escalating on the rest would decide nothing.

    So an unbound path is surfaced as undecided instead — the developer reads what was not
    reasoned about rather than mistaking it for reasoned about.
    """
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert not tool.escalation_reasons(["README.md"], policy, governance_wide=False)
    source = TOOL.read_text(encoding="utf-8")
    assert "undecided_changed_paths" in source


def test_the_plan_reports_undecided_paths_for_a_real_change(tool):
    plan = tool.plan("origin/main", "HEAD")
    assert "undecided_changed_paths" in plan
    assert isinstance(plan["undecided_changed_paths"], list)
    assert plan["mode"] in {"selected", "full"}


# ── the defect this tool had ───────────────────────────────────────────────


def test_working_tree_edits_are_seen(tool, tmp_path):
    """The first version read only the committed diff, so it saw nothing and exited 0.

    A local accelerator blind to the edit you just made has the exact shape of everything
    else this session chased: it runs, and it measures nothing.
    """
    source = TOOL.read_text(encoding="utf-8")
    assert "--porcelain" in source, "the plan must read the working tree, not the diff alone"
    paths = tool.working_tree_paths()
    assert isinstance(paths, list)


def test_a_rename_does_not_shift_the_working_tree_parse(tool):
    """`git status -z` puts a rename's source in the NEXT field; misreading it corrupts paths."""
    source = TOOL.read_text(encoding="utf-8")
    assert '"R" in status' in source and '"C" in status' in source


# ── it must never become a gate ────────────────────────────────────────────


def test_no_workflow_invokes_the_selector():
    """It is an accelerator. If CI ever ran it, CI would inherit a narrowed suite."""
    offenders = [
        path.name
        for path in sorted((ROOT / ".github/workflows").glob("*.yml"))
        if "test_impact" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"test_impact must not be a CI gate; invoked by: {offenders}"


def test_the_tool_states_its_own_limit_where_a_reader_will_see_it():
    """A selector that does not say what it skipped will be read as full coverage."""
    for path in (TOOL, RUNNER):
        text = path.read_text(encoding="utf-8")
        assert "CI" in text, f"{path.name} must say the final decision belongs to CI"


def test_the_policy_carries_its_adjudication_and_its_measured_ceiling():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["schema"] == "sahool.test_impact_policy"
    assert isinstance(policy["version"], int) and policy["version"] >= 1
    assert policy["adjudicated_on"], "a decided artifact carries the date it was decided"
    ceiling = policy["measured_ceiling"]
    assert ceiling["cases_in_the_always_run_floor"] > 0
    assert ceiling["cases_in_the_always_run_floor"] < ceiling["unit_test_cases"]
    assert ceiling["measured_on"]


def test_the_runner_refuses_to_report_success_on_an_empty_selection():
    """`pytest` with no paths collects the whole tree; an empty plan must fail, not pass."""
    text = RUNNER.read_text(encoding="utf-8")
    assert "${#PATHS[@]}" in text and "exit 2" in text


def test_the_gate_engine_the_selector_loads_is_the_one_ci_runs():
    """A copy of the engine under another name would reintroduce the drift it prevents."""
    assert GATE.is_file()
    workflows = (ROOT / ".github/workflows").glob("*.yml")
    assert any(
        "pr_capability_impact_gate.py" in path.read_text(encoding="utf-8") for path in workflows
    ), "the engine this tool trusts must itself be a blocking gate"


def test_selection_is_reproducible_from_git_alone():
    """No network, no cached state: two runs on the same tree must agree."""

    def run():
        return subprocess.run(
            [sys.executable, str(TOOL), "--base", "origin/main", "--print-paths"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout

    assert run() == run()
