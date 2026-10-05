#!/usr/bin/env python3
"""Prevent sahool-brain-only edits from claiming executable/certification closure."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

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

# BRAIN-TRANSITION-GUARD-BLIND-TO-FRONTEND-CODE-01. `SUBSTANTIVE` had no frontend entry, so a
# real frontend fix (source plus vitest) carrying its brain row was rejected as "brain-only"
# -- measured on FRONTEND-REFERENCE-LISTS-CALL-MAP-ON-AN-ENVELOPE-01, which had to reword its
# status to pass. The repair is deliberately NOT a `frontend/` prefix: that would let a
# README, a config file or a regenerated `*.generated.ts` stand in as evidence of a fix.
# Only executable source and its tests count -- `.ts/.tsx/.js/.jsx` under `frontend/src/` or
# `frontend/e2e/`, and never a generated artifact.
_FRONTEND_CODE_ROOTS = ("frontend/src/", "frontend/e2e/")
_FRONTEND_CODE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")


def _is_frontend_code(path: str) -> bool:
    """مصدرُ واجهةٍ قابلٌ للتنفيذ أو اختبارُه — لا توثيق ولا إعداد ولا مُولَّد."""
    return (
        path.startswith(_FRONTEND_CODE_ROOTS)
        and path.endswith(_FRONTEND_CODE_SUFFIXES)
        and ".generated." not in path
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


def _has_executable_evidence(paths: list[str]) -> bool:
    """في نطاق الـPR شيفرةٌ أو اختبارٌ أو دليلٌ خارج الدماغ (``SUBSTANTIVE`` أو مصدرُ الواجهة)."""
    return any(
        (any(p.startswith(x) for x in SUBSTANTIVE) or _is_frontend_code(p))
        and not p.startswith("sahool-brain/")
        for p in paths
    )


# BRAIN-TRANSITION-GUARD-BLIND-TO-FIXED-01. ``CLOSED_RE`` لا يطابق ``fixed``، فكان صفٌّ يُنقل إلى fixed في تعديلٍ
# للدماغ وحده يمرّ — وقاعدةُ «fixed في PR إصلاحها» (decisions/ledger.md، #1136) مطلبُ مراجعةٍ بلا إنفاذ.
# العلاجُ ليس مطابقةَ الكلمة (تُذكر fixed في السجلّ ولقطة التركيز والسرد آلافَ المرّات): يُقرأ **انتقالُ الحالة**
# من مواضعها القانونيّة في السجلّ نفسها التي يقرؤها gap_registry_measure.py — خليّةُ الحالة في جدولٍ بترويسة،
# وسطرُ ``- **الحالة:**`` تحت عنوانٍ غيرِ تاريخيّ — ثمّ يُقارَن الأساسُ بالرأس. صفٌّ صار fixed (أو سُجِّل fixed
# لأوّل مرّة) يشترط شيفرةً أو اختباراً خارج الدماغ في نطاق الـPR. **حدٌّ معلن:** الحارسُ يرى وجودَ دليلٍ تنفيذيّ
# في الـPR، لا أنّ ذلك الدليلَ يخصّ الفجوةَ نفسها — والربطُ بينهما يبقى للمراجعة.
REGISTRY = "sahool-brain/gaps/registry.md"


def _measure_module():
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import gap_registry_measure

    return gap_registry_measure


def fixed_gap_ids(text: str) -> set[str]:
    """معرّفاتُ الفجوات التي حالتُها ``fixed`` في مواضع الحالة القانونيّة (لا السرد، ولا المداخل التاريخيّة)."""
    g = _measure_module()
    out: set[str] = set()
    schema: list[str] | None = None
    heading: str | None = None
    role: str | None = None
    fence: str | None = None
    # كلُّ عنوانٍ بدوره النهائيّ، وكلُّ سطرِ حالةٍ fixed بعنوانه — يُحسم التاريخيّ بعد القراءة كاملةً.
    entries: list[list[str]] = []
    sections: list[int] = []
    lines = text.splitlines()
    for number, line in enumerate(lines, 1):
        fence_match = g.FENCE.match(line)
        if fence is not None:
            marker = fence_match.group("marker") if fence_match else ""
            if (
                fence_match
                and marker[0] == fence[0]
                and len(marker) >= len(fence)
                and not fence_match.group("tail").strip()
            ):
                fence = None
            continue
        if fence_match:
            fence, schema = fence_match.group("marker"), None
            continue
        if not line.startswith("|"):
            schema = None
        if re.match(r"^#{1,2}\s", line):
            heading, role = None, None
        found = g.HEADING.match(line)
        if found:
            heading, role = found.group("id"), "unreviewed"
            entries.append([heading, role])
            continue
        annotation = g.ANNOTATION.fullmatch(line.strip())
        if annotation and heading and role == "unreviewed":
            if annotation.group("role") in ("current", "historical"):
                role = annotation.group("role")
                entries[-1][1] = role
            continue
        if line.startswith("|"):
            cells = g.table_cells(line)
            if number < len(lines) and g.is_separator(lines[number]):
                schema = [cell.strip("* ").lower() for cell in cells]
                continue
            if g.is_separator(line) or not schema or not cells:
                continue
            label = g.LABEL.fullmatch(cells[0])
            columns = [
                i
                for i, name in enumerate(schema)
                if name == "status" or name in ("الحالة", "الحالة والدليل")
            ]
            if (
                not label
                or len(columns) != 1
                or schema[0] not in g.ID_HEADERS
                or len(cells) != len(schema)
            ):
                continue
            raw = cells[columns[0]]
            if not g.ANNOTATION.search(raw) and g.classify(raw)[0] == "fixed":
                out.add(label.group("id"))
            continue
        section = g.SECTION_STATE.match(line)
        if section and heading:
            raw = section.group("value")
            if not g.ANNOTATION.search(raw) and g.classify(raw)[0] == "fixed":
                sections.append(len(entries) - 1)
    # وسمُ ``historical`` لا يُسقط الحالةَ إلّا في سلسلةٍ مُراجَعة بقاعدة gap_registry_measure.measure() نفسها:
    # أكثرُ من مدخلٍ للمعرّف، مدخلٌ حاليٌّ واحد، والباقي كلُّه تاريخيّ. مدخلٌ منفردٌ موسومٌ تاريخيّاً
    # (أو سلسلةٌ بلا حاليّ) يبقى حالةً تُقرأ — وإلّا صار الوسمُ نفسُه طريقاً لتسجيل fixed في الدماغ وحده.
    roles: dict[str, Counter] = defaultdict(Counter)
    for gap_id, entry_role in entries:
        roles[gap_id][entry_role] += 1
    reviewed = {
        gap_id
        for gap_id, counts in roles.items()
        if sum(counts.values()) > 1
        and counts == Counter(current=1, historical=sum(counts.values()) - 1)
    }
    for index in sections:
        gap_id, entry_role = entries[index]
        if entry_role == "historical" and gap_id in reviewed:
            continue
        out.add(gap_id)
    return out


def fixed_transitions(base_text: str, head_text: str) -> list[str]:
    """ما صار fixed في الرأس ولم يكن fixed في الأساس (ومنه المسجَّلُ fixed لأوّل مرّة)."""
    return sorted(fixed_gap_ids(head_text) - fixed_gap_ids(base_text))


def check_fixed(paths: list[str], base_text: str, head_text: str) -> None:
    moved = fixed_transitions(base_text, head_text)
    if moved and not _has_executable_evidence(paths):
        raise SystemExit(
            "sahool-brain-only fixed transition rejected for "
            + ", ".join(moved)
            + "; fixed is declared in the PR that carries the fix (decisions/ledger.md, #1136) — "
            "include its executable code/test outside the brain knowledge base"
        )


def check(paths: list[str], diff: str) -> None:
    claims = [line for line in diff.splitlines() if _is_claim(line)]
    brain_changed = any(p.startswith("sahool-brain/") for p in paths)
    if brain_changed and claims and not _has_executable_evidence(paths):
        raise SystemExit(
            "sahool-brain-only closure/verification transition rejected; include executable code/test/evidence outside the brain knowledge base"
        )
    print("brain_state_transition_guard_ok")


# BRAIN-TRANSITION-GUARD-BLIND-TO-FIXED-01 (تصحيحٌ ثانٍ، 2026-10-05). ``git diff --name-only`` يُدرج الاسمَ الجديد
# لملفٍّ أُعيدت تسميتُه، فإعادةُ تسميةٍ صرفة (R100) لاختبارٍ قائم — أو نسخُه بلا تعديل (C100) — كانت تُحتسب دليلاً
# تنفيذيّاً وتُمرِّر انتقالاً إلى fixed لا يحمل سطراً جديداً. الدليلُ إذن **محتوى** لا اسم: يُقرأ ``--raw -M``
# (الحالةُ وبصمةُ الكائن الجديدة)، ويُسقَط كلُّ مسارٍ بصمتُه الجديدة موجودةٌ أصلاً في شجرة الأساس. القاعدةُ الواحدة
# تُسقط R100 وC100 (البصمةُ نفسُها بتعريف التشابه 100٪) ونسخاً لا يكتشفه ``-M`` فيصل ``A``، وتغييرَ صلاحيّاتٍ
# وحده — فلا فحصَ منفصلاً لدرجة التشابه: كان سيكون فرعاً ميتاً لا تقتله طفرة. **حدٌّ معلن:** تعديلٌ تافه يبقى
# محتوىً جديداً — الحارسُ يرى أنّ في الـPR محتوىً تنفيذيّاً جديداً، لا أنّه يُصلح الفجوة.


def parse_raw(raw: str) -> list[tuple[str, str, str]]:
    """``git diff --raw -z --no-abbrev`` ⇒ ``[(status, dst_blob, path)]`` (للمُعاد تسميتُه والمنسوخ: الاسمُ الجديد)."""
    fields = raw.split("\0")
    out: list[tuple[str, str, str]] = []
    i = 0
    while i < len(fields) and fields[i].startswith(":"):
        meta = fields[i][1:].split()
        status, dst_blob = meta[4], meta[3]
        two_paths = status[:1] in ("R", "C")
        path = fields[i + 2] if two_paths else fields[i + 1]
        out.append((status, dst_blob, path))
        i += 3 if two_paths else 2
    return out


def content_evidence(entries: list[tuple[str, str, str]], base_blobs: set[str]) -> list[str]:
    """المساراتُ التي تحمل محتوىً لم يكن في الأساس — المرشّحةُ وحدها دليلاً تنفيذيّاً."""
    return [path for _status, blob, path in entries if blob not in base_blobs]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base")
    p.add_argument("--head", default="HEAD")
    a = p.parse_args()
    base = subprocess.run(
        ["git", "merge-base", a.base, a.head],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    # ``--diff-filter=d`` يُسقط الملفّاتِ المحذوفة: حذفُ اختبارٍ ليس دليلاً تنفيذيّاً على إصلاح، وإلّا كفى
    # حذفُ أيّ ملفٍّ تحت ``tests_v9/`` لتمرير انتقالٍ إلى fixed. والحذفُ لا يُضيف سطراً ولا حالةً يُفحصان.
    raw_format = ["--raw", "-z", "-M", "--no-abbrev"]
    entries = parse_raw(
        subprocess.run(
            ["git", "diff", *raw_format, "--diff-filter=d", f"{a.base}...{a.head}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
    )
    names = [path for _, _, path in entries]
    base_blobs = {
        line.split()[2]
        for line in subprocess.run(
            ["git", "ls-tree", "-r", base],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.splitlines()
        if line
    }
    evidence = content_evidence(entries, base_blobs)
    diff = subprocess.run(
        ["git", "diff", "--unified=0", f"{a.base}...{a.head}", "--", "sahool-brain/"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if REGISTRY in names:
        texts = [
            subprocess.run(
                ["git", "show", f"{ref}:{REGISTRY}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout
            for ref in (base, a.head)
        ]
        check_fixed(evidence, *texts)
    check(evidence, diff)


if __name__ == "__main__":
    main()
