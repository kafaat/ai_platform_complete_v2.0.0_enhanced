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


def _resolvable_base(tool) -> str:
    """A base ref that exists **here**.

    Measured on #791: both tests below hardcoded ``origin/main`` and died in CI with a
    raw `git merge-base` traceback, because `actions/checkout` at depth 1 has no such
    ref. The selector was right to refuse; the tests were asserting the runner's git
    topology instead of the selector's behaviour. So the base is derived, and the test
    fails loudly if nothing resolves rather than skipping.
    """
    for candidate in ("origin/main", "HEAD~1", "HEAD"):
        if tool.ref_exists(candidate):
            return candidate
    raise AssertionError("no git ref resolves — the repository has no history to diff")


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


def test_the_audit_sample_rides_with_every_narrowed_run(tool):
    """Excluded tests never run, so a wrong exclusion is invisible unless some are sampled.

    This is the v1 plan shape from #1357 (top-level ``audit_sample``); it must stay readable.
    """
    result = {
        "mode": "selected",
        "floor": ["a/test_x.py"],
        "selected": {"b/test_y.py": {}},
        "audit_sample": ["c/test_z.py"],
    }
    assert set(tool.paths_to_run(result)) == {"a/test_x.py", "b/test_y.py", "c/test_z.py"}


def test_the_audit_sample_is_seeded_bounded_and_drawn_only_from_the_excluded(tool):
    # #1357's guarantees under the percent-with-minimum size (5% of 40 = 2, minimum 5 → 5).
    kw = {"percent": 5, "minimum": 5}
    excluded = [f"t/test_{i}.py" for i in range(40)]
    first = tool.audit_sample(excluded, "abc:def", **kw)
    assert first == tool.audit_sample(list(reversed(excluded)), "abc:def", **kw), (
        "order must not matter"
    )
    assert len(first) == 5 and set(first) <= set(excluded) and first == sorted(first)
    rotated = {tuple(tool.audit_sample(excluded, f"commit{i}:def", **kw)) for i in range(8)}
    assert len(rotated) > 1, "successive commits must rotate through the excluded corpus"
    assert tool.audit_sample(excluded[:3], "abc:def", **kw) == sorted(excluded[:3])
    assert tool.audit_sample([], "abc:def", **kw) == []
    # Changed from #1357: ``per_run: 0`` used to mean "sample nothing". One mechanism now,
    # and a minimum below one is refused rather than read as switching the audit off.
    with pytest.raises(ValueError):
        tool.audit_sample(excluded, "abc:def", percent=5, minimum=0)


def test_a_real_plan_samples_only_excluded_tests_and_none_when_escalated(tool):
    base = _resolvable_base(tool)
    result = tool.plan(base, "HEAD", include_working_tree=False)
    sample = set(result["audit"]["test_paths"])
    if result["mode"] == "full":
        assert not sample, "full mode excludes nothing, so there is nothing to sample"
    else:
        assert not sample & set(result["floor"]) and not sample & set(result["selected"])
        policy = json.loads(POLICY.read_text(encoding="utf-8"))["audit_sample"]
        assert len(sample) == tool.sample_size(
            result["audit"]["population"], policy["percent"], policy["minimum"]
        )


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
    plan = tool.plan(_resolvable_base(tool), "HEAD")
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


def test_selection_is_reproducible_from_git_alone(tool):
    """No network, no cached state: two runs on the same tree must agree."""
    base = _resolvable_base(tool)

    def run():
        return subprocess.run(
            [sys.executable, str(TOOL), "--base", base, "--print-paths"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout

    assert run() == run()


def test_an_unresolvable_base_is_diagnosed_not_a_traceback(tool):
    """Measured on #791: CI checks out at depth 1, so `origin/main` does not exist there.

    The first version died with a raw `git merge-base ... exit 128` CalledProcessError.
    Refusing was correct — a base that does not resolve cannot produce a delta — but a
    traceback is not a diagnosis. It must name the ref and say what to do, the same
    standard applied to the schema guard's missing-library message in #788.
    """
    assert not tool.ref_exists("definitely/not/a/ref")
    result = subprocess.run(
        [sys.executable, str(TOOL), "--base", "definitely/not/a/ref"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "definitely/not/a/ref" in result.stderr, (
        "the message must name the ref it could not resolve"
    )
    assert "Traceback" not in result.stderr, result.stderr


# ── the audit sample measures what the selection drops ──────────────────────
# Method and formula from Unified Local Lab ``portable_ci_lab.change_selection``.

TESTS = [f"tests_v9/test_{i:03d}.py" for i in range(100)]
SELECTED = {TESTS[0]: {}, TESTS[1]: {}}
FLOOR = TESTS[2:12]
KW = {"mode": "selected", "percent": 5, "minimum": 5, "seed_material": "s"}


def test_the_audit_is_drawn_only_from_excluded_tests_and_never_empty(tool):
    audit, counts, decisions = tool.decide(TESTS, SELECTED, FLOOR, **KW)
    excluded = set(TESTS) - set(SELECTED) - set(FLOOR)
    assert audit and set(audit) <= excluded
    assert len(audit) == 5  # max(5, ceil(88 * 5 / 100))
    assert counts == {
        "selected": 2,
        "floor": 10,
        "audit": 5,
        "excluded_not_run": 83,
        "full_suite": 0,
        "total": 100,
    }
    assert sum(counts[k] for k in ("selected", "floor", "audit", "excluded_not_run")) == 100
    assert set(decisions) == set(TESTS), "every tracked test gets exactly one decision"
    tally = {}
    for record in decisions.values():
        tally[record["decision"]] = tally.get(record["decision"], 0) + 1
    assert tally == {k: v for k, v in counts.items() if k != "total" and v}
    one, _, _ = tool.decide(TESTS, SELECTED, TESTS[2:99], **KW)
    assert one == [TESTS[99]], "a single excluded test is still audited"


def test_the_same_change_draws_the_same_sample_and_another_change_may_not(tool):
    kw = {"percent": 10, "minimum": 5}
    first = tool.audit_sample(TESTS, "seed-a", **kw)
    assert first == tool.audit_sample(list(reversed(TESTS)), "seed-a", **kw)
    assert any(tool.audit_sample(TESTS, f"seed-{n}", **kw) != first for n in range(5))


def test_a_full_suite_run_has_nothing_to_audit(tool):
    audit, counts, decisions = tool.decide(TESTS, SELECTED, FLOOR, **{**KW, "mode": "full"})
    assert audit == [] and counts["full_suite"] == 100 and counts["excluded_not_run"] == 0
    assert {record["decision"] for record in decisions.values()} == {"full_suite"}


def test_an_invalid_audit_percent_is_refused(tool):
    for bad in (0, -1, 101, float("nan"), "5", True):
        with pytest.raises(ValueError):
            tool.audit_sample(TESTS, "s", percent=bad, minimum=5)
    for bad in (0, -1, 2.5, "5", True):
        with pytest.raises(ValueError):
            tool.audit_sample(TESTS, "s", percent=5, minimum=bad)


def test_the_runner_runs_the_audit_sample_and_never_drops_the_floor(tool):
    result = {
        "mode": "selected",
        "selected": SELECTED,
        "floor": FLOOR,
        "audit": {"test_paths": [TESTS[50]]},
    }
    assert tool.paths_to_run(result) == sorted(set(SELECTED) | set(FLOOR) | {TESTS[50]})


def test_the_policy_declares_one_valid_sampling_mechanism():
    """One policy block: percent with a minimum. The old fixed ``per_run`` must not linger."""
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["audit_sample"]
    percent, minimum = policy["percent"], policy["minimum"]
    assert isinstance(percent, (int, float)) and 0 < percent <= 100
    assert isinstance(minimum, int) and minimum >= 5, (
        "the minimum is the fixed count #1357 ran; no narrowed run may audit fewer"
    )
    assert "per_run" not in policy, "two sampling mechanisms would disagree on the count"


@pytest.mark.parametrize(
    "n, expected",
    [
        (0, 0),
        (1, 1),
        (3, 3),
        (5, 5),
        (10, 5),
        (50, 5),
        (100, 5),
        (101, 6),
        (200, 10),
        (878, 44),
        (2000, 100),
    ],
)
def test_the_sample_size_is_a_percent_with_a_minimum_never_more_than_excluded(tool, n, expected):
    """min(n, max(minimum, ceil(n * percent / 100))) at 5% / minimum 5."""
    assert tool.sample_size(n, 5, 5) == expected


def test_a_dependency_selected_test_carries_decision_selected_with_its_reason(tool):
    """#1361: a test selected only by a proven edge is ``selected``, its edge is the reason."""
    edge = "dependency:source_read:services/guard/main.py"
    selected = {
        TESTS[0]: {"capabilities": [], "sources": ["x"], "dependencies": [edge]},
        TESTS[1]: {"capabilities": ["SEC-006"], "sources": ["y"]},
    }
    audit, counts, decisions = tool.decide(TESTS, selected, FLOOR, **KW)
    assert decisions[TESTS[0]] == {"decision": "selected", "reasons": [edge]}
    assert decisions[TESTS[1]] == {"decision": "selected", "reasons": ["capability:SEC-006"]}
    assert TESTS[0] not in audit and counts["selected"] == 2


def test_a_v1_plan_without_any_audit_is_still_runnable(tool):
    result = {"mode": "selected", "floor": FLOOR, "selected": SELECTED}
    assert tool.paths_to_run(result) == sorted(set(SELECTED) | set(FLOOR))


def test_a_real_plan_records_commits_decisions_and_its_own_digest(tool):
    plan = tool.plan(_resolvable_base(tool), "HEAD")
    assert len(plan["head_commit"]) == 40
    counts = plan["decision_counts"]
    assert counts["total"] == len(tool.discover_test_files())
    assert set(plan["decisions"]) == set(tool.discover_test_files())
    # Which branch runs depends on the local diff against the resolved base, so both
    # must hold. Measured on the wave-7 carrier: a diff touching .github/workflows/
    # escalated to full while ``selected`` still listed the 1072-file cone, and the
    # selected-mode check below, then unconditional, failed on the first of them.
    if plan["mode"] == "full":
        assert counts["full_suite"] == counts["total"] and not plan["audit"]["test_paths"]
        assert {d["decision"] for d in plan["decisions"].values()} == {"full_suite"}
    else:
        assert (
            sum(counts[k] for k in ("selected", "floor", "audit", "excluded_not_run"))
            == counts["total"]
        )
        assert set(plan["audit"]["test_paths"]).isdisjoint(
            set(plan["selected"]) | set(plan["floor"])
        )
        for path in plan["selected"]:
            assert plan["decisions"][path]["decision"] == "selected"
    unsigned = {k: v for k, v in plan.items() if k != "plan_sha256"}
    assert plan["plan_sha256"] == tool._digest(unsigned)
    # The digest identifies the plan; the record must say it is not evidence of a run.
    assert "not what ran" in plan["authority"]
    assert "لا تُثبت أنّ اختباراً عمل" in tool.render(plan)
