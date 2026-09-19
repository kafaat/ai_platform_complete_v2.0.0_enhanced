#!/usr/bin/env python3
"""Measure gap-registry state/identity structure without rewriting historical data."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "sahool-brain/gaps/registry.md"
ID = r"(?:[A-Z][A-Za-z0-9_.]*(?:-[A-Za-z0-9_.]+)+|[A-Z][A-Z0-9_.]*)"
LABEL = re.compile(rf"^(?P<id>{ID})(?P<label_suffix>(?:\s+.*)?)$")
HEADING = re.compile(rf"^##\s+(?P<id>{ID})(?=\s|$)")
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
    non_state_table_rows = []
    table_errors = []
    annotation_errors = []
    unscoped_states = []
    current_heading: dict | None = None
    schema: list[str] | None = None
    schema_line: int | None = None
    fence: str | None = None
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
        if not line.startswith("|"):
            schema = None
            schema_line = None
        if re.match(r"^#{1,2}\s", line):
            current_heading = None
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
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("path", nargs="?", default=str(REGISTRY))
    args = parser.parse_args()
    report = measure(Path(args.path).read_text(encoding="utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
