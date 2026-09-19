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
ID = r"[A-Z][A-Z0-9_.]*(?:-[A-Z0-9_.]+)+"
ROW = re.compile(rf"^\|\s*(?P<id>{ID})(?P<label_suffix>[^|]*)\|(?P<rest>.*)$")
HEADING = re.compile(rf"^##\s+(?P<id>{ID})\b")
SECTION_STATE = re.compile(r"^-\s*\*\*(?:الحالة|status)\s*:\*\*\s*(?P<value>.+?)\s*$", re.I)
CANON = ("open", "fixed", "verified")


def classify(raw: str) -> tuple[str | None, str]:
    s = raw.strip().lower()
    match = re.match(r"^\*{0,2}(open|fixed|verified)\b(?P<q>.*)$", s, re.I)
    if match:
        return match.group(1).lower(), match.group("q").strip(" *—–-·:()")
    return None, s


def measure(text: str) -> dict:
    rows = []
    headings = []
    section_states = []
    current_heading_id: str | None = None
    for number, line in enumerate(text.splitlines(), 1):
        row = ROW.match(line)
        if row:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            raw = cells[-1] if len(cells) > 1 else ""
            state, qualifier = classify(raw.strip("* "))
            rows.append(
                {
                    "id": row.group("id"),
                    "line": number,
                    "label_suffix": row.group("label_suffix").strip(),
                    "raw_state": raw,
                    "state": state,
                    "qualifier": qualifier,
                }
            )
        heading = HEADING.match(line)
        if heading:
            current_heading_id = heading.group("id")
            headings.append({"id": current_heading_id, "line": number})
        section = SECTION_STATE.match(line)
        if section:
            state, qualifier = classify(section.group("value"))
            section_states.append(
                {
                    "id": current_heading_id,
                    "line": number,
                    "raw_state": section.group("value"),
                    "state": state,
                    "qualifier": qualifier,
                }
            )

    by_id: dict[str, list[int]] = defaultdict(list)
    for heading in headings:
        by_id[heading["id"]].append(heading["line"])
    duplicates = {gap_id: lines for gap_id, lines in by_id.items() if len(lines) > 1}

    states_by_id: dict[str, list[dict]] = defaultdict(list)
    for item in section_states:
        if item["id"] is not None:
            states_by_id[item["id"]].append(item)
    contradictions = {}
    for gap_id, items in states_by_id.items():
        known = {item["state"] for item in items if item["state"] is not None}
        if len(known) > 1:
            contradictions[gap_id] = items

    counts = Counter(row["state"] or "unclassified" for row in rows)
    return {
        "row_count": len(rows),
        "heading_count": len(headings),
        "row_state_counts": dict(sorted(counts.items())),
        "unclassified_rows": [row for row in rows if row["state"] is None],
        "duplicate_heading_ids": duplicates,
        "duplicate_heading_id_count": len(duplicates),
        "contradictory_sections": contradictions,
        "contradictory_section_id_count": len(contradictions),
        "section_state_count": len(section_states),
        "unclassified_section_states": [
            state for state in section_states if state["state"] is None
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
