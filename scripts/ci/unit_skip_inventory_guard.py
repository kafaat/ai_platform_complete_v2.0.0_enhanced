#!/usr/bin/env python3
"""Every skip report in the Unit Tests job is a declared, named debt, never a silent one.

S1 F3 (`OFFICE-20261110:F3` on #1369): the hospital's S1 measurement of the unit suite gave
13,139 reports, 0 failures and 24 skips, verdict `INCONCLUSIVE / TESTS_SKIPPED`. Nothing in
the repository listed those 24, so nobody could tell a known, costed gap from a test that
stopped running yesterday. A skip is one line at the end of thousands of dots; the job stays
green either way.

This guard reads the JUnit XML that the two unit stages write and compares each skip report,
by node id *and* reason, with ``docs/testing/unit_skip_inventory.json``:

* a skip that is not declared                      -> BLOCKED (a new dormant test)
* a declared skip whose reason changed            -> BLOCKED (the cause moved; re-decide it)
* a declared skip that no longer occurs            -> BLOCKED (stale entry; delete it, the
                                                       inventory only shrinks)
* a declared skip reported in a different stage    -> BLOCKED (the same test, another gate)

What it does **not** do: it never turns a skip into a pass. Every entry carries
``status: "open"`` unless the owner records a named exception (``status: "exception"`` with
``decision``); S1 stays INCONCLUSIVE while any open entry exists. The guard only makes the
list exact, so it can shrink honestly.

    python scripts/ci/unit_skip_inventory_guard.py --junit parallel=unit-par.xml \\
        --junit tree_writer=unit-tw.xml
Exit 0 when the reports equal the inventory, 1 on any difference, 2 on unreadable input.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/testing/unit_skip_inventory.json"
STATUSES = {"open", "exception"}
CLASSIFICATIONS = {"unit", "integration", "optional-profile", "obsolete-or-inapplicable"}
REQUIRED_FIELDS = ("stage", "nodeid", "reason", "classification", "required_gate", "status")


class InventoryError(Exception):
    pass


def node_id(case: ET.Element) -> str:
    """pytest's node id from a JUnit testcase (``classname`` dotted, ``name`` the leaf)."""
    classname = case.get("classname", "")
    name = case.get("name", "")
    if not classname:  # a module skipped at collection is reported with the module as name
        return name.replace(".", "/") + ".py"
    parts = classname.split(".")
    for cut in range(len(parts), 0, -1):
        candidate = Path(*parts[:cut]).with_suffix(".py")
        if (ROOT / candidate).is_file():
            rest = parts[cut:]
            return "::".join([candidate.as_posix(), *rest, name])
    # The file is gone (renamed or deleted since the run): name it by the dotted path.
    return f"{Path(*parts).with_suffix('.py').as_posix()}::{name}"


def skips_in(stage: str, report: Path) -> list[tuple[str, str, str]]:
    try:
        tree = ET.parse(report)
    except (OSError, ET.ParseError) as exc:
        raise InventoryError(f"{report}: unreadable JUnit report ({exc})") from exc
    found = []
    for case in tree.getroot().iter("testcase"):
        skipped = case.find("skipped")
        if skipped is None:
            continue
        reason = (skipped.get("message") or "").strip()
        found.append((stage, node_id(case), reason))
    return found


def load_inventory(path: Path = INVENTORY) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    entries = document.get("skips")
    if not isinstance(entries, list):
        raise InventoryError(f"{path}: 'skips' must be a list")
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        missing = [f for f in REQUIRED_FIELDS if not str(entry.get(f, "")).strip()]
        if missing:
            raise InventoryError(f"{entry.get('nodeid', entry)}: missing {missing}")
        if entry["status"] not in STATUSES:
            raise InventoryError(f"{entry['nodeid']}: status must be one of {sorted(STATUSES)}")
        if entry["classification"] not in CLASSIFICATIONS:
            raise InventoryError(
                f"{entry['nodeid']}: classification must be one of {sorted(CLASSIFICATIONS)}"
            )
        if entry["status"] == "exception" and not str(entry.get("decision", "")).strip():
            raise InventoryError(f"{entry['nodeid']}: an exception needs the owner's decision")
        key = (entry["stage"], entry["nodeid"])
        if key in seen:
            raise InventoryError(f"{entry['nodeid']}: declared twice in stage {entry['stage']}")
        seen.add(key)
    return entries


def compare(reports: list[tuple[str, str, str]], entries: list[dict]) -> list[str]:
    declared = {(e["stage"], e["nodeid"]): e["reason"] for e in entries}
    observed: dict[tuple[str, str], str] = {}
    problems: list[str] = []
    for stage, nodeid, reason in reports:
        if (stage, nodeid) in observed:
            problems.append(f"reported twice in stage {stage}: {nodeid}")
        observed[(stage, nodeid)] = reason
    by_node = {nodeid: stage for stage, nodeid in declared}
    for key, reason in sorted(observed.items()):
        stage, nodeid = key
        if key not in declared:
            other = by_node.get(nodeid)
            where = f" (declared for stage {other})" if other and other != stage else ""
            problems.append(f"undeclared skip in stage {stage}{where}: {nodeid} — {reason}")
        elif declared[key] != reason:
            problems.append(
                f"skip reason changed in stage {stage}: {nodeid}\n"
                f"      declared: {declared[key]}\n      observed: {reason}"
            )
    for key in sorted(set(declared) - set(observed)):
        problems.append(f"declared skip no longer occurs (delete the entry): {key[1]} [{key[0]}]")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--junit", action="append", required=True, metavar="STAGE=PATH")
    parser.add_argument("--inventory", default=str(INVENTORY))
    args = parser.parse_args(argv)
    try:
        reports: list[tuple[str, str, str]] = []
        for item in args.junit:
            stage, sep, path = item.partition("=")
            if not sep or not stage or not path:
                raise InventoryError(f"--junit expects STAGE=PATH, got {item!r}")
            reports.extend(skips_in(stage, Path(path)))
        entries = load_inventory(Path(args.inventory))
    except (InventoryError, OSError, json.JSONDecodeError) as exc:
        print(f"unit skip inventory guard: UNREADABLE — {exc}", file=sys.stderr)
        return 2
    problems = compare(reports, entries)
    if problems:
        print("unit skip inventory guard: BLOCKED")
        for line in problems:
            print(f"  ✗ {line}")
        return 1
    open_count = sum(1 for e in entries if e["status"] == "open")
    print(
        f"unit skip inventory guard: PASS — {len(reports)} skip reports equal the inventory "
        f"({open_count} open, {len(entries) - open_count} owner exceptions). "
        "Open entries keep S1 INCONCLUSIVE; this guard never turns a skip into a pass."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
