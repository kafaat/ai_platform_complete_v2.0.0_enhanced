#!/usr/bin/env python3
"""Prevent sahool-brain-only edits from claiming executable/certification closure."""

from __future__ import annotations

import argparse
import re
import subprocess

# BRAIN-TRANSITION-GUARD-MATCHES-FAIL-CLOSED-01. `\b(CLOSED)\b` was wrong in both
# directions at once, and the two errors hid each other:
#
#   false positive — `fail-closed` and `open-closed` are DESIGN descriptions, not state
#     transitions, and the hyphen is a word boundary. The term appears 273 times in the
#     brain alone and in 477 files repo-wide, so any brain-only note explaining a
#     fail-closed rule was rejected with a message about "closure/verification
#     transition" -- a true block for a false reason, which is worse than no block,
#     because the message sends the reader to look for a claim that was never made.
#
#   false negative — `CLOSED_IN_CODE` and `CLOSED_IN_CODE_AND_PG_PROVEN` are THIS
#     repository's actual closure vocabulary, and `\b` fails on the trailing `_`, so the
#     real claims the guard exists to catch walked straight past it.
#
# The lookbehind rejects a preceding hyphen or word character (kills `fail-closed`), the
# optional `_UPPER` tail admits the real status tokens, and the trailing lookahead keeps
# `closedness` out. Verified against twelve cases, positive and negative, in
# tests_v9/test_brain_transition_guard_vocabulary.py.
CLOSED_RE = re.compile(
    r"^\+[^+].*(?<![\w-])(CLOSED|VERIFIED|RUNTIME_VERIFIED|PRODUCTION_CERTIFIED)"
    r"(?:_[A-Z][A-Z_]*)?(?![\w-])",
    re.I,
)
SUBSTANTIVE = (
    "services/",
    "scripts/ci/",
    "tests/",
    "tests_v9/",
    ".github/workflows/",
    "migrations/",
    "runtime-verification/",
    "certification/evidence/",
)


# BRAIN-TRANSITION-GUARD-MATCHES-A-QUOTED-STATUS-TOKEN-01. The boundary above kills
# `fail-closed`, but a boundary is not an anchor: `CLOSED_RE` still matches the token
# ANYWHERE in an added line, so citing a field is read as claiming it. Measured, and it
# fired on a real commit: a line saying in so many words that `production_certified=0/81`
# is NOT a defect, and that raising it fails the build, was rejected as a closure claim.
# Prose explaining this repository's honesty invariants must name these fields — that is
# what the invariants ARE — so the guard was blocking the very writing it wants.
#
# The anchor is semantic, and it is the narrowest one that cannot open a hole: a citation
# stating the value is ZERO cannot be a claim that something closed. A real transition
# necessarily asserts a positive state (`runtime_verified: 1`, `— CLOSED`), and those
# still match. Only `TOKEN=0`, `TOKEN: 0`, `TOKEN=false` and their `0/81`-style ratios are
# read as quotations of a current, unclosed value.
#
# Deliberately NOT "ignore a line containing a negation": that is a list wearing a
# pattern's clothes, and it fails on the fourteenth phrasing.
_CITED_AS_ZERO = re.compile(
    r"(?<![\w-])(?:CLOSED|VERIFIED|RUNTIME_VERIFIED|PRODUCTION_CERTIFIED)"
    r"(?:_[A-Z][A-Z_]*)?\s*[=:]\s*(?:0(?![.1-9])|false\b)",
    re.I,
)


# BRAIN-TRANSITION-GUARD-MATCHES-A-DISCUSSED-POLICY-STATE-01, the third false-positive
# class. The token appears as the OBJECT of a sentence about a policy whose state happens
# to be that token -- quoting a registered mutation's text, or prose explaining a gate
# that is closed. `_CITED_AS_ZERO` does not reach it: nothing is being assigned a value.
#
# The anchor is typography, and it is measured, not chosen by taste. Over the 298 brain
# lines this guard blocks today, 149 carry every one of their mentions inside a code span
# or a quotation -- `CLOSED`, «قراءةَ CLOSED إذناً عامّاً». Marking a token as code or
# quoting it is the act of NAMING a literal, not of asserting a state.
#
# The carve-out below is what keeps this from opening a hole, and it was measured too.
# The recorded direction for this gap was "anchor on the heading", on the premise that a
# claim in this repository never lands in prose. That premise is FALSE: `**SAM2** closed
# (gated, env-unverified)` in sahool-brain/strategy.md is a genuine closure claim written
# in running prose, and a heading-only anchor would release it. So prose keeps being read
# -- only its quotations are exempt -- and the canonical claim positions (a heading, a
# `- **الحالة:**` line) are read WHATEVER their typography, so backticking a real claim
# where a real claim belongs cannot smuggle it past.
#
# Residual, stated rather than hidden: a claim written with its token inside backticks in
# running prose escapes. That is the price of every semantic exemption here, and it is
# the narrower price -- the alternative on offer released an entire syntactic position.
_TYPESET_AS_QUOTATION = re.compile(r"`[^`\n]*`|«[^»\n]*»|“[^”\n]*”")
_CANONICAL_CLAIM_POSITION = re.compile(
    r"^\+\s{0,3}(?:#{1,6}\s|[-*]\s*\*\*\s*(?:الحالة|الحالةُ|status)\s*:?\s*\*\*)",
    re.I,
)


# والاقتباسُ لا يُعفي إسناداً بقيمةٍ موجبة، وهذا الحدُّ **مقيسٌ لا احتياطيّ**: السطر
# `` `production_certified: 1` `` ادّعاءٌ بعينه، وخطُّ الشيفرة لا يُغيّر ما يقوله. فلولا
# هذا الشرط لكان إصلاحُ الإيجابيّة الكاذبة صنَع سلبيّةً كاذبةً أخطر — وهو بالضبط الفخّ
# الذي وقعت فيه المحاولةُ الأولى لتضييق `_CITED_AS_ZERO` وسجّله رأسُ هذا الملفّ.
_ASSIGNS_A_VALUE = re.compile(
    r"(?<![\w-])(?:CLOSED|VERIFIED|RUNTIME_VERIFIED|PRODUCTION_CERTIFIED)"
    r"(?:_[A-Z][A-Z_]*)?\s*[=:]\s*\S",
    re.I,
)


def _blank(match: re.Match) -> str:
    """يُفرِغ المقتبَس ويحفظ طولَه — فلا يلتحم ما كان مفصولاً."""
    quotation = match.group(0)
    if _ASSIGNS_A_VALUE.search(_CITED_AS_ZERO.sub("", quotation)):
        return quotation
    return " " * len(quotation)


def _is_claim(line: str) -> bool:
    """سطرٌ مُضاف يدّعي انتقال حالة — لا سطرٌ يقتبس رمزاً أو قيمةً صفريّة."""
    if not CLOSED_RE.search(line):
        return False
    # كلّ ذكرٍ في السطر مقتبَسٌ بقيمة صفر ⇒ ليس ادّعاءً. ويكفي ذِكرٌ واحد غير مقتبَس
    # ليعود السطر ادّعاءً — فالفشل في الجهة الآمنة.
    stripped = _CITED_AS_ZERO.sub("", line)
    if not _CANONICAL_CLAIM_POSITION.match(line):
        stripped = _TYPESET_AS_QUOTATION.sub(_blank, stripped)
    return bool(CLOSED_RE.search(stripped))


def check(paths: list[str], diff: str) -> None:
    claims = [line for line in diff.splitlines() if _is_claim(line)]
    brain_changed = any(p.startswith("sahool-brain/") for p in paths)
    outside = [
        p
        for p in paths
        if any(p.startswith(x) for x in SUBSTANTIVE) and not p.startswith("sahool-brain/")
    ]
    if brain_changed and claims and not outside:
        raise SystemExit(
            "sahool-brain-only closure/verification transition rejected; include executable code/test/evidence outside the brain knowledge base"
        )
    print("brain_state_transition_guard_ok")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base")
    p.add_argument("--head", default="HEAD")
    a = p.parse_args()
    names = subprocess.run(
        ["git", "diff", "--name-only", f"{a.base}...{a.head}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    diff = subprocess.run(
        ["git", "diff", "--unified=0", f"{a.base}...{a.head}", "--", "sahool-brain/"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    check(names, diff)


if __name__ == "__main__":
    main()
