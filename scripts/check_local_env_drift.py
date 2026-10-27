#!/usr/bin/env python3
"""Advisory: keys in .env.example that a local .env lacks (key names only, never values).

A local .env copied before a new setting was introduced keeps working until a service
refuses to start. The case that motivated this check: #1244 made raster-service refuse
``http://sahool-minio`` unless ``S3_ALLOW_PLAINTEXT_INTERNAL=true``; Compose defaults it
to ``false`` and ``.env.example`` sets it, so an older .env stopped the whole stack.

Usage: python scripts/check_local_env_drift.py [--env .env] [--example .env.example] [--strict]
Exit 0 always (advisory) unless --strict and a key is missing. Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Missing keys whose Compose default stops a service at startup, with the reason.
STARTUP_BLOCKING = {
    "S3_ALLOW_PLAINTEXT_INTERNAL": (
        "raster-service refuses http://sahool-minio without it (Compose default false)"
    ),
}

_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def env_keys(path: Path) -> list[str]:
    """Key names assigned in a dotenv file, in file order, without duplicates."""
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _KEY.match(line)
        if m and m.group(1) not in keys:
            keys.append(m.group(1))
    return keys


def missing_keys(env: Path, example: Path) -> list[str]:
    present = set(env_keys(env))
    return [k for k in env_keys(example) if k not in present]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--example", type=Path, default=Path(".env.example"))
    parser.add_argument("--strict", action="store_true", help="exit 1 when a key is missing")
    args = parser.parse_args(argv)
    if not args.env.is_file() or not args.example.is_file():
        print(f"env drift: skipped (missing {args.env} or {args.example})")
        return 0
    missing = missing_keys(args.env, args.example)
    if not missing:
        print(f"env drift: {args.env} has every key in {args.example}")
        return 0
    blocking = [k for k in missing if k in STARTUP_BLOCKING]
    for key in blocking:
        print(f"env drift: MISSING {key} - {STARTUP_BLOCKING[key]}")
    others = [k for k in missing if k not in STARTUP_BLOCKING]
    if others:
        print(f"env drift: {len(others)} other key(s) in {args.example} not in {args.env}:")
        for key in others:
            print(f"  {key}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
