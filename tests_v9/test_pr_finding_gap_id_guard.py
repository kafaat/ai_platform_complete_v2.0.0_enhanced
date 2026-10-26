"""GAP-REGISTRY-DOES-NOT-REQUIRE-IDS-FOR-PR-FINDINGS-01 — a labelled finding names its gap.

PR #1133 fixed four material defects with every gap guard green; the IDs were registered
by hand afterwards. The owner approved (2026-10-15) a guard that ties severity-labelled
review findings to registered gap IDs. The fixtures are verbatim paragraphs from main's
history — the ones it must catch, and the domain-tier vocabulary it must not.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "pr_finding_gap_id_guard", ROOT / "scripts/ci/pr_finding_gap_id_guard.py"
)
guard = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(guard)

_CLAIM = guard._claim_guard()
KNOWN = _CLAIM.registry_ids()
GAP_ID = _CLAIM._GAP_ID
REGISTERED = "GAP-REGISTRY-DOES-NOT-REQUIRE-IDS-FOR-PR-FINDINGS-01"

# 63a1ad7fd (#405), second paragraph — verbatim.
_EXTERNAL_AUDIT_HIGH = """\
تدقيق خارجيّ (High): docker-compose.unified.yml كان يكشف خدمات داخليّة على كلّ
واجهات المضيف (auth:8120, supervisor:8096, guardrails:8097, 4×MCP, edge:8100,
actuator:8111, RAG:8125, ollama:11434, video-processor:8110, agriai:8127,
odoo-bridge:8126) — يتجاوز مبدأ gateway-only ويكشف Ollama (LLM بلا مصادقة)."""

# 18b64ed0f — verbatim.
_COPILOT_HIGH = """\
مراجعة Copilot (High) على #1122: المنصّةُ تبني `policy_mode=full_external` مع
`external_llm_allowed=false` حين لا يقول الصفُّ `ai_generation_allowed=true` صراحةً
(`services/sahool-platform/core/ai_policy_envelope.py:122-127`)، والمستهلكُ القائم يرفض
تلك الحالة (`services/ai_agronomist/policy_envelope.py:135-136`). بوّابةُ الصوت كانت تقرأ
الوضعَ وحده، فنصُّ مستأجِرٍ عطّل التوليد كان سيخرج إلى edge."""

# 79dae5e1 (#308) — approval tiers; the subject says «تدقيق #306». Verbatim.
_APPROVAL_TIERS = (
    "P1 (شريحة ١): موزِّع القرار المحروس — دماغ الحلقة المغلقة (نقيّ، مُختبَر) (#308)",
    """\
core/decision_dispatch.py (نقيّ، لا I/O): `evaluate_dispatch(...)` يُرجِع
DispatchDecision بحالة واحدة من ثلاث:
  • BLOCKED — خرق HALT (خط أحمر) ⇒ لا تنفيذ أبداً، أيّاً كانت الموافقات.
  • PENDING_APPROVAL — محروس لكن يحتاج موافقات (طبقات: LOW=0/MEDIUM=1/HIGH=2/
    CRITICAL=3 مطابِقة لـguardrails-engine/human_in_loop).
  • READY — محروس + موافَق (أو منخفض المخاطر) — مُخلَّص للتنفيذ.""",
)

# 8722ea99 (#322) — a blocked substance tier next to «مراجعة خبير». Verbatim.
_SUBSTANCE_TIER = """\
  • fail-closed على المجهول: ChemicalSafetyTier يحجب المواد المحظورة (CRITICAL) والمجهولة
    (تتطلّب مراجعة خبير) وتجاوز الجرعة — لا تمرير صامت."""

# 7c897ea1 (#469) — water-stress levels. Verbatim.
_WATER_STRESS = """\
D2 (تحكيم الإجهاد المائيّ) حسّاس يغيّر القرار القانونيّ، فطُلِبت خطّة رسميّة + إقرار
عتبة. أُقِرّ نموذج 4 مستويات (المستخدم 2026-06-23): NORMAL>0.5 · WATCH (Dr≥RAW، تنبيه)
· CRITICAL (AWF≤0.2، توصية) · ESCALATE→human_review حصراً عند
AWF≤0.2 ∧ depletion_confidence≥0.8 ∧ تأكيد طيفيّ (فيزياء+رصد، نادر عالي الثقة)."""


def _violations(text: str, subject: str = "") -> list[tuple[str, str]]:
    return guard.unanchored_findings(text, KNOWN, GAP_ID, subject)


# ── what it must catch ────────────────────────────────────────────────────────


@pytest.mark.parametrize("paragraph", [_EXTERNAL_AUDIT_HIGH, _COPILOT_HIGH])
def test_a_labelled_review_finding_without_an_id_is_blocked(paragraph: str) -> None:
    """Merged on main with no gap ID — the class #1133 made visible."""
    found = _violations(paragraph)
    assert len(found) == 1 and found[0][0] == "(High)", found


def test_naming_a_registered_id_is_the_remedy() -> None:
    assert REGISTERED in KNOWN
    assert _violations(_COPILOT_HIGH + f"\nمسجَّلة: {REGISTERED}.") == []


def test_an_unregistered_id_shaped_text_is_not_a_registration() -> None:
    """Writing an ID is not registering one: the claim must resolve in the registry."""
    invented = "TTS-VOICE-GATE-READS-MODE-ONLY-99"
    assert invented not in KNOWN
    assert len(_violations(_COPILOT_HIGH + f"\n{invented}")) == 1


@pytest.mark.parametrize(
    "label",
    [
        "(Medium)",
        "[High]",
        "**Critical**",
        "- High: the cache key ignores the tenant",
        "1. Medium — the retry is unbounded",
        "| High | cache key | fixed |",
        "severity: High",
        "- HIGH: ValidatedRasterProduct rejected an honest mask",
        "Finding 4 (HIGH) — crash loop",
    ],
)
def test_every_label_form_counts(label: str) -> None:
    assert len(_violations(f"Codex review\n{label}")) == 1


def test_the_subject_line_supplies_review_context() -> None:
    assert len(_violations("- High: tenant leak in the export", "fix: address review")) == 1


def test_the_pr_body_is_read_too(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    body = tmp_path / "body.md"
    body.write_text("## Review\n\n" + _COPILOT_HIGH + "\n", encoding="utf-8")
    assert guard.main(["--pr-body-file", str(body)]) == 1
    assert "PR body" in capsys.readouterr().out
    body.write_text(f"## Review\n\n{_COPILOT_HIGH}\n{REGISTERED}\n", encoding="utf-8")
    assert guard.main(["--pr-body-file", str(body)]) == 0


def test_with_nothing_to_read_it_refuses_rather_than_passes() -> None:
    with pytest.raises(SystemExit) as exit_info:
        guard.main([])
    assert exit_info.value.code == 2


# ── what it must not condemn ─────────────────────────────────────────────────


def test_approval_tiers_are_domain_vocabulary_not_a_finding() -> None:
    subject, paragraph = _APPROVAL_TIERS
    assert _violations(paragraph, subject) == []


def test_a_blocked_substance_tier_is_not_a_finding() -> None:
    assert _violations(_SUBSTANCE_TIER) == []


def test_water_stress_levels_are_not_a_finding() -> None:
    assert _violations(_WATER_STRESS, "feat(water): Bundle D / D2a") == []


def test_a_severity_without_review_context_is_not_a_finding() -> None:
    """An owner's or ChatGPT's PR describing alert levels names no review."""
    text = "Alerts now carry a level:\n- High: frost within 6h\n- Medium: frost within 24h"
    assert _violations(text, "feat(alerts): frost levels") == []


def test_one_paragraph_is_one_unit() -> None:
    text = f"Copilot review (High): A.\n{REGISTERED}\n\nCopilot review (Medium): B."
    found = _violations(text)
    assert [label for label, _ in found] == ["(Medium)"]


# ── one ID per labelled finding, not per paragraph ───────────────────────────
# The first slice made the paragraph the unit, so a paragraph listing several findings
# passed with one ID. Main's history (2395 commits) never had a labelled review paragraph
# with two labels, so the tightening adds no flag there — these fixtures are synthetic.

SECOND = "TTS-BAKEOFF-WORKER-INHERITS-HOST-CREDENTIALS-01"
_TWO_FINDINGS = f"Copilot review on #1133:\n- High: worker inherits host credentials\n- Medium: digest marked trusted unverified\n{SECOND}"


def test_two_findings_in_one_paragraph_need_two_ids() -> None:
    """Accepted on main (one ID covered the paragraph); the second finding now needs its own."""
    found = _violations(_TWO_FINDINGS)
    # The one ID stands after the Medium line, so it is Medium's: the High one is unanswered.
    assert [label for label, _ in found] == ["- High:"], found
    assert found[0][1].startswith("[2 labelled findings, 1 registered ID(s)]"), found


def test_one_distinct_id_per_finding_is_the_remedy() -> None:
    assert SECOND in KNOWN
    remedy = _TWO_FINDINGS.replace("credentials\n", f"credentials → {REGISTERED}\n")
    assert remedy != _TWO_FINDINGS
    assert _violations(remedy) == []


def test_naming_the_same_id_twice_is_still_one_id() -> None:
    assert len(_violations(_TWO_FINDINGS + f" · {SECOND}")) == 1


@pytest.mark.parametrize("paragraph", ["severity: **High**", "Finding 3 (High)"])
def test_label_forms_around_one_word_are_one_finding(paragraph: str) -> None:
    """Two patterns matching one severity word are one finding, not two."""
    assert guard.severity_labels(paragraph) == [guard.severity_label(paragraph)]
    assert _violations(f"Codex review — {paragraph}: tenant leak. {REGISTERED}") == []


# ── an ID is bound to its finding, not counted against the paragraph ─────────
# The counting rule passed a paragraph naming N IDs for N findings without saying which
# answers which. Synthetic for the reason above: history has no two-label review paragraph.


def test_ids_listed_apart_from_their_findings_are_not_bound() -> None:
    """Accepted by the counting rule (2 IDs, 2 findings); neither ID stands beside one."""
    text = (
        f"Copilot review on #1133 — registered {REGISTERED} · {SECOND}:\n"
        "- High: worker inherits host credentials\n"
        "- Medium: digest marked trusted unverified"
    )
    found = _violations(text)
    assert [label for label, _ in found] == ["- High:"], found
    assert found[0][1].startswith("[2 labelled findings, 2 registered ID(s), not one beside"), found


def test_a_trailing_list_of_ids_answers_only_the_last_finding() -> None:
    text = (
        "Copilot review on #1133:\n- High: worker inherits host credentials\n"
        f"- Medium: digest marked trusted unverified\nRegistered: {REGISTERED} · {SECOND}"
    )
    assert [label for label, _ in _violations(text)] == ["- High:"]


def test_an_id_written_before_its_label_on_the_same_line_is_bound() -> None:
    text = (
        f"Codex review:\n- {REGISTERED} (High): worker inherits host credentials\n"
        f"- {SECOND} (Medium): digest marked trusted unverified"
    )
    assert _violations(text) == []


def test_two_findings_on_one_line_split_at_the_second_label() -> None:
    bound = f"Codex review: (High) tenant leak {REGISTERED}; (Medium) unbounded retry {SECOND}."
    assert _violations(bound) == []
    unbound = f"Codex review: (High) tenant leak; (Medium) unbounded retry {REGISTERED} {SECOND}."
    assert [label for label, _ in _violations(unbound)] == ["(High)"]


def test_binding_is_a_matching_not_first_come() -> None:
    """High names two IDs and Medium one of them: High takes the other, both are answered."""
    assert REGISTERED < SECOND  # a first-come binder in sorted order gives High REGISTERED
    text = (
        f"Codex review:\n- High: worker inherits host credentials {REGISTERED} {SECOND}\n"
        f"- Medium: digest marked trusted unverified {REGISTERED}"
    )
    assert _violations(text) == []


# ── GitHub review comments, judged from the envelope the workflow measured ────

BOT = {"login": "copilot-pull-request-reviewer[bot]", "type": "Bot"}
OWNER = {"login": "kafaat", "type": "User"}


def _envelope(
    comments: list[dict] | None = None,
    reviews: list[dict] | None = None,
    conversation: list[dict] | None = None,
    *,
    head: str = "kafaat/sahool",
    status: int = 200,
    per_page: int = 100,
) -> dict:
    def pages(items: list[dict]) -> list[dict]:
        return [{"page": 1, "http_status": status, "items": items if status == 200 else None}]

    return {
        "schema_version": "sahool.pr-review-bodies.v2",
        "repository": "kafaat/sahool",
        "head_repository": head,
        "pr_number": 1234,
        "per_page": per_page,
        "fetches": {
            "comments": pages(comments or []),
            "reviews": pages(reviews or []),
            "issue_comments": pages(conversation or []),
        },
    }


def _comment(cid: int, body: str, *, reply_to: int | None = None, user: dict = BOT) -> dict:
    return {"id": cid, "body": body, "user": user, "in_reply_to_id": reply_to}


_INLINE_HIGH = _comment(11, "**High** — the export joins tenants without `tenant_id`.")


def _run(tmp_path: Path, envelope: object, *extra: str, body: str = "") -> int:
    reviews = tmp_path / "reviews.json"
    reviews.write_text(json.dumps(envelope), encoding="utf-8")
    pr_body = tmp_path / "body.md"
    pr_body.write_text(body, encoding="utf-8")
    argv = ["--pr-body-file", str(pr_body), "--review-comments-file", str(reviews)]
    return guard.main([*argv, "--event-name", "pull_request", *extra])


def test_an_unregistered_high_review_comment_is_blocked(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Not read on main at all; a bot's labelled inline finding now needs its gap ID."""
    assert _run(tmp_path, _envelope([_INLINE_HIGH])) == 1
    out = capsys.readouterr().out
    assert "review comment 11 by copilot-pull-request-reviewer[bot]: `**High**`" in out, out


def test_a_reply_in_the_thread_naming_the_id_is_the_remedy(tmp_path: Path) -> None:
    reply = _comment(12, f"Registered as {REGISTERED}.", reply_to=11, user=OWNER)
    assert _run(tmp_path, _envelope([_INLINE_HIGH, reply])) == 0


def test_a_reply_in_another_thread_does_not_anchor(tmp_path: Path) -> None:
    other = _comment(20, "nit: rename")
    reply = _comment(21, f"Registered as {REGISTERED}.", reply_to=20, user=OWNER)
    assert _run(tmp_path, _envelope([_INLINE_HIGH, other, reply])) == 1


def test_a_review_body_is_anchored_by_a_pr_body_paragraph_that_links_it(
    tmp_path: Path,
) -> None:
    """A review summary has no reply button: the PR body links it and names the IDs."""
    review = {"id": 77, "body": "Review:\n- High: A\n- Medium: B", "user": OWNER, "state": "X"}
    envelope = _envelope(reviews=[review])
    assert _run(tmp_path, envelope) == 1
    link = "https://github.com/kafaat/sahool/pull/1234#pullrequestreview-77"
    assert _run(tmp_path, envelope, body=f"{link}: {REGISTERED} · {SECOND}") == 0
    assert _run(tmp_path, envelope, body=f"{link}: {REGISTERED}") == 1


def test_ids_in_a_review_root_bind_to_the_finding_they_stand_beside(tmp_path: Path) -> None:
    """A root that lists two findings and both IDs on the first line answers only one."""
    root = f"Review — {REGISTERED} {SECOND}\n- High: A\n- Medium: B"
    review = {"id": 78, "body": root, "user": OWNER, "state": "X"}
    assert _run(tmp_path, _envelope(reviews=[review])) == 1
    beside = {**review, "body": f"Review\n- High: A {REGISTERED}\n- Medium: B {SECOND}"}
    assert _run(tmp_path, _envelope(reviews=[beside])) == 0


def test_labels_in_a_reply_are_not_counted_as_new_findings(tmp_path: Path) -> None:
    reply = _comment(12, f"Fixed the (High) one: {REGISTERED}.", reply_to=11, user=OWNER)
    assert _run(tmp_path, _envelope([_INLINE_HIGH, reply])) == 0


# ── the Conversation tab (/issues/<n>/comments) ──────────────────────────────
# Not read before: a labelled finding posted there passed with no ID. Measured
# 2026-10-26 on this repository's 350 Conversation comments (287 by the owner, 48
# dependabot, 13 Copilot, 2 others): none carries a severity label form, so reading
# them adds no flag to history; these fixtures are synthetic.

_CONVERSATION_HIGH = {
    "id": 501,
    "body": "## Code review\n\nTwo things before merge.\n\n- High: the export joins tenants",
    "user": {"login": "claude[bot]", "type": "Bot"},
}


def test_a_labelled_conversation_finding_without_an_id_is_blocked(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """The comment's first line is the review context, as a commit's subject line is."""
    assert _run(tmp_path, _envelope(conversation=[_CONVERSATION_HIGH])) == 1
    out = capsys.readouterr().out
    assert "Conversation comment 501 by claude[bot]: `- High:`" in out, out


def test_a_conversation_finding_is_answered_beside_it_or_by_a_link(tmp_path: Path) -> None:
    named = {**_CONVERSATION_HIGH, "body": _CONVERSATION_HIGH["body"] + f" → {REGISTERED}"}
    assert _run(tmp_path, _envelope(conversation=[named])) == 0
    link = "https://github.com/kafaat/sahool/pull/1234#issuecomment-501"
    linked = _envelope(conversation=[_CONVERSATION_HIGH])
    assert _run(tmp_path, linked, body=f"{link}: {REGISTERED}") == 0
    reply = {"id": 502, "body": f"Fixed, see {link}: {REGISTERED}", "user": OWNER}
    assert _run(tmp_path, _envelope(conversation=[_CONVERSATION_HIGH, reply])) == 0


def test_a_conversation_table_outside_a_review_is_not_a_finding(tmp_path: Path) -> None:
    """A Conversation comment is not review context by definition: a bot posts tables there."""
    advisory = {
        "id": 600,
        "body": "Dependency advisories\n\n| Package | Severity |\n|---|---|\n| foo | High |",
        "user": {"login": "some-scanner[bot]", "type": "Bot"},
    }
    assert _run(tmp_path, _envelope(conversation=[advisory])) == 0
    as_review = {**advisory, "body": "Security review\n\n" + advisory["body"]}
    assert _run(tmp_path, _envelope(conversation=[as_review])) == 1


def test_a_conversation_fetch_failure_on_the_same_repository_fails_closed(
    tmp_path: Path,
) -> None:
    envelope = _envelope()
    envelope["fetches"]["issue_comments"] = [{"page": 1, "http_status": 403, "items": None}]
    assert _run(tmp_path, envelope) == 1


def test_an_envelope_without_the_conversation_kind_is_a_read_error(tmp_path: Path) -> None:
    """A fetch step that stopped reading the Conversation tab must not pass as «none there»."""
    envelope = _envelope()
    del envelope["fetches"]["issue_comments"]
    assert _run(tmp_path, envelope) == 1


def test_a_fork_fetch_failure_is_reported_not_measured(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert _run(tmp_path, _envelope(head="contributor/sahool", status=403)) == 0
    out = capsys.readouterr().out
    assert "review comments NOT MEASURED — fork PR" in out and "HTTP 403" in out, out


def test_a_same_repository_fetch_failure_fails_closed(tmp_path: Path) -> None:
    assert _run(tmp_path, _envelope(status=403)) == 1


@pytest.mark.parametrize(
    "breakage",
    ["not json", "html body", "full last page", "page gap", "wrong schema"],
)
def test_a_read_error_fails_closed_even_on_a_fork(tmp_path: Path, breakage: str) -> None:
    envelope = _envelope([_comment(1, "ok")], head="contributor/sahool", per_page=1)
    if breakage == "not json":
        (tmp_path / "reviews.json").write_text("{", encoding="utf-8")
    if breakage == "html body":
        envelope["fetches"]["reviews"][0]["items"] = None
    if breakage == "page gap":
        envelope["fetches"]["reviews"][0]["page"] = 2
    if breakage == "wrong schema":
        envelope["schema_version"] = "v0"
    if breakage != "full last page":
        envelope["per_page"] = 100
    if breakage == "not json":
        args = ["--review-comments-file", str(tmp_path / "reviews.json")]
        assert guard.main([*args, "--event-name", "pull_request"]) == 1
        return
    assert _run(tmp_path, envelope) == 1


def test_every_page_is_read(tmp_path: Path) -> None:
    envelope = _envelope([_comment(1, "nit")], per_page=1)
    envelope["fetches"]["comments"].append({"page": 2, "http_status": 200, "items": [_INLINE_HIGH]})
    envelope["fetches"]["comments"].append({"page": 3, "http_status": 200, "items": []})
    assert _run(tmp_path, envelope) == 1


def test_on_a_push_event_missing_pr_inputs_are_a_printed_no_op(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    missing = ["--pr-body-file", str(tmp_path / "a"), "--review-comments-file", str(tmp_path / "b")]
    assert guard.main([*missing, "--event-name", "push"]) == 0
    out = capsys.readouterr().out
    assert "a `push` event has no pull request" in out, out
    assert "pr_finding_gap_id_guard_not_measured" in out, out


@pytest.mark.parametrize("event", [["--event-name", "pull_request"], []])
def test_a_missing_review_file_on_a_pr_fails_closed(tmp_path: Path, event: list[str]) -> None:
    assert guard.main(["--review-comments-file", str(tmp_path / "absent.json"), *event]) == 1


def test_the_workflow_measures_review_comments_and_the_guard_judges_them() -> None:
    """The job fetches every page with a read-only token; the guard step reads the file."""
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/capability-governance.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["capability-registry"]
    assert job["permissions"] == {"contents": "read", "pull-requests": "read", "issues": "read"}
    steps = {step.get("name", ""): step for step in job["steps"]}
    fetch = steps["Fetch the PR's review comments and review bodies"]
    assert "pull_request" in fetch["if"]
    for fragment in (
        "for KIND in comments reviews issue_comments",
        'issue_comments) URL="${REPO_API}/issues/${PR_NUMBER}/comments"',
        "per_page=${PER_PAGE}&page=${PAGE}",
        "sahool.pr-review-bodies.v2",
        "head_repository: $head_repo",
    ):
        assert fragment in fetch["run"], fragment
    judge = next(s for s in job["steps"] if "pr_finding_gap_id_guard.py" in s.get("run", ""))
    assert "--review-comments-file /tmp/pr-reviews.json" in judge["run"]
    assert "--event-name" in judge["run"] and judge["if"] == "${{ !cancelled() }}"
