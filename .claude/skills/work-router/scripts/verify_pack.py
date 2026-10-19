#!/usr/bin/env python3
"""Read-only integrity and portability check for UWRP Professional. Standard library only.

  verify_pack.py [SKILLS_ROOT] [--require-baselines] [--write-manifest]

SKILLS_ROOT is the directory holding the skill folders (`.claude/skills`, `~/.claude/skills`,
or `skills/` in the portable bundle); default: the parent of this skill. Replaces v4.1's two
validators, which disagreed: `validate_pack.py` failed the intact v4.1 release because it
sorted Path objects while SHA256SUMS was sorted as strings.

Checks: the managed skill set matches routing.json; each SKILL.md has a matching name, a
description of 1-200 characters (claude.ai upload limit) and only upload-safe frontmatter
keys; every relative link stays inside its own skill folder (so one skill can be installed
alone); JSON parses; no symlinks; MANIFEST.sha256 matches; routing, router text and trigger
scenarios agree; example action templates never claim authority; baselines, when present,
are byte-identical to their pinned releases.

`--write-manifest` regenerates MANIFEST.sha256 (the only write this script can do).
Exit 0 = PASS, 1 = problems found.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MANIFEST = "work-router/references/MANIFEST.sha256"
UPLOAD_KEYS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DESCRIPTION_MAX = 200
# Frozen owner releases, verified through their own SHA256SUMS whose digest is pinned here.
BASELINES = {
    "work-continuation": "f1ec5cf88b119a8227605d53bbfd5748ec93e742dd21009fa121f00f85a5de42",
    "adaptive-test-accelerator": "9c4a9c093befeaab818ae78da9906704ca71a9811203c0f0c3ccd40ef8ee59a7",
}
IGNORED_PARTS = {"__pycache__", ".pytest_cache"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not match:
        raise ValueError("missing frontmatter")
    values: dict[str, str] = {}
    keys: list[str] = []
    for line in match.group(1).splitlines():
        top = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if top:
            keys.append(top.group(1))
            values[top.group(1)] = top.group(2).strip()
    for key in ("name", "description"):
        raw = values.get(key, "")
        if raw.startswith('"'):
            values[key] = json.loads(raw)
    return values, keys


def managed_skills() -> list[str]:
    routing = json.loads(
        (HERE / "references" / "routing.json").read_text(encoding="utf-8")
    )
    names = {"work-router"} | {
        r["skill"] for r in routing["routes"] if not r.get("baseline")
    }
    return sorted(names)


def managed_files(root: Path) -> list[str]:
    out = []
    for skill in managed_skills():
        base = root / skill
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            rel = path.relative_to(root).as_posix()
            if (
                path.is_file()
                and rel != MANIFEST
                and not IGNORED_PARTS & set(path.parts)
                and path.suffix != ".pyc"
            ):
                out.append(rel)
    return sorted(out)


def manifest_text(root: Path) -> str:
    return "".join(f"{sha256(root / rel)}  {rel}\n" for rel in managed_files(root))


def verify(root: Path, require_baselines: bool = False) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    routing = json.loads(
        (HERE / "references" / "routing.json").read_text(encoding="utf-8")
    )
    router_text = (
        (root / "work-router" / "SKILL.md").read_text(encoding="utf-8")
        if (root / "work-router" / "SKILL.md").is_file()
        else ""
    )

    for skill in managed_skills():
        path = root / skill / "SKILL.md"
        if not path.is_file():
            problems.append(f"missing skill: {skill}")
            continue
        text = path.read_text(encoding="utf-8")
        try:
            meta, keys = frontmatter(text)
        except ValueError as exc:
            problems.append(f"{skill}: {exc}")
            continue
        if meta.get("name") != skill or not NAME_RE.fullmatch(skill) or len(skill) > 64:
            problems.append(
                f"{skill}: name must equal the folder and be lowercase-hyphenated"
            )
        description = meta.get("description", "")
        if not 1 <= len(description) <= DESCRIPTION_MAX:
            problems.append(
                f"{skill}: description is {len(description)} chars (1-{DESCRIPTION_MAX})"
            )
        if not re.search(r"\bUse (?:when|to|before|at|for)\b", description):
            problems.append(f"{skill}: description does not say when to use it")
        extra = set(keys) - UPLOAD_KEYS
        if extra:
            problems.append(
                f"{skill}: frontmatter keys rejected by claude.ai upload: {sorted(extra)}"
            )
        if len(text.splitlines()) >= 500:
            problems.append(f"{skill}: SKILL.md has 500+ lines")
        for md in (root / skill).rglob("*.md"):
            for dest in re.findall(
                r"(?<!!)\[[^\]]+\]\(([^)\s]+)\)", md.read_text(encoding="utf-8")
            ):
                dest = dest.split("#", 1)[0]
                if not dest or "://" in dest or dest.startswith(("mailto:", "#")):
                    continue
                target = (md.parent / dest).resolve()
                if not target.is_file():
                    problems.append(f"broken link: {md.relative_to(root)} -> {dest}")
                elif (root / skill).resolve() not in target.parents:
                    problems.append(
                        f"link leaves its skill folder: {md.relative_to(root)} -> {dest}"
                    )

    for route in routing["routes"]:
        if f"`{route['skill']}`" not in router_text:
            problems.append(
                f"work-router/SKILL.md does not list routed skill {route['skill']}"
            )

    scenarios = root / "skill-evaluator" / "assets" / "trigger_scenarios.json"
    if scenarios.is_file():
        known = set(managed_skills()) | set(BASELINES)
        for case in json.loads(scenarios.read_text(encoding="utf-8"))["cases"]:
            for name in case["required"] + case["any_of"] + case["acceptable"]:
                if name not in known:
                    problems.append(
                        f"trigger scenario {case['id']} names unknown skill {name}"
                    )

    for rel in managed_files(root):
        path = root / rel
        if path.is_symlink():
            problems.append(f"symlink not allowed: {rel}")
        if path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                problems.append(f"invalid JSON {rel}: {exc}")

    action = root / "safe-delivery" / "assets" / "external-action.example.json"
    if action.is_file():
        data = json.loads(action.read_text(encoding="utf-8"))
        if data.get("authorized") is not False or data.get("state") != "NOT_STARTED":
            problems.append("external-action example claims authority")

    manifest = root / MANIFEST
    if not manifest.is_file():
        problems.append(f"missing {MANIFEST}")
    elif manifest.read_text(encoding="utf-8") != manifest_text(root):
        problems.append(
            f"{MANIFEST} does not match the files (changed, added or removed)"
        )

    for name, pinned in BASELINES.items():
        sums = root / name / "SHA256SUMS"
        if not sums.is_file():
            (problems if require_baselines else notes).append(
                f"baseline not installed: {name}"
            )
            continue
        if sha256(sums) != pinned:
            problems.append(
                f"baseline {name}: SHA256SUMS differs from the pinned release"
            )
            continue
        for line in sums.read_text(encoding="utf-8").splitlines():
            digest, _, rel = line.partition("  ")
            target = root / name / rel
            if not target.is_file() or sha256(target) != digest:
                problems.append(f"baseline {name}: {rel} differs from its release")
    return problems, notes


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("root", nargs="?", type=Path, default=HERE.parent)
    parser.add_argument("--require-baselines", action="store_true")
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.write_manifest:
        (root / MANIFEST).write_text(manifest_text(root), encoding="utf-8")
    problems, notes = verify(root, args.require_baselines)
    for note in notes:
        print("·", note)
    for problem in problems:
        print("✗", problem)
    print(
        f"{'PASS' if not problems else 'FAIL'}: {len(managed_skills())} managed skills, "
        f"{len(managed_files(root))} files, {len(problems)} problems"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
