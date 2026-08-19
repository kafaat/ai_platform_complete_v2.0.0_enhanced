"""The local preflight must delegate authority, not copy it.

A preflight script is read as though it were the gate. That makes three failure modes
worse in a script than anywhere else, and two uploaded drafts carried all three:

* **A number typed in.** ``47 steps`` written into the script goes stale the day a
  generator is added, and it reads as measurement.
* **A hand-maintained sensitivity table.** ``SENSITIVE="docs/architecture/db_ownership.yml"``
  answers "which capabilities does this touch?" from a list somebody curated once. The
  blocking gate answers it from a map derived from the tree.
* **Volatile platform advice.** Merge mechanics (stacked PRs, merge-async, merge queues)
  change under us. They belong in the runbook, which carries a field-verification date
  and a maintenance contract — not in a tool, where nothing marks them as perishable.

And one honesty property: a local PASS is not runtime or production certification. A
script that implies otherwise manufactures exactly the claim this repository's CI
invariants exist to prevent.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/preflight.sh"
CONTRACT = ROOT / "docs/architecture/preflight_required.json"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_script_parses_as_bash():
    """A preflight that cannot start is worse than none: it is skipped, then trusted."""
    # `text=True` alone decodes with the machine's locale — the second vector in §3.10
    # of the runbook, and this repository's own encoding guard fails the file for it.
    # The script is Arabic-commented, so under LC_ALL=C that decode raises.
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_authority_is_delegated_to_the_repository_sweep_and_gate():
    text = _text()
    assert "scripts/ci/verify_all_generated.py" in text, (
        "the sweep discovers its own step list from the workflows; never enumerate here"
    )
    assert "scripts/ci/pr_capability_impact_gate.py" in text
    assert "--pr-body-file" in text, (
        "reproducing the blocking decision needs the real gate on the real body"
    )


def test_no_hand_maintained_sensitivity_table():
    """The engine answers this question; a curated list only goes stale."""
    text = _text()
    assert "SENSITIVE=" not in text
    assert "db_ownership.yml" not in text, (
        "naming a sensitive file here reinstates the table this replaced"
    )


def test_no_perishable_platform_advice_inside_the_tool():
    """Merge mechanics belong to the runbook, which dates and reviews its claims."""
    text = _text()
    for token in ("merge-async", "enqueuePullRequest", "stacked"):
        assert token not in text, f"perishable platform detail in a tool: {token!r}"


def test_the_tool_reads_no_github_state():
    """It is a local developer preflight, not a CI gate and not a decision source.

    Anything that depends on live GitHub state — open PRs, green status, merge order —
    is volatile by nature and must not become part of the governance definition. Those
    judgements live in the runbook (§3.21), which carries a review date. What runs here
    must be locally reproducible facts only.
    """
    text = _text()
    for token in ("api.github.com", "gh pr", "gh api", "list_pull_requests", "GITHUB_TOKEN"):
        assert token not in text, f"GitHub state read inside a local tool: {token!r}"
    # `git fetch` is allowed: it yields a git fact (a ref), not a platform judgement —
    # and `--no-fetch` keeps even that optional for fully offline runs.
    assert "--no-fetch" in text


def test_it_refuses_an_archive_instead_of_reporting_false_green():
    """Measured: a full package was built on an archive with no .git and looked green.

    Without git metadata the generators fall back to the signed manifest, so drift
    cannot be seen — the sweep reports success about a question it could not ask.
    """
    text = _text()
    assert "git rev-parse --show-toplevel" in text
    assert "[ -d .git ] || [ -f .git ]" in text
    assert text.count("أخضر كاذباً") >= 2, "the refusal must say why, in both branches"


def test_a_missing_gate_script_is_a_coverage_loss_not_a_test_failure():
    text = _text()
    assert "require_file" in text
    assert "سكربت بوّابة مفقود" in text


def test_skips_are_counted_and_the_summary_refuses_to_overclaim():
    """`Green` here means "what was measured passed", never "CI will be green"."""
    text = _text()
    assert "skipped=$((skipped + 1))" in text, "a skipped gate must be counted, not swallowed"
    assert "لم تُقَس" in text
    assert "٢٠٩" in text and "٧١" in text, (
        "the summary must state the measured coverage ratio, not imply completeness"
    )
    assert "ادفع بثقة" not in text


def test_it_reports_index_state_not_only_untracked_files():
    """An unstaged edit to a tracked file hides drift exactly as an untracked file does."""
    text = _text()
    assert "git ls-files --others --exclude-standard" in text
    assert "git diff --name-only" in text
    assert "git diff --cached --name-only" in text


def test_a_leaked_test_probe_fails_the_fast_tier_instead_of_warning():
    """Measured twice: an untracked probe left the tree, and the tool called it green.

    ``test_api_versioning_policy_guard`` injects an unadjudicated route, *deliberately
    regenerates the inventories* to prove regeneration does not launder it, then restores
    in ``finally`` — and ``finally`` does not survive an interrupt. What is left behind is
    ``_probe_unadjudicated_route.py`` plus drifted generated inventories.

    The first time, that leak was read as a real unauthorized route and cost an external
    certification round nineteen misattributed failures. ``probe_leak_guard.py`` was
    written to name it in one line, and it blocks in CI (``ci.yml:536``).

    It happened again anyway, because the local preflight never called it: step ٠ب prints
    a generic ``⚠ untracked file`` — a warning, not a failure — so ``--fast`` reported
    ``إخفاقات=0`` on a tree CI would block, and the defect resurfaced later as eleven
    ``pytest -m unit`` failures on route-derived inventories. Eleven symptoms instead of
    one named cause. The guard existed; the question was never asked locally.

    So the assertion is placement, not presence: it must run inside the fast tier, before
    the early exit, where the untracked-file warning it explains is printed.

    And placement is anchored on the **invocation**, never on the bare path. The bare path
    also appears in ``require_file`` and would appear in any comment that names the guard —
    so ``text.index(path)`` could later resolve to prose above the step while the executed
    line sits below the early exit, and the assertion would pass on a tier that never runs
    it. That is the same class this whole file exists to reject: an assertion that stops
    measuring what it claims. Uniqueness is asserted too, so a second invocation cannot
    make ``index`` ambiguous again.
    """
    text = _text()
    invocation = "python3 scripts/ci/probe_leak_guard.py"
    assert invocation in text, (
        "a guard that blocks in CI but is never invoked locally lets the tree be pushed "
        "on the green of a tool that did not ask"
    )
    assert text.count(invocation) == 1, (
        "two invocations make the placement check read whichever comes first — pick one"
    )
    fast_exit_at = text.index('if [ "$TIER" = fast ]')
    assert text.index(invocation) < fast_exit_at, (
        "the leak must be named in --fast: the tier developers actually run before pushing"
    )
    assert text.index("require_file scripts/ci/probe_leak_guard.py") < fast_exit_at, (
        "a missing guard must be named a coverage loss inside the tier that runs it"
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert "scripts/ci/probe_leak_guard.py" in contract["required_scripts"], (
        "deleting the guard must be named a coverage loss, not read as a passing gate"
    )


def test_the_mutation_guard_plants_locally_and_not_only_validates_its_spec():
    """Measured: the half that blocks in CI was the half never run locally.

    ``guard_mutation_guard.py`` has two halves. Bare, it validates the *specification*
    — every registered mutation names a real anchor and a real test. With ``--run`` it
    **plants** each defect and asserts the named test turns red. Only the second half
    measures anything; the first reads a document.

    ``preflight.sh`` called the bare form and ``preflight_required.json`` listed the
    script, so the contract was satisfied by name while nothing was ever planted. CI runs
    ``--run`` (``ci.yml:743``), so the two disagreed — and the disagreement shipped: a
    second check added to ``knowledge_relation_registry_guard.py`` fails in a temporary
    root, so ``test_zero_relations_checked_fails_closed`` began passing on a ``SystemExit``
    raised by *that* check instead of the gate it claims to guard. Mutation ``[6]``
    survived, ``--fast`` said ``إخفاقات=0``, and *Unit Tests* failed on run 96216401333.

    Planting all 265 mutations costs ~38 minutes and fits no tier, so the step is scoped
    to guards the change actually touched — 11 seconds for one guard, nothing when none
    were touched. That scoping is the reason it can live in ``--fast``, and ``--fast`` is
    the tier this must live in: it is the one developers run before pushing.

    The assertion is therefore placement *and* derivation. A hard-coded guard name would
    measure one guard forever and read as coverage for all of them, so the invocation must
    pass a variable — the same "green about a question never asked" this file rejects.
    """
    text = _text()
    invocation = "python3 scripts/ci/guard_mutation_guard.py --run --only"
    assert invocation in text, (
        "the planting half blocks in CI; a preflight that only validates the spec reports "
        "green on a tree CI rejects"
    )
    assert text.count(invocation) == 1, (
        "two invocations make the placement check read whichever comes first — pick one"
    )
    fast_exit_at = text.index('if [ "$TIER" = fast ]')
    assert text.index(invocation) < fast_exit_at, (
        "planting must run in --fast: the tier that was green when the defect was pushed"
    )
    planted = text[text.index(invocation) : text.index(invocation) + 120]
    assert '"$_g"' in planted, (
        "a hard-coded guard name measures one guard and is read as covering all of them — "
        "the target must be derived from what the change touched"
    )
    assert "python3 scripts/ci/guard_mutation_guard.py\n" in text, (
        "the spec-validating half is cheap and still wanted — this replaces neither half"
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert "scripts/ci/guard_mutation_guard.py" in contract["required_scripts"], (
        "deleting the guard must be named a coverage loss, not read as a passing gate"
    )


def test_the_commit_claim_step_says_it_reads_committed_messages_only():
    """Measured: its green ran before the commit it was read as clearing.

    ``brain_commit_claim_guard`` reads commit *messages* in ``base..HEAD``. Running the
    preflight before committing therefore measures a range that does not contain the
    message about to be written — so ``٦ج ✓`` means "what is committed is clean", never
    "your message will pass". A commit whose subject carried ``CI-HOST-PSQL:`` — a
    truncated prefix of a registered identifier — passed that green and then failed the
    blocking ``guard`` job in CI.

    Same class as the Capability-Impact reminder already in this tool: derive it after
    committing or do not derive it. So the step must say so where its result is printed.
    """
    text = _text()
    claim_at = text.index("brain_commit_claim_guard.py")
    tail = text[claim_at:]
    assert "المُلتزَمة" in tail[:1200], (
        "٦ج must state that it reads committed messages — a green measured on a range "
        "without the message reads as clearing the message"
    )


def test_exit_codes_use_the_form_the_runbook_proved():
    """`[ $rc -ne 0 ] && echo …` as a function's last statement returns 1 on success.

    That is a measured defect in this repository's own verification scripts, and §2 of
    the runbook documents the correct shape. The preflight must not reintroduce it.
    """
    text = _text()
    assert "|| rc=$?" in text
    assert re.search(r"if \[ \"\$rc\" -ne 0 \]", text), "read the captured status, not $?"
    body = text.split("run() {", 1)[1].split("\n}", 1)[0]
    assert body.rstrip().endswith("return 0"), (
        "run() must end with an explicit `return 0` so a failing gate does not become "
        "the function's return value"
    )


def test_the_runbook_points_at_this_script():
    """A committed script nobody is told about is the decorative-gate class again."""
    runbook = (ROOT / "docs/runbooks/CI_GATES_AND_PRE_PUSH_PROTOCOL.md").read_text(encoding="utf-8")
    claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "scripts/ci/preflight.sh" in runbook
    assert "scripts/ci/preflight.sh" in claude_md, (
        "CLAUDE.md is what a new session reads; an unindexed runbook section is unread"
    )


def test_the_required_list_is_data_not_lines_in_the_tool():
    """A list buried in a script goes stale silently — the class killed twice today."""
    text = _text()
    assert "preflight_required.json" in text
    assert "REQUIRED_TESTS=" not in text, "the list must live in the contract, not here"


def test_the_requirements_contract_validates():
    """Schema, version, relative paths, no duplicates, and every path exists."""
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))

    assert data["schema"] == "sahool.preflight_required"
    # `version` is a field of its own so the schema name survives evolution; folding it
    # into the name ("...v1") forces a rename on every change and breaks every reader.
    assert isinstance(data["version"], int) and data["version"] >= 1

    listed: list[str] = []
    for key in ("required_tests", "required_scripts"):
        entries = data[key]
        assert entries, f"{key} must not be empty — an empty contract asserts nothing"
        for path in entries:
            assert not Path(path).is_absolute(), f"{key}: absolute path {path!r}"
            assert not path.startswith("../"), f"{key}: escapes the repository: {path!r}"
            assert (ROOT / path).exists(), f"{key}: declared but missing: {path}"
        listed += entries
    assert len(listed) == len(set(listed)), "duplicate entries in the contract"

    for tool in data["optional_tools"]:
        assert {"command", "gate"} <= set(tool), f"optional tool missing keys: {tool}"


def test_no_operational_key_goes_unread():
    """A declared key nobody consumes looks like coverage and is nothing.

    This is the same class as a registered module that never executes, and it is the
    reason to check known keys rather than enforce a name prefix. A prefix rule
    (`everything must start with required_`) was the first proposal; it rejects
    `optional_tools` — deliberately non-blocking — and rejects `adjudicated_on`, which
    `claim_base_guard` *requires* of every `decided` artifact under docs/architecture/.
    A rule that forbids what governance mandates is not a stricter rule, it is a wrong
    one. Known-keys instead: prose may be added freely, operational keys may not.
    """
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    operational = {"required_tests", "required_scripts", "optional_tools"}
    metadata = {"schema", "version", "adjudicated_on"}

    unread = {
        key
        for key in data
        if key not in operational | metadata and not key.endswith(("_ar", "_en", "_note"))
    }
    assert not unread, f"keys nobody reads — declare a consumer or drop them: {sorted(unread)}"
    script = _text()
    for key in operational & set(data):
        assert key in script or key == "optional_tools", (
            f"{key!r} is declared in the contract but the preflight never reads it"
        )


def test_the_contract_lives_with_hand_written_contracts_not_generated_ones():
    """`governance/` holds generated closures; editing there invites editing output.

    Placement is a real decision, not filing: `docs/architecture/` is where the
    hand-authored contracts already are (route placement, non-secret keys, db ownership).
    """
    assert CONTRACT.parent.name == "architecture"
    assert (ROOT / "governance/generated").exists(), (
        "the rationale assumes governance/ is generated output; re-check if that changed"
    )


def test_the_sweep_is_called_with_an_explicit_check_flag():
    """Relying on a tool's default means its meaning can change without touching us."""
    text = _text()
    assert "verify_all_generated.py --check" in text
    sweep = (ROOT / "scripts/ci/verify_all_generated.py").read_text(encoding="utf-8")
    assert '"--check"' in sweep, "the flag the preflight relies on must exist upstream"


def test_regeneration_is_followed_by_a_verification_pass():
    """`--fix` exiting zero says "finished", not "converged"."""
    text = _text()
    fix_at = text.index("verify_all_generated.py --fix")
    assert "verify_all_generated.py --check" in text[fix_at:], (
        "a --fix branch that never re-checks proves nothing about convergence"
    )


def test_the_runbook_carries_a_field_verification_date():
    """A living document without a review date is treated as fact long after it rots."""
    runbook = (ROOT / "docs/runbooks/CI_GATES_AND_PRE_PUSH_PROTOCOL.md").read_text(encoding="utf-8")
    assert re.search(r"آخر تحقّق ميدانيّ:\s*\d{4}-\d{2}-\d{2}", runbook)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__]))
