#!/usr/bin/env python3
"""Advisory skill router. Reads references/routing.json; no execution, no network, no writes.

  route_work.py --profile profile.json [--skills-root DIR]

The profile is a JSON object of boolean flags (see assets/work-profile.example.json) plus an
optional `approx_minutes`. The output names the smallest matching skill set, the mode, and,
when --skills-root is given (default: this skill's parent directory), whether each suggested
skill is actually installed there. A route to a missing skill is reported, never assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ORDER = {"LIGHT": 0, "CHECKPOINTED": 1, "COORDINATED": 2}


def load_routes(path: Path = HERE / "references" / "routing.json") -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    flags = [route["flag"] for route in data["routes"]]
    if len(flags) != len(set(flags)):
        raise ValueError("duplicate routing flag")
    return data


def choose(profile: dict, routing: dict, skills_root: Path | None = None) -> dict:
    if not isinstance(profile, dict):
        raise TypeError("profile must be a JSON object")
    known = {route["flag"] for route in routing["routes"]} | {
        "high_risk",
        "requires_git",
    }
    for key, value in profile.items():
        if key in known and not isinstance(value, bool):
            raise ValueError(f"{key} must be boolean")
    minutes = profile.get("approx_minutes", 0)
    if (
        not isinstance(minutes, (int, float))
        or isinstance(minutes, bool)
        or minutes < 0
    ):
        raise ValueError("approx_minutes must be a non-negative number")

    picked = [r for r in routing["routes"] if profile.get(r["flag"]) is True]
    mode = "LIGHT"
    for route in picked:
        mode = max(mode, route["mode"], key=ORDER.__getitem__)
    if profile.get("high_risk"):
        mode = "COORDINATED"
    elif minutes >= 60 and mode == "LIGHT":
        mode = "CHECKPOINTED"

    suggestions = []
    for route in picked:
        entry = {"skill": route["skill"], "reason": route["when"]}
        if skills_root is not None:
            entry["installed"] = (skills_root / route["skill"] / "SKILL.md").is_file()
        suggestions.append(entry)
    missing = [s["skill"] for s in suggestions if s.get("installed") is False]
    return {
        "mode": mode,
        "skills": suggestions,
        "missing": missing,
        "note": "Advisory only. Grants no permission; project rules and the user's instructions win."
        + (
            " Missing skills: paste their SKILL.md or install them; do not pretend they ran."
            if missing
            else ""
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--skills-root", type=Path, default=HERE.parent)
    args = parser.parse_args()
    try:
        result = choose(
            json.loads(args.profile.read_text(encoding="utf-8")),
            load_routes(),
            args.skills_root,
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
