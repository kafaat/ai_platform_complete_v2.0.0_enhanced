#!/usr/bin/env python3
"""A severity-labelled review finding in a PR must name a registered gap ID.

GAP-REGISTRY-DOES-NOT-REQUIRE-IDS-FOR-PR-FINDINGS-01 (owner decision 2026-10-15: approved).

PR #1133 fixed four material defects and every gap guard stayed green: the registry
measurement checks the consistency of what *was* registered (duplicates, canonical states,
transitions) and nothing asks that a defect fixed inside a PR be registered at all. The
four were registered by hand afterwards. ``brain_commit_claim_guard`` is the converse —
an ID that *is* named must exist — so a finding that names no ID passes both.

**The rule.** In the PR's commit messages (``--base``/``--head``) and in its body
(``--pr-body-file``), a paragraph that

* carries **severity labels** — ``(High)`` · ``[High]`` · ``**High**`` · ``- High:`` ·
  ``| High |`` · ``severity: High`` for Critical/High/Medium in Title case, or the label
  forms ``- HIGH:`` and ``Finding 3 (HIGH)`` in capitals; **and**
* is **review context** — ``review`` · ``Copilot`` · ``Codex`` · ``finding`` · ``audit`` ·
  ``مراجعة`` · ``ملاحظة`` · ``تدقيق`` in the paragraph or in the commit's subject line —

must name **one distinct registered ID per labelled finding** (IDs are those registered in
``sahool-brain/gaps/registry.md``, read with ``brain_commit_claim_guard.registry_ids`` —
one reader, not two).

**The finding unit is the label occurrence.** Each place a severity word stands in a label
form is one finding; two label forms around the same word (``severity: **High**``,
``Finding 3 (High)``) are one finding, because they share the word's position. A paragraph
with three labelled findings and one ID used to pass; it now needs three distinct
registered IDs. Calibrated on main's history before it was tightened (the evidence note
``docs/evidence/pr_finding_gap_id_calibration_20261017.md``): no labelled review paragraph
in 2395 commits carried more than one label, so the counting rule adds no flag there.

**An ID is bound to its finding, not counted.** Where several labelled findings share a
text, each finding's *segment* runs from the start of its label's line (or from the label
itself when the previous label sits on the same line) to the next finding's segment; the
ID that answers a finding must stand in that segment, and no ID answers two findings
(a bipartite matching, so the order IDs are written in does not matter). ``- High: A →
X-01`` / ``- Medium: B → Y-01`` passes; ``Registered X-01, Y-01:`` above the same two
findings does not, because nothing says which answers which. A text with one finding is
one segment — the rule calibrated on history is unchanged there.

**Review comments on GitHub** (``--review-comments-file``). GitHub state does not enter
this tool directly — the workflow job fetches the PR's inline review comments, review
bodies and Conversation-tab comments (every page) into a JSON envelope, and this guard
judges the envelope. Every inline comment and review body is review context by
definition, and every author counts: review bots (Copilot, Codex, Claude) are exactly who
emits severity labels. The unit there is the **thread**, because the remedy is a reply:
the labelled findings of a thread's root (an inline comment, or a review body) need as
many distinct registered IDs — bound by segment when named in the root itself, or
supplied by a reply in that thread (``in_reply_to_id``) or by a PR-body/commit/
Conversation paragraph that links the thread (``#discussion_r<id>`` /
``#pullrequestreview-<id>`` — a review body has no reply button). Replies supply IDs
only; a finding first stated in a reply is not counted.

**Conversation-tab comments** (``/issues/<n>/comments``) are threads of their own, but
not review context by definition — a bot posting a deploy or an advisory table there is
not reviewing. A labelled paragraph counts when it, or the comment's first line, is in
review context (as for a commit's subject line). The remedy is an ID beside the finding,
or a paragraph elsewhere that links ``#issuecomment-<id>`` and names it.

The envelope is judged before its content: a page that is not HTTP 200 is a **fetch
failure**, which fails closed — except on a PR from a fork, whose token may not read the
base repository; that one case is reported as **not measured** and skipped, by name. A
200 page whose body is not the expected list, a gap in the page sequence, or a last page
that is still full (pagination cap hit) is a **read error** and always fails closed. A
missing envelope fails closed, unless ``--event-name`` says the event has no pull request
(a push to main) — then the PR-scoped inputs are reported as not read and skipped.

**Calibrated against what it must not condemn.** Bare capitals are domain vocabulary in
this repository — approval tiers ``LOW=0/MEDIUM=1/HIGH=2/CRITICAL=3`` (79dae5e1), a
blocked substance ``(CRITICAL)`` (8722ea99), water-stress levels ``WATCH · CRITICAL``
(7c897ea1) — so capitals count only in the two label forms above. And a severity word
without review context (an owner's or ChatGPT's PR describing alert levels) is not a
finding.

**Honesty limits:** binding is positional, so it holds where the ID and the finding share
a text; IDs that arrive from a reply or a linking paragraph have no position in the
finding's text and are still counted against the thread's findings, not bound to one.
A finding stated without any severity label is invisible here. The workflow runs on
push/edit of the PR, so a review or Conversation comment posted after the last run is read
on the next one, not before a merge that follows it without a push.

    python scripts/ci/pr_finding_gap_id_guard.py --base origin/main --head HEAD
    python scripts/ci/pr_finding_gap_id_guard.py --pr-body-file body.md \\
        --review-comments-file reviews.json --event-name pull_request
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]

_TITLE = r"(?:Critical|High|Medium)"
_CAPS = r"(?:CRITICAL|HIGH|MEDIUM)"
SEVERITY_LABELS = (
    re.compile(rf"\({_TITLE}\)"),
    re.compile(rf"\[{_TITLE}\]"),
    re.compile(rf"\*\*{_TITLE}\*\*"),
    re.compile(rf"^\s*(?:[-*•]|\d+[.)])\s*{_TITLE}\s*[:—–]", re.MULTILINE),
    re.compile(rf"^\s*[-*•]\s*{_CAPS}\s*:", re.MULTILINE),
    re.compile(rf"\|\s*{_TITLE}\s*\|"),
    re.compile(rf"\b[Ss]everity\s*[:=]\s*\**{_TITLE}\b"),
    re.compile(rf"\b[Ff]inding\s*#?\d*\s*\((?:{_TITLE}|{_CAPS})\)"),
)
_SEVERITY_WORD = re.compile(rf"{_TITLE}|{_CAPS}")
REVIEW_CONTEXT = re.compile(
    r"(?i:\b(?:review|reviewer|copilot|codex|finding|findings|audit)\b)|مراجعة|ملاحظة|تدقيق"
)
# The anchors GitHub gives an inline comment, a review and a Conversation comment in
# their html_url.
THREAD_LINK = re.compile(r"(discussion_r|pullrequestreview-|issuecomment-)(\d+)")

ENVELOPE_SCHEMA = "sahool.pr-review-bodies.v2"
# ``comments``/``reviews`` come from ``/pulls/<n>/…``; ``issue_comments`` is the
# Conversation tab, ``/issues/<n>/comments``.
REVIEW_KINDS = ("comments", "reviews", "issue_comments")
PR_EVENTS = {"pull_request", "pull_request_target"}


def _claim_guard():
    spec = importlib.util.spec_from_file_location(
        "_brain_commit_claim_guard", ROOT / "scripts/ci/brain_commit_claim_guard.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def _label_spans(paragraph: str) -> list[tuple[int, str]]:
    """``(start, label)`` per labelled finding, in order of its severity word.

    Label forms sharing a severity word are one finding; it keeps the first form's text and
    starts where the earliest of them starts (``Finding 3 (High)`` starts at ``Finding``).
    """
    by_word: dict[int, tuple[int, str]] = {}
    for pattern in SEVERITY_LABELS:
        for match in pattern.finditer(paragraph):
            word = _SEVERITY_WORD.search(paragraph, match.start(), match.end())
            assert word is not None  # every label pattern contains a severity word
            start, label = by_word.get(word.start(), (match.start(), match.group(0).strip()))
            by_word[word.start()] = (min(start, match.start()), label)
    return [by_word[position] for position in sorted(by_word)]


def severity_labels(paragraph: str) -> list[str]:
    """Each labelled finding once, in order: label forms sharing a severity word are one."""
    return [label for _, label in _label_spans(paragraph)]


def severity_label(paragraph: str) -> str | None:
    labels = severity_labels(paragraph)
    return labels[0] if labels else None


def finding_segments(paragraph: str) -> list[tuple[str, str]]:
    """``(label, segment)`` per finding: the text an ID must stand in to answer it.

    One finding: the whole paragraph. Several: each segment opens at the start of its
    label's line — or at the label, when the previous label shares that line — and runs
    to where the next one opens. Text above the first label's line answers none of them.
    """
    spans = _label_spans(paragraph)
    if not spans:
        return []
    if len(spans) == 1:
        return [(spans[0][1], paragraph)]
    opens: list[int] = []
    for k, (start, _) in enumerate(spans):
        line_start = paragraph.rfind("\n", 0, start) + 1
        shares_line = k > 0 and spans[k - 1][0] >= line_start
        opens.append(start if shares_line else line_start)
    closes = opens[1:] + [len(paragraph)]
    return [(label, paragraph[a:b]) for (_, label), a, b in zip(spans, opens, closes, strict=True)]


def registered_ids(paragraph: str, known: set[str], gap_id: re.Pattern) -> set[str]:
    return {candidate for candidate in gap_id.findall(paragraph) if candidate in known}


def _first_line(text: str) -> str:
    return next(line.strip() for line in text.splitlines() if line.strip())[:100]


def _shortfall(
    findings: list[tuple[str, set[str]]], pool: frozenset[str] = frozenset()
) -> str | None:
    """The first finding left without a distinct ID bound to it, or ``None``.

    Finding *k* may take an ID from its own segment or from ``pool`` (IDs a reply or a
    linking paragraph supplied, which have no position to bind by); no ID answers two
    findings. Augmenting paths (Kuhn), so the order IDs are written in does not matter.
    """
    holder: dict[str, int] = {}

    def bind(k: int, seen: set[str]) -> bool:
        for candidate in sorted(findings[k][1] | pool):
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate not in holder or bind(holder[candidate], seen):
                holder[candidate] = k
                return True
        return False

    for k, (label, _) in enumerate(findings):
        if not bind(k, set()):
            return label
    return None


def _tally(findings: list[tuple[str, set[str]]], named: set[str]) -> str:
    """``named``: every registered ID the unit names, beside a finding or not."""
    if len(findings) < 2:
        return ""
    unbound = ", not one beside each" if len(named) >= len(findings) else ""
    return f"[{len(findings)} labelled findings, {len(named)} registered ID(s){unbound}] "


def unanchored_findings(
    text: str, known: set[str], gap_id: re.Pattern, subject: str = ""
) -> list[tuple[str, str]]:
    """``(label, first line)`` for each finding paragraph with a finding no ID answers."""
    found: list[tuple[str, str]] = []
    subject_is_review = bool(REVIEW_CONTEXT.search(subject))
    for paragraph in paragraphs(text):
        segments = finding_segments(paragraph)
        if not segments:
            continue
        if not (subject_is_review or REVIEW_CONTEXT.search(paragraph)):
            continue
        findings = [(label, registered_ids(seg, known, gap_id)) for label, seg in segments]
        label = _shortfall(findings)
        if label is not None:
            named = registered_ids(paragraph, known, gap_id)
            found.append((label, _tally(findings, named) + _first_line(paragraph)))
    return found


# ── GitHub review comments, as the workflow job measured them ────────────────


class ReviewReadError(ValueError):
    """The envelope cannot be read as what the fetch step promised — always fails closed."""


class Thread(NamedTuple):
    """One reply unit: a NamedTuple, not a dataclass — guards load without ``sys.modules``."""

    key: tuple[str, int]  # ("discussion_r" | "pullrequestreview-" | "issuecomment-", id)
    where: str
    root: str
    replies: list[str]
    # A Conversation comment is not review context by definition (a deploy bot posts there).
    needs_context: bool = False


def _author(item: dict) -> str:
    user = item.get("user")
    if not isinstance(user, dict):
        return "ghost"
    login = str(user.get("login", "?"))
    return f"{login} [bot]" if user.get("type") == "Bot" and "[bot]" not in login else login


def _items(envelope: object) -> tuple[dict[str, list[dict]], list[str]]:
    """Every item per kind, and the fetch failures; raise on anything unreadable."""
    if not isinstance(envelope, dict) or envelope.get("schema_version") != ENVELOPE_SCHEMA:
        raise ReviewReadError(f"not a {ENVELOPE_SCHEMA} envelope")
    per_page = envelope.get("per_page")
    fetches = envelope.get("fetches")
    if not isinstance(per_page, int) or per_page < 1 or not isinstance(fetches, dict):
        raise ReviewReadError("envelope lacks per_page/fetches")
    items: dict[str, list[dict]] = {}
    failures: list[str] = []
    for kind in REVIEW_KINDS:
        pages = fetches.get(kind)
        if not isinstance(pages, list) or not pages:
            raise ReviewReadError(f"{kind}: no page recorded")
        items[kind] = []
        for number, page in enumerate(pages, start=1):
            if not isinstance(page, dict) or page.get("page") != number:
                raise ReviewReadError(f"{kind}: page sequence broken at {number}")
            status = page.get("http_status")
            if status != 200:
                failures.append(f"{kind} page {number}: HTTP {status}")
                break
            body = page.get("items")
            if not isinstance(body, list) or not all(isinstance(i, dict) for i in body):
                raise ReviewReadError(f"{kind} page {number}: HTTP 200 but not a list of objects")
            for item in body:
                if not isinstance(item.get("id"), int) or not isinstance(
                    item.get("body") or "", str
                ):
                    raise ReviewReadError(f"{kind} page {number}: item without int id/str body")
            items[kind].extend(body)
            if number == len(pages) and len(body) >= per_page:
                raise ReviewReadError(
                    f"{kind}: last page {number} is full — pagination cap hit, not read to the end"
                )
    return items, failures


def review_threads(items: dict[str, list[dict]]) -> list[Thread]:
    """Inline threads (root + ``in_reply_to_id`` replies), review bodies and Conversation
    comments, each one unit."""
    threads: dict[tuple[str, int], Thread] = {}
    comments = items["comments"]
    roots = {c["id"] for c in comments if c.get("in_reply_to_id") is None}
    for comment in comments:
        parent = comment.get("in_reply_to_id")
        if parent is None or parent not in roots:  # an orphaned reply stands on its own
            key = ("discussion_r", comment["id"])
            where = f"review comment {comment['id']} by {_author(comment)}"
            threads[key] = Thread(key, where, comment["body"] or "", [])
    for comment in comments:
        parent = comment.get("in_reply_to_id")
        if parent is not None and parent in roots:
            threads[("discussion_r", parent)].replies.append(comment["body"] or "")
    for review in items["reviews"]:
        if (review["body"] or "").strip():
            key = ("pullrequestreview-", review["id"])
            threads[key] = Thread(
                key, f"review {review['id']} by {_author(review)}", review["body"], []
            )
    for comment in items["issue_comments"]:
        if (comment["body"] or "").strip():
            key = ("issuecomment-", comment["id"])
            where = f"Conversation comment {comment['id']} by {_author(comment)}"
            threads[key] = Thread(key, where, comment["body"], [], needs_context=True)
    return list(threads.values())


def thread_anchors(texts: list[str], known: set[str], gap_id: re.Pattern) -> dict:
    """Registered IDs named in an author paragraph that links a thread, per thread key."""
    anchors: dict[tuple[str, int], set[str]] = {}
    for text in texts:
        for paragraph in paragraphs(text):
            ids = registered_ids(paragraph, known, gap_id)
            for prefix, number in THREAD_LINK.findall(paragraph):
                anchors.setdefault((prefix, int(number)), set()).update(ids)
    return anchors


def unanchored_review_findings(
    threads: list[Thread], anchors: dict, known: set[str], gap_id: re.Pattern
) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for thread in threads:
        labels = [label for p in paragraphs(thread.root) for label in severity_labels(p)]
        if not labels:
            continue
        opening_is_review = bool(REVIEW_CONTEXT.search(_first_line(thread.root)))
        judged = [
            p
            for p in paragraphs(thread.root)
            if not thread.needs_context or opening_is_review or REVIEW_CONTEXT.search(p)
        ]
        # One finding in the whole root: the root is its segment (an ID in another
        # paragraph of it still answers). Several: each is bound inside its paragraph.
        segments = [s for p in judged for s in finding_segments(p)]
        if len(segments) == 1:
            segments = [(segments[0][0], thread.root)]
        findings = [(label, registered_ids(text, known, gap_id)) for label, text in segments]
        pool = frozenset(anchors.get(thread.key, set())).union(
            *(registered_ids(reply, known, gap_id) for reply in thread.replies)
        )
        label = _shortfall(findings, pool)
        if label is not None:
            found.append(
                (
                    f"{thread.where}: `{label}`",
                    _tally(findings, pool | registered_ids(thread.root, known, gap_id))
                    + _first_line(thread.root),
                )
            )
    return found


def read_review_envelope(path: Path) -> tuple[list[Thread] | None, str]:
    """``(threads, note)``; ``threads`` is ``None`` when a fork's fetch failed (not measured)."""
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewReadError(f"not JSON: {exc}") from exc
    items, failures = _items(envelope)
    if failures:
        if envelope.get("head_repository") != envelope.get("repository"):
            return None, (
                "review comments NOT MEASURED — fork PR "
                f"({envelope.get('head_repository')} → {envelope.get('repository')}) and the "
                f"fork's token could not read them ({'; '.join(failures)}). Fail-open for a "
                "fork's fetch failure only; a read error would still fail closed."
            )
        raise ReviewReadError(f"fetch failed on a same-repository PR: {'; '.join(failures)}")
    threads = review_threads(items)
    return threads, (
        f"{len(items['comments'])} review comment(s) + {len(items['reviews'])} review(s) + "
        f"{len(items['issue_comments'])} Conversation comment(s) in {len(threads)} thread(s)"
    )


def commit_messages(base: str, head: str) -> list[tuple[str, str]]:
    out = subprocess.run(
        ["git", "log", "--no-merges", "--format=%H%x00%B%x1e", f"{base}..{head}"],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout
    messages: list[tuple[str, str]] = []
    for record in out.split("\x1e"):
        if "\x00" in record:
            sha, body = record.split("\x00", 1)
            messages.append((sha.strip()[:9], body.strip("\n")))
    return messages


def evaluate(
    commits: list[tuple[str, str]],
    body: str | None,
    known: set[str],
    gap_id: re.Pattern,
    threads: list[Thread] | None = None,
) -> list[str]:
    violations: list[str] = []
    for sha, message in commits:
        subject = message.split("\n", 1)[0]
        for label, first in unanchored_findings(message, known, gap_id, subject):
            violations.append(f"commit {sha}: `{label}` — {first}")
    if body is not None:
        for label, first in unanchored_findings(body, known, gap_id):
            violations.append(f"PR body: `{label}` — {first}")
    if threads:
        texts = [message for _, message in commits] + ([body] if body is not None else [])
        # A Conversation comment that links a thread is a reply to it in all but placement.
        texts += [t.root for t in threads if t.key[0] == "issuecomment-"]
        anchors = thread_anchors(texts, known, gap_id)
        for where, first in unanchored_review_findings(threads, anchors, known, gap_id):
            violations.append(f"{where} — {first}")
    return violations


def _pr_scoped(path: Path | None, flag: str, event: str | None, notes: list[str]) -> bool:
    """Whether ``path`` is to be read; a missing file is skipped only off a PR event."""
    if path is None:
        return False
    if path.is_file():
        return True
    if event is not None and event not in PR_EVENTS:
        notes.append(f"{flag}: not read — a `{event}` event has no pull request to measure")
        return False
    raise ReviewReadError(f"{flag} {path} does not exist — the step that writes it did not run")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="commit range start (exclusive)")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--pr-body-file", type=Path)
    parser.add_argument(
        "--review-comments-file",
        type=Path,
        help=f"{ENVELOPE_SCHEMA} JSON written by the workflow's fetch step",
    )
    parser.add_argument(
        "--event-name", help="github.event_name; off a PR event a missing PR input is a no-op"
    )
    args = parser.parse_args(argv)
    if args.base is None and args.pr_body_file is None and args.review_comments_file is None:
        parser.error("nothing to read: pass --base, --pr-body-file and/or --review-comments-file")

    notes: list[str] = []
    try:
        read_body = _pr_scoped(args.pr_body_file, "--pr-body-file", args.event_name, notes)
        read_reviews = _pr_scoped(
            args.review_comments_file, "--review-comments-file", args.event_name, notes
        )
        threads, note = (
            read_review_envelope(args.review_comments_file) if read_reviews else (None, "")
        )
    except ReviewReadError as exc:
        print(f"pr_finding_gap_id_guard_failed\n  ✗ cannot read the PR's review input: {exc}")
        return 1
    if note:
        notes.append(note)

    claim = _claim_guard()
    known = claim.registry_ids()
    commits = commit_messages(args.base, args.head) if args.base else []
    body = args.pr_body_file.read_text(encoding="utf-8") if read_body else None
    for line in notes:
        print(f"  · {line}")
    violations = evaluate(commits, body, known, claim._GAP_ID, threads)
    if violations:
        print("pr_finding_gap_id_guard_failed")
        for violation in violations:
            print(f"  ✗ {violation}")
        print(
            "\nA review finding labelled Critical/High/Medium was fixed or reported without "
            "its own gap ID. Register each finding in sahool-brain/gaps/registry.md (a '## <ID>' "
            "section or a table row starting with the ID) and name one ID per labelled finding "
            "beside it — on the finding's own line, before the next labelled finding; a list "
            "of IDs above or below several findings does not say which answers which. For a "
            "GitHub review or Conversation comment, name it in a reply in its thread or in a "
            "PR-body/Conversation paragraph that links it — otherwise the defect leaves no "
            "trace once the PR is merged (GAP-REGISTRY-DOES-NOT-REQUIRE-IDS-FOR-PR-FINDINGS-01)."
        )
        return 1
    if not (args.base or read_body or threads is not None):
        print("pr_finding_gap_id_guard_not_measured (nothing to read on this event — see above)")
        return 0
    read = [f"{len(commits)} commit(s)"] if args.base else []
    read += ["PR body"] if body is not None else []
    read += ["review + Conversation comments"] if threads is not None else []
    read += ["review comments NOT MEASURED (fork)"] if read_reviews and threads is None else []
    print(
        f"pr_finding_gap_id_guard_ok ({' + '.join(read)}; "
        "every labelled review finding names its own ID)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
