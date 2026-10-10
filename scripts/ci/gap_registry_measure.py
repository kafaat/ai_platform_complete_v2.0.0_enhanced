#!/usr/bin/env python3
"""Measure gap-registry state/identity structure without rewriting historical data."""

from __future__ import annotations

import argparse
import bisect
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا السكربت عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نتيجته (UnicodeEncodeError) ⇒ خروجٌ بغير صفر يُقرَأ حجباً وهو قد مرّ.
# **عند التحميل لا داخل `main()`** — بعضُ المخرَج يُطبَع من جسد الوحدة قبل أيّ نداء.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "sahool-brain/gaps/registry.md"
ID = r"(?:[A-Z][A-Za-z0-9_.]*(?:-[A-Za-z0-9_.]+)+|[A-Z][A-Z0-9_.]*)"
LABEL = re.compile(rf"^(?P<id>{ID})(?P<label_suffix>(?:\s+.*)?)$")
HEADING = re.compile(rf"^##\s+(?P<id>{ID})(?=\s|$)")
# ── `A-GAP-UNDER-A-DEEPER-HEADING-IS-INVISIBLE-TO-ITS-OWN-RATCHET-01` ───────────
#
# `HEADING` يقرأ `^##` وحدَه، ولا شيءَ كان يقرأ ما تحته. فمدخلةُ فجوةٍ تُكتب
# `### <معرِّف>` **لا تدخل `heading_count` أصلاً**، فلا تصير يتيمةً، فلا يراها راتشِتُ
# اليتامى الذي وُجِد ليمسك هذا الصنفَ بعينه. مقيسٌ على `a0bba343` (دمج #1036):
# `V25-AI-RUNTIME-LOCAL-ACCEPTANCE-01` مفتوحةٌ في الملفّ ولا تظهر في **أيّ** عدّ —
# لا heading ولا section_state ولا صفّ ولا شذوذ — و«Gap registry measurement» خضراء.
# أخضرُ عن سؤالٍ لم يُطرَح: نفسُ عقدِ `GAP-HEADING-WITHOUT-A-STATE-RECORD-IS-INVISIBLE-01`
# في مستوى العنوان بدل سطر الحالة.
#
# **والشكلُ المقبول هنا أضيقُ من `ID` عمداً، والفرقُ مقيس.** `ID` يقبل كلمةً كبيرةً
# مفردة (`HIL` · `MCP`)، وفي هذا السجلّ عنوانان بهذا الشكل (`### HIL SQL follow-up`
# و`### MCP review follow-up`) **ليسا مدخلَي فجوة** بل عنوانا قسمٍ فوق جدولٍ تُقرأ
# صفوفُه أصلاً. فقبولُهما يجعل الحقلَ يُبلِّغ عمّا لا عطلَ فيه، وحقلٌ يُحمِّر على عملٍ
# طبيعيّ يُطفَأ. المطلوبُ **الشكلُ الموصول بشَرطة** وحدَه، والمقيسُ بعده: **حالةٌ واحدة**.
DEEP_HEADING = re.compile(
    r"^(?P<hashes>#{3,6})\s+(?P<id>[A-Z][A-Za-z0-9_.]*(?:-[A-Za-z0-9_.]+)+)(?=\s|$)"
)
SECTION_STATE = re.compile(r"^-\s*\*\*(?:الحالة|status)\s*:\*\*\s*(?P<value>.+?)\s*$", re.I)
CANON = ("open", "fixed", "verified")
ANNOTATION = re.compile(r"<!--\s*gap-registry:\s*(?P<role>[\w-]+)\s*-->")
NON_STATE_KINDS = ("alias", "policy", "adjudicated")
ID_HEADERS = {"id", "gap", "الهوية", "المعرّف", "المعرف", "المجموعة"}
FENCE = re.compile(r"^\s{0,3}(?P<marker>`{3,}|~{3,})(?P<tail>.*)$")


def classify(raw: str) -> tuple[str | None, str]:
    s = raw.strip().lstrip("*` ")
    match = re.match(r"^(open|fixed|verified)\b(?P<q>.*)$", s, re.I)
    if match:
        return match.group(1).lower(), match.group("q").strip(" *`—–-·:()")
    return None, s


def table_cells(line: str) -> list[str]:
    """Keep escaped pipes and pipes inside matched code spans in their cell."""
    cells: list[str] = []
    part: list[str] = []
    index = 0
    while index < len(line):
        char = line[index]
        if char == "\\" and index + 1 < len(line):
            part.append(line[index : index + 2])
            index += 2
            continue
        if char == "`":
            end = index
            while end < len(line) and line[end] == "`":
                end += 1
            marker = line[index:end]
            closing = re.search(rf"(?<!`){re.escape(marker)}(?!`)", line[end:])
            if closing:
                stop = end + closing.end()
                part.append(line[index:stop])
                index = stop
                continue
            part.append(marker)
            index = end
            continue
        if char == "|":
            cells.append("".join(part).strip())
            part = []
        else:
            part.append(char)
        index += 1
    cells.append("".join(part).strip())
    if line.lstrip().startswith("|"):
        cells = cells[1:]
    if line.rstrip().endswith("|") and cells and not cells[-1]:
        cells = cells[:-1]
    return cells


def is_separator(line: str) -> bool:
    cells = table_cells(line)
    return len(cells) > 1 and all(re.fullmatch(r":?-+:?", cell) for cell in cells)


def measure(text: str) -> dict:
    rows = []
    headings = []
    section_states = []
    noncanonical_headings: list[dict[str, object]] = []
    non_state_table_rows = []
    table_errors = []
    annotation_errors = []
    unscoped_states = []
    current_heading: dict | None = None
    schema: list[str] | None = None
    schema_line: int | None = None
    fence: str | None = None
    # مواضعُ تقرؤها ``fixed_provenance`` بالقاعدة نفسها: ما داخل سياجٍ مثالٌ لا سجلّ.
    unfenced: set[int] = set()
    section_ends: list[int] = []
    lines = text.splitlines()
    for number, line in enumerate(lines, 1):
        fence_match = FENCE.match(line)
        if fence is not None:
            if (
                fence_match
                and fence_match.group("marker")[0] == fence[0]
                and len(fence_match.group("marker")) >= len(fence)
                and not fence_match.group("tail").strip()
            ):
                fence = None
            continue
        if fence_match:
            fence = fence_match.group("marker")
            schema = None
            continue
        unfenced.add(number)
        if not line.startswith("|"):
            schema = None
            schema_line = None
        if re.match(r"^#{1,2}\s", line):
            current_heading = None
            section_ends.append(number)
        deep = DEEP_HEADING.match(line)
        if deep:
            noncanonical_headings.append(
                {
                    "id": deep.group("id"),
                    "line": number,
                    "level": len(deep.group("hashes")),
                }
            )
        heading = HEADING.match(line)
        if heading:
            current_heading = {
                "id": heading.group("id"),
                "line": number,
                "entry_role": "unreviewed",
            }
            headings.append(current_heading)
        annotation = ANNOTATION.fullmatch(line.strip())
        if annotation:
            role = annotation.group("role")
            if (
                current_heading is not None
                and number == current_heading["line"] + 1
                and role in ("current", "historical")
                and current_heading["entry_role"] == "unreviewed"
            ):
                current_heading["entry_role"] = role
            else:
                annotation_errors.append({"line": number, "role": role})

        if line.startswith("|"):
            cells = table_cells(line)
            if number < len(lines) and is_separator(lines[number]):
                schema = [cell.strip("* ").lower() for cell in cells]
                schema_line = number
                continue
            if is_separator(line):
                continue
            label = LABEL.fullmatch(cells[0]) if cells else None
            if label:
                item = {
                    "id": label.group("id"),
                    "line": number,
                    "label_suffix": label.group("label_suffix").strip(),
                }
                status_columns = (
                    [
                        i
                        for i, name in enumerate(schema)
                        if name == "status" or name in ("الحالة", "الحالة والدليل")
                    ]
                    if schema
                    else []
                )
                if schema and (not status_columns or schema[0] not in ID_HEADERS):
                    non_state_table_rows.append({**item, "header": schema})
                    continue
                if schema is None or len(status_columns) != 1 or len(cells) != len(schema):
                    reason = "missing_table_header" if schema is None else "invalid_table_shape"
                    table_errors.append(
                        {
                            **item,
                            "reason": reason,
                            "header_line": schema_line,
                            "expected_columns": len(schema) if schema else None,
                            "actual_columns": len(cells),
                        }
                    )
                    rows.append(
                        {
                            **item,
                            "kind": "gap",
                            "raw_state": "",
                            "state": None,
                            "qualifier": "",
                            "reason": reason,
                        }
                    )
                    continue
                raw = cells[status_columns[0]]
                annotations = ANNOTATION.findall(raw)
                kind = "gap"
                if annotations:
                    if len(annotations) == 1 and annotations[0] in NON_STATE_KINDS:
                        kind = annotations[0]
                    else:
                        annotation_errors.append({"line": number, "roles": annotations})
                state, qualifier = classify(ANNOTATION.sub("", raw))
                rows.append(
                    {
                        **item,
                        "kind": kind,
                        "raw_state": raw,
                        "state": state if kind == "gap" else None,
                        "qualifier": qualifier,
                    }
                )
        section = SECTION_STATE.match(line)
        if section:
            raw = section.group("value")
            annotations = ANNOTATION.findall(raw)
            kind = "gap"
            if annotations:
                if len(annotations) == 1 and annotations[0] in NON_STATE_KINDS:
                    kind = annotations[0]
                else:
                    annotation_errors.append({"line": number, "roles": annotations})
            state, qualifier = classify(ANNOTATION.sub("", raw))
            item = {
                "id": current_heading["id"] if current_heading else None,
                "heading_line": current_heading["line"] if current_heading else None,
                "entry_role": current_heading["entry_role"] if current_heading else None,
                "line": number,
                "kind": kind,
                "raw_state": raw,
                "state": state if kind == "gap" else None,
                "qualifier": qualifier,
            }
            (section_states if current_heading else unscoped_states).append(item)

    by_id: dict[str, list[dict]] = defaultdict(list)
    for heading in headings:
        by_id[heading["id"]].append(heading)
    duplicates = {
        gap_id: [item["line"] for item in items]
        for gap_id, items in by_id.items()
        if len(items) > 1
    }
    reviewed = {
        gap_id: items
        for gap_id, items in by_id.items()
        if len(items) > 1
        and Counter(item["entry_role"] for item in items)
        == {"current": 1, "historical": len(items) - 1}
    }

    states_by_id: dict[str, list[dict]] = defaultdict(list)
    for item in section_states:
        states_by_id[item["id"]].append(item)
    contradictions = {}
    historical_variations = {}
    for gap_id, items in states_by_id.items():
        # Historical text stays visible. Only an explicitly reviewed sequence can
        # separate its historical state from the current record.
        active = (
            [item for item in items if item["entry_role"] != "historical"]
            if gap_id in reviewed
            else items
        )
        known = {item["state"] for item in active if item["state"] is not None}
        if len(known) > 1:
            contradictions[gap_id] = active
        elif len({item["state"] for item in items if item["state"] is not None}) > 1:
            historical_variations[gap_id] = items

    gap_rows = [row for row in rows if row["kind"] == "gap"]
    non_state_rows = [row for row in rows if row["kind"] != "gap"]
    counts = Counter(row["state"] or "unclassified" for row in gap_rows)

    # ── `GAP-HEADING-WITHOUT-A-STATE-RECORD-IS-INVISIBLE-01` ────────────────────
    #
    # **العطلُ مقيسٌ على مصنوعَتَي تشغيلٍ حقيقيَّتين، لا مفترَض.** أُضيف عنوانُ فجوةٍ
    # جديد بصيغة `## <معرِّف> — مفتوحة (…)` — الحالةُ **عربيّةٌ في العنوان**. فارتفع
    # `heading_count` (٢٦٣ ⇒ ٢٦٤) وبقي `section_state_count` عند ٤٢، و
    # `unclassified_section_states` **فارغاً**. أي أنّ الفجوةَ لم تظهر `open` ولا حتّى
    # `unclassified`: **اختفت من كلّ عدٍّ يُقرأ، والقياسُ أخضر**.
    #
    # **والسببُ بنيويّ لا إملائيّ:** `unclassified_*` تصف ما **رآه** القارئ ولم يفهمه.
    # وما لم يُرَ أصلاً لا يقع في أيّ منها — فكلُّ حقول الشذوذ القائمة كانت عمياءَ عنه
    # بالتصميم. هذا الحقلُ يسدّ الفرق: عنوانٌ **يحمل معرِّفاً** ولا يقابله سجلُّ حالة،
    # لا في قسمٍ (`- **الحالة:**`) ولا في صفِّ جدول.
    #
    # **والعددُ المقيس ٢١٢ من ٢٦٤ — فهو ليس صفراً يُفرَض بل أساسٌ يُخفَّض.** أكثرُ
    # عناوين هذا السجلّ سردٌ تاريخيّ لا مدخلُ حالة، فحقلٌ يُحمِّر على الكلّ يُطفَأ
    # في أوّل أسبوع. والراتشِتُ في `docs/architecture/gap_heading_state_baseline.json`
    # يمنع **النموّ** ولا يدّعي أنّ ما فيه سليم — نفسُ عقد `fake_connection_debt`.
    # ``BRAIN-FIXED-PROVENANCE-NOT-RECONCILED-WITH-MERGE-01``: سجلّاتُ fixed الحاليّة وسطورُ
    # ``canonical`` في أقسامها — يقرؤها ``fixed_provenance``. **وبقواعد هذه الدالّة نفسها**
    # (مراجعةُ Copilot على #1150): حدُّ القسم عنوانٌ **خارج سياج**، وسطرُ canonical خارج سياج —
    # وإلّا قطع `## مثال` مُسيَّجٌ القسمَ قبل ربطٍ حقيقيّ، أو ستر سطرٌ مُسيَّجٌ غيابَ الربط. والتاريخيُّ
    # لا يُسقَط إلّا في سلسلةٍ مُراجَعة (``reviewed``)، كقاعدة الحالة أعلاه حرفاً — مدخلٌ تاريخيٌّ
    # منفرد يبقى فعّالاً، فلا يكون الوسمُ طريقاً لإخفاء SHA غيرِ مُصالَح.
    def _canonical(begin: int, end: int) -> list[str]:
        return [
            lines[n - 1]
            for n in range(begin, end + 1)
            if n in unfenced and CANONICAL_LINE.match(lines[n - 1])
        ]

    def _section_end(begin: int) -> int:
        return next((n - 1 for n in section_ends if n > begin), len(lines))

    fixed_spans = [
        {"id": row["id"], "line": row["line"], "status": row["raw_state"], "canonical": []}
        for row in gap_rows
        if row["state"] == "fixed"
    ] + [
        {
            "id": item["id"],
            "line": item["line"],
            "status": item["raw_state"],
            "canonical": _canonical(item["heading_line"], _section_end(item["heading_line"])),
        }
        for item in section_states
        if item["kind"] == "gap"
        and item["state"] == "fixed"
        and not (item["entry_role"] == "historical" and item["id"] in reviewed)
    ]
    stated_ids = {item["id"] for item in section_states}
    row_ids = {row["id"] for row in rows if row.get("id")}
    unresolved_aliases = resolve_aliases(rows, section_states, headings)
    orphans = [
        {"id": heading["id"], "line": heading["line"]}
        for heading in headings
        if heading["id"] not in stated_ids and heading["id"] not in row_ids
    ]
    return {
        "schema_version": 2,
        "row_count": len(rows),
        "gap_row_count": len(gap_rows),
        "non_state_rows": non_state_rows,
        "non_state_row_counts": dict(
            sorted(Counter(row["kind"] for row in non_state_rows).items())
        ),
        "non_state_table_rows": non_state_table_rows,
        "table_structure_errors": table_errors,
        "annotation_errors": annotation_errors,
        "heading_count": len(headings),
        "row_state_counts": dict(sorted(counts.items())),
        "unclassified_rows": [row for row in gap_rows if row["state"] is None],
        "duplicate_heading_ids": duplicates,
        "duplicate_heading_id_count": len(duplicates),
        "reviewed_heading_sequences": reviewed,
        "unreviewed_duplicate_heading_ids": {
            gap_id: at for gap_id, at in duplicates.items() if gap_id not in reviewed
        },
        "contradictory_sections": contradictions,
        "contradictory_section_id_count": len(contradictions),
        "historical_state_variations": historical_variations,
        "section_state_count": len(section_states),
        "unscoped_section_states": unscoped_states,
        "non_state_section_states": [state for state in section_states if state["kind"] != "gap"],
        "unclassified_section_states": [
            state for state in section_states if state["kind"] == "gap" and state["state"] is None
        ],
        # يُصدَّران معاً عمداً: العددُ وحدَه يُقارَن بالأساس، والقائمةُ هي ما يجعل
        # الفارقَ قابلاً للتشخيص بدل أن يكون رقماً يرتفع بلا اسم.
        "orphan_gap_headings": orphans,
        "orphan_gap_heading_count": len(orphans),
        # القائمةُ مع العدد، كما في اليتامى: عددٌ بلا أسماء يرتفع بلا تشخيص.
        "noncanonical_heading_levels": noncanonical_headings,
        "noncanonical_heading_level_count": len(noncanonical_headings),
        "unresolved_aliases": unresolved_aliases,
        "fixed_records": fixed_spans,
    }


#: هدفُ اللقب: أوّلُ ``code span`` بشكل معرِّف في نصّ حالته بعد الوسم — وهو ما يكتبه
#: المدخلان القائمان (``**alias → `SAHOOL-AI-RAG-LIVE-001`**`` و``لقبٌ (alias) للهويّة
#: القانونيّة `SEC-QDRANT-AUTH-FAIL-CLOSED-01```)، و``alias_of: `X``` يستوفيه إن كُتِب أوّلاً.
ALIAS_TARGET = re.compile(rf"`(?P<target>{ID})`")


def resolve_aliases(rows: list[dict], section_states: list[dict], headings: list[dict]) -> list:
    """لقبٌ لا يُحَلّ إلى هويّةٍ قانونيّة ⇒ سطرٌ في القائمة، بسببه.

    ``BRAIN-HISTORICAL-GAP-ID-ALIAS-01``: وسمُ ``alias`` **يُخرِج المدخلَ من كلّ عدّ
    حالة** (``kind != "gap"``)، وهدفُه كان نثراً لا يقرؤه شيء. مقيسٌ على السجلّ الحيّ:
    صفٌّ ``open`` يُوسَم ``alias`` نحو معرِّفٍ لا وجود له ⇒ ``open`` ينزل ٧٣ ⇒ ٧٢ ولا
    حارسَ يحمرّ — فالوسمُ طريقٌ لإخفاء فجوةٍ مفتوحةٍ بلا ثمن. والحلُّ **قفزةٌ واحدة إلى
    هويّةٍ مُسجَّلة ليست لقباً**: لا هدف · هدفٌ هو نفسُه · هدفٌ غيرُ مسجَّل · هدفٌ لقبٌ
    بدوره (سلسلةٌ تُخفي أين تعيش الحالة).
    """
    alias_ids = {e["id"] for e in rows + section_states if e.get("kind") == "alias"}
    registered = {h["id"] for h in headings} | {
        r["id"] for r in rows if r.get("id") and r.get("kind") != "alias"
    }
    out: list[dict] = []
    for entry in [*rows, *section_states]:
        if entry.get("kind") != "alias":
            continue
        match = ALIAS_TARGET.search(ANNOTATION.sub("", entry.get("raw_state", "")))
        target = match.group("target") if match else None
        if target is None:
            reason = "no_target"
        elif target == entry["id"]:
            reason = "self"
        elif target in alias_ids:
            reason = "target_is_alias"
        elif target not in registered:
            reason = "target_not_registered"
        else:
            continue
        out.append({"id": entry["id"], "line": entry["line"], "alias_of": target, "reason": reason})
    return out


# ── `BRAIN-FIXED-PROVENANCE-NOT-RECONCILED-WITH-MERGE-01` ──────────────────────
#
# الدمجُ هنا squash: فـSHA الإصلاح الذي يذكره صفُّ fixed يعيش في فرع الـPR وحده، وبعد الدمج
# **ليس سلفاً لـ`main`** (مقيس: `git merge-base --is-ancestor` سالبٌ لـ`49bc30ee` · `da920253` ·
# `3bd8641b` على `9801d076`، ولـ`0726a887` على `ab07ceb8`). فالصفُّ صادقٌ زمنَ كتابته ويشير إلى
# commit لا تحمله `main`، ووظيفةُ القياس كانت خضراءَ على كلّ مَظهرٍ له.
#
# **العيبُ المقيس:** سجلُّ fixed تذكر حالتُه SHA لا يُبلَغ من HEAD، **ولا يحمل موضعُ الربط أيَّ
# SHA يُبلَغ** — أي لا ربطَ بأيّ commit على `main`. والعلاجُ إلحاقُ commit الدمج، لا استبدالُ الأصل.
#
# **وموضعُ الربط محدَّد، لا المدخلُ كلُّه — مقيسٌ:** صفُّ #1149 يذكر في خليّة الوصف `main@c56db557`
# (القاعدةَ التي قيس عليها العطل)، وهي تُبلَغ؛ فلو عُدّ أيُّ SHA في المدخل ربطاً لستر الصفَّ الذي
# وُجِد القياسُ لأجله. الموضعُ: نصُّ الحالة نفسُه (خليّةُ الحالة / سطرُ `- **الحالة:**`)، وسطرُ
# `- **canonical …:**` في القسم — الاصطلاحُ الذي كتبت به المطابقاتُ اليدويّة الأربعَ عشرة.
#
# **و`#N` في الحالة تلميحٌ لا حكم — مقيسٌ لا مفترَض.** على `ab07ceb8` سبعةُ سجلّاتٍ تذكر PR؛ وفي
# ثلاثةٍ منها الـSHA المُصلِح من PR **آخر** (`4634ef15` ∈ #1110 والصفّ يذكر #1031 · `0a6f2988` ∈
# #1112 والصفّ يذكر #993 · `fd850a06` ∈ #987 والصفّ يذكر #988) لأنّ الـPR المذكورَ موضعُ القياس لا
# الإصلاح. فلو طُلب «commit دمج الـPR المذكور» لدُفع القارئُ إلى ربطٍ خاطئ. لذا ``cited_pr_merges``
# يُعرَض للقارئ ولا يدخل الحكم، والربطُ الصحيح يُستخرج من الـSHA نفسه (`commits/{sha}/pulls`).
#
# **حدٌّ مُعلَن:** أيُّ SHA يُبلَغ **داخل مقطع canonical** يُعَدّ ربطاً — القياسُ يرى **غيابَ** الربط
# لا صحّتَه. و`GAP-REGISTRY-MEASURE-REACHABLE-SHA-IN-STATUS-PROSE-MASKS-UNRECONCILED-FIXED-01` (مقيسٌ على
# `main@c1760e9e`): نثرُ خليّة الحالة نفسِها قد يذكر SHA مبلوغاً (`main@94e6e07a` أساسَ مقارنةٍ بصريّة)
# فستر إصلاحين مُسحَقين (`71191cd5` · `90b8c697`)؛ لذا يُقرأ الربطُ من مقاطع `**canonical …:**` وحدها
# — داخل الخليّة (حتّى الفاصل ` · **` التالي أو نهايتها) أو سطراً `- **canonical …:**` في القسم — ولا
# يُقرأ SHA الإصلاح إلّا من النثر خارجها.
#
# **والقياسُ يحتاج التاريخ:** على استنساخٍ ضحل كلُّ SHA «لا يُبلَغ»، فيصير كلُّ صفّ fixed عيباً
# كاذباً. لذا ``provenance_measured`` يُعلَن، والحقلُ ``None`` حين لا يُقاس — صمتٌ مُعلَن بسببه.
# حدُّ الكلمة الكامل (لا حدُّ hex) كي لا يُقرأ «feedback» SHA؛ وحرفٌ واحدٌ a-f على الأقلّ كي لا
# تُقرأ التواريخُ (`20260626`) ومعرّفاتُ وظائف CI (`2412021383`) — مقيسٌ: كانت ٧ من ٤٦ كاذبة.
STATUS_SHA = re.compile(r"(?<![0-9A-Za-z_])(?=[0-9]*[a-f])([0-9a-f]{7,40})(?![0-9A-Za-z_])")
STATUS_PR = re.compile(r"(?<![\w/&])#(\d{2,6})(?!\d)")
SQUASH_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")
CANONICAL_LINE = re.compile(r"^\s*-\s*\*\*canonical\b", re.I)
CANONICAL_INLINE = re.compile(r"(?:^|(?<= · ))\*\*canonical\b[^*\n]*:\*\*", re.I)
INLINE_ITEM_SEPARATOR = " · **"


#: بصمةُ محتوى (``sha256:a4938f37…`` لصورة MinIO) ليست commit — مراجعةُ Copilot على #1150: كانت
#: تُدرج `MINIO-IMAGES-DELETED-FROM-DOCKER-HUB-01` بين غير المُصالَحة كذباً.
DIGEST = re.compile(r"(?<![0-9A-Za-z_])[a-z][a-z0-9]*:[0-9a-f]{7,}…?")


def _shas(text: str) -> list[str]:
    # داخل ``code span`` وحده: النثرُ العربيّ لا يحمل hex، لكنّ المعرّفاتِ والأرقامَ قد تُشبهه.
    return [
        m
        for span in re.findall(r"`([^`]+)`", text)
        for m in STATUS_SHA.findall(DIGEST.sub(" ", span))
    ]


def _split_inline_canonical(status: str) -> tuple[str, list[str]]:
    """نثرُ الخليّة بلا مقاطع canonical، ومقاطعُ canonical وحدها (كلٌّ حتّى الفاصل ` · **` التالي).

    لا تُعامل إشارةٌ وسط النثر إلى صياغة canonical بوصفها وصلةً؛ يجب أن تبدأ عند حدّ
    عنصرٍ داخليّ وأن تُغلق بعلامة ``:**``.
    """
    prose: list[str] = []
    segments: list[str] = []
    cursor = 0
    for marker in CANONICAL_INLINE.finditer(status):
        if marker.start() < cursor:
            continue
        prose.append(status[cursor : marker.start()])
        end = status.find(INLINE_ITEM_SEPARATOR, marker.end())
        end = len(status) if end < 0 else end
        segments.append(status[marker.start() : end])
        cursor = end
    prose.append(status[cursor:])
    return "".join(prose), segments


def fixed_provenance(text: str, records: list[dict], merges: dict[int, str], reachable) -> list:
    """``merges``: رقمُ PR ⇒ SHA دمجه الكامل على HEAD. ``reachable(sha)``: هل يُبلَغ من HEAD."""
    del text  # السجلّاتُ تحمل سطورَ canonical مقروءةً بقواعد ``measure()`` (السياج)
    out: list[dict] = []
    for record in records:
        status = ANNOTATION.sub("", record["status"])
        prose, inline_links = _split_inline_canonical(status)
        repair = [sha for sha in _shas(prose) if not reachable(sha)]
        if not repair:
            continue
        links = [*inline_links, *record["canonical"]]
        if any(reachable(sha) for sha in _shas("\n".join(links))):
            continue
        prs = sorted({int(n) for n in STATUS_PR.findall(status)})
        out.append(
            {
                "id": record["id"],
                "line": record["line"],
                "repair_shas": repair,
                "cited_pr_merges": {str(pr): merges[pr] for pr in prs if pr in merges},
            }
        )
    return out


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout


def git_history(root: Path) -> tuple[dict[int, str], list[str]] | str:
    """(دمجات الـPR على السلسلة الأولى، كلُّ SHA يُبلَغ من HEAD) — أو سببُ عدم القياس."""
    try:
        if _git(root, "rev-parse", "--is-shallow-repository").strip() == "true":
            return "shallow_clone"
        merges: dict[int, str] = {}
        for line in _git(root, "log", "--first-parent", "--format=%H%x00%s", "HEAD").splitlines():
            sha, _, subject = line.partition("\0")
            match = SQUASH_SUBJECT.search(subject)
            if match:
                merges.setdefault(int(match.group(1)), sha)
        return merges, sorted(_git(root, "rev-list", "HEAD").split())
    except (OSError, subprocess.CalledProcessError):
        return "no_git_history"


def _prefix_lookup(all_shas: list[str]):
    def reachable(sha: str) -> bool:
        index = bisect.bisect_left(all_shas, sha.lower())
        return index < len(all_shas) and all_shas[index].startswith(sha.lower())

    return reachable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("path", nargs="?", default=str(REGISTRY))
    args = parser.parse_args()
    path = Path(args.path)
    text = path.read_text(encoding="utf-8")
    report = measure(text)
    history = git_history(path.resolve().parent)
    if isinstance(history, str):
        report["provenance_measured"] = False
        report["provenance_unmeasured_reason"] = history
        report["unreconciled_fixed_provenance"] = None
        report["unreconciled_fixed_provenance_count"] = None
    else:
        merges, all_shas = history
        found = fixed_provenance(text, report["fixed_records"], merges, _prefix_lookup(all_shas))
        report["provenance_measured"] = True
        report["unreconciled_fixed_provenance"] = found
        report["unreconciled_fixed_provenance_count"] = len(found)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
