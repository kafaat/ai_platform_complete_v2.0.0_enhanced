#!/usr/bin/env python3
"""Blind trigger evaluation for installed Agent Skills. Standard library only; no network.

Measures the layer that decides *which* skill an agent loads: the `name` + `description`
pairs an agent sees before any skill body. It does not measure whether the agent then
follows the skill's steps.

  trigger_eval.py emit  --skills-root DIR --scenarios FILE [--seed N] > prompt.txt
      Prints a self-contained prompt. Give it to any agent (Claude, Codex, Kimi, ...) in a
      fresh context; save its JSON reply as answers.json.
  trigger_eval.py score --scenarios FILE --answers FILE [--skills-root DIR] [--json]
      Scores the reply. Exit 0 = scored (whatever the result), 2 = unusable input.

A case passes when every `required` skill is chosen, at least one `any_of` skill is chosen
(if any_of is non-empty), and nothing outside required + any_of + acceptable is chosen.
A case with all three lists empty is a negative case: choosing any skill is a false trigger.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

MAX_SKILLS_PER_TASK = 3


def frontmatter(text: str) -> dict[str, str]:
    """`name` and `description` from SKILL.md frontmatter, including folded `>-` blocks."""
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not match:
        raise ValueError("missing frontmatter")
    out: dict[str, str] = {}
    lines = match.group(1).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        key_match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        i += 1
        if not key_match:
            continue
        key, value = key_match.group(1), key_match.group(2).strip()
        if value in (">", ">-", "|", "|-"):
            block = []
            while i < len(lines) and (
                lines[i].startswith((" ", "\t")) or not lines[i].strip()
            ):
                block.append(lines[i].strip())
                i += 1
            joiner = "\n" if value.startswith("|") else " "
            value = joiner.join(part for part in block if part)
        out[key] = value.strip().strip("\"'")
    return out


def installed_skills(root: Path) -> dict[str, str]:
    skills = {}
    for path in sorted(root.glob("*/SKILL.md")):
        meta = frontmatter(path.read_text(encoding="utf-8"))
        name = meta.get("name", "")
        if name != path.parent.name:
            raise ValueError(f"{path}: name {name!r} does not match its directory")
        skills[name] = meta.get("description", "")
    if not skills:
        raise ValueError(f"no */SKILL.md under {root}")
    return skills


def load_cases(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids")
    for case in cases:
        for key in ("required", "any_of", "acceptable"):
            if not isinstance(case.get(key, []), list):
                raise TypeError(f"{case['id']}: {key} must be a list")
    return cases


def emit(skills: dict[str, str], cases: list[dict], seed: int) -> str:
    order = list(cases)
    random.Random(seed).shuffle(order)
    catalogue = "\n".join(f"- {name}: {desc}" for name, desc in sorted(skills.items()))
    tasks = "\n".join(f"{case['id']}: {case['prompt']}" for case in order)
    return (
        "You are an AI agent. Before starting a task you may load skills. Each loaded skill "
        "costs context, so load one only when its instructions would materially change how "
        "you do that task. Choosing no skill is often correct. Judge each task "
        "independently, using only the skill names and descriptions below.\n\n"
        f"AVAILABLE SKILLS\n{catalogue}\n\n"
        f"TASKS (id: request)\n{tasks}\n\n"
        f"For every task id, list the skills you would load (0 to {MAX_SKILLS_PER_TASK}). "
        "Reply with ONLY a JSON object mapping each id to a list of skill names, e.g. "
        '{"X-1": [], "X-2": ["some-skill"]}.'
    )


def score(cases: list[dict], answers: dict, known: set[str] | None) -> dict:
    rows, unknown_names = [], set()
    per_skill: dict[str, dict[str, int]] = {}
    for case in cases:
        chosen = answers.get(case["id"])
        if not isinstance(chosen, list):
            rows.append({"id": case["id"], "ok": False, "reason": "no answer"})
            continue
        chosen_set = {str(x) for x in chosen}
        if known is not None:
            unknown_names |= chosen_set - known
        required = set(case.get("required", []))
        any_of = set(case.get("any_of", []))
        allowed = required | any_of | set(case.get("acceptable", []))
        negative = not allowed
        problems = []
        if required - chosen_set:
            problems.append("missed " + ",".join(sorted(required - chosen_set)))
        if any_of and not (any_of & chosen_set):
            problems.append("none of " + ",".join(sorted(any_of)))
        if chosen_set - allowed:
            problems.append("extra " + ",".join(sorted(chosen_set - allowed)))
        if len(chosen_set) > MAX_SKILLS_PER_TASK:
            problems.append("too many")
        rows.append(
            {
                "id": case["id"],
                "ok": not problems,
                "negative": negative,
                "chosen": sorted(chosen_set),
                "reason": "; ".join(problems),
            }
        )
        for name in required | any_of | chosen_set:
            stats = per_skill.setdefault(
                name, {"expected": 0, "hit": 0, "chosen": 0, "wrong": 0}
            )
            if name in required:
                stats["expected"] += 1
                stats["hit"] += name in chosen_set
            if name in chosen_set:
                stats["chosen"] += 1
                stats["wrong"] += name not in allowed
    negatives = [r for r in rows if r.get("negative")]
    return {
        "cases": len(cases),
        "passed": sum(r["ok"] for r in rows),
        "pass_rate": round(sum(r["ok"] for r in rows) / len(cases), 3)
        if cases
        else None,
        "negative_cases": len(negatives),
        "false_triggers": sum(not r["ok"] for r in negatives),
        "unknown_skill_names": sorted(unknown_names),
        "per_skill": dict(sorted(per_skill.items())),
        "failures": [r for r in rows if not r["ok"]],
        "limits": "Measures selection from name+description only, on one reply; not step "
        "compliance, not a different model, not a different prompt wording.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_emit = sub.add_parser("emit")
    p_emit.add_argument("--skills-root", type=Path, required=True)
    p_emit.add_argument("--scenarios", type=Path, required=True)
    p_emit.add_argument("--seed", type=int, default=0)
    p_score = sub.add_parser("score")
    p_score.add_argument("--scenarios", type=Path, required=True)
    p_score.add_argument("--answers", type=Path, required=True)
    p_score.add_argument("--skills-root", type=Path)
    p_score.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        cases = load_cases(args.scenarios)
        if args.cmd == "emit":
            print(emit(installed_skills(args.skills_root), cases, args.seed))
            return 0
        text = args.answers.read_text(encoding="utf-8")
        found = re.search(r"\{.*\}", text, re.DOTALL)
        answers = json.loads(found.group(0) if found else text)
        known = set(installed_skills(args.skills_root)) if args.skills_root else None
        result = score(cases, answers, known)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"unusable input: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"{result['passed']}/{result['cases']} cases pass; false triggers on negatives: "
            f"{result['false_triggers']}/{result['negative_cases']}"
        )
        for row in result["failures"]:
            print(
                f"  FAIL {row['id']}: {row['reason'] or 'unanswered'} (chose {row.get('chosen')})"
            )
        if result["unknown_skill_names"]:
            print("  unknown skill names:", ", ".join(result["unknown_skill_names"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
