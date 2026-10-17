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

* carries a **severity label** — ``(High)`` · ``[High]`` · ``**High**`` · ``- High:`` ·
  ``| High |`` · ``severity: High`` for Critical/High/Medium in Title case, or the label
  forms ``- HIGH:`` and ``Finding 3 (HIGH)`` in capitals; **and**
* is **review context** — ``review`` · ``Copilot`` · ``Codex`` · ``finding`` · ``audit`` ·
  ``مراجعة`` · ``ملاحظة`` · ``تدقيق`` in the paragraph or in the commit's subject line —

must name at least one ID registered in ``sahool-brain/gaps/registry.md`` (read with
``brain_commit_claim_guard.registry_ids`` — one reader, not two).

**Calibrated against what it must not condemn.** Bare capitals are domain vocabulary in
this repository — approval tiers ``LOW=0/MEDIUM=1/HIGH=2/CRITICAL=3`` (79dae5e1), a
blocked substance ``(CRITICAL)`` (8722ea99), water-stress levels ``WATCH · CRITICAL``
(7c897ea1) — so capitals count only in the two label forms above. And a severity word
without review context (an owner's or ChatGPT's PR describing alert levels) is not a
finding.

**Honesty limit:** the unit is a paragraph. A paragraph listing three findings passes
with one ID; a finding stated without any severity label is invisible here.

    python scripts/ci/pr_finding_gap_id_guard.py --base origin/main --head HEAD
    python scripts/ci/pr_finding_gap_id_guard.py --pr-body-file body.md
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

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
REVIEW_CONTEXT = re.compile(
    r"(?i:\b(?:review|reviewer|copilot|codex|finding|findings|audit)\b)|مراجعة|ملاحظة|تدقيق"
)


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


def severity_label(paragraph: str) -> str | None:
    for pattern in SEVERITY_LABELS:
        match = pattern.search(paragraph)
        if match:
            return match.group(0).strip()
    return None


def names_registered_id(paragraph: str, known: set[str], gap_id: re.Pattern) -> bool:
    return any(candidate in known for candidate in gap_id.findall(paragraph))


def unanchored_findings(
    text: str, known: set[str], gap_id: re.Pattern, subject: str = ""
) -> list[tuple[str, str]]:
    """``(label, first line)`` of each finding paragraph that names no registered ID."""
    found: list[tuple[str, str]] = []
    subject_is_review = bool(REVIEW_CONTEXT.search(subject))
    for paragraph in paragraphs(text):
        label = severity_label(paragraph)
        if label is None:
            continue
        if not (subject_is_review or REVIEW_CONTEXT.search(paragraph)):
            continue
        if names_registered_id(paragraph, known, gap_id):
            continue
        first = next(line.strip() for line in paragraph.splitlines() if line.strip())
        found.append((label, first[:100]))
    return found


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
    commits: list[tuple[str, str]], body: str | None, known: set[str], gap_id: re.Pattern
) -> list[str]:
    violations: list[str] = []
    for sha, message in commits:
        subject = message.split("\n", 1)[0]
        for label, first in unanchored_findings(message, known, gap_id, subject):
            violations.append(f"commit {sha}: `{label}` — {first}")
    if body is not None:
        for label, first in unanchored_findings(body, known, gap_id):
            violations.append(f"PR body: `{label}` — {first}")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="commit range start (exclusive)")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--pr-body-file", type=Path)
    args = parser.parse_args(argv)
    if args.base is None and args.pr_body_file is None:
        parser.error("nothing to read: pass --base and/or --pr-body-file")

    claim = _claim_guard()
    known = claim.registry_ids()
    commits = commit_messages(args.base, args.head) if args.base else []
    body = args.pr_body_file.read_text(encoding="utf-8") if args.pr_body_file else None
    violations = evaluate(commits, body, known, claim._GAP_ID)
    if violations:
        print("pr_finding_gap_id_guard_failed")
        for violation in violations:
            print(f"  ✗ {violation}")
        print(
            "\nA review finding labelled Critical/High/Medium was fixed or reported without "
            "a gap ID. Register it in sahool-brain/gaps/registry.md (a '## <ID>' section or "
            "a table row starting with the ID) and name the ID in the same paragraph — "
            "otherwise the defect leaves no trace once the PR is merged "
            "(GAP-REGISTRY-DOES-NOT-REQUIRE-IDS-FOR-PR-FINDINGS-01)."
        )
        return 1
    read = f"{len(commits)} commit(s)" + (" + PR body" if body is not None else "")
    print(f"pr_finding_gap_id_guard_ok ({read}; every labelled review finding names an ID)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
