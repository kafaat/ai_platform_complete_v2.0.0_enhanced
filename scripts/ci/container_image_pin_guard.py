#!/usr/bin/env python3
"""Reject mutable or unversioned container images in production Compose files."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FILES = (ROOT / "docker-compose.v9.yml", ROOT / "docker-compose.production.yml")
VERSION_TAG = re.compile(r"^(?=.*\d)(?=.*[.-])[A-Za-z0-9_.-]+$")


def _default_image(raw: str) -> str:
    match = re.fullmatch(r"\$\{[A-Z0-9_]+:-([^}]+)\}", raw)
    return match.group(1) if match else raw


def _is_pinned(image: str) -> bool:
    # A required interpolation has no mutable fallback. The production preflight
    # separately requires ZLMediaKit to be supplied as an sha256 digest.
    if re.fullmatch(r"\$\{[A-Z0-9_]+:\?[^}]+\}", image):
        return True
    if "@sha256:" in image:
        return len(image.rsplit("@sha256:", 1)[1]) == 64
    if ":" not in image.rsplit("/", 1)[-1]:
        return False
    tag = image.rsplit(":", 1)[1]
    return tag != "latest" and bool(VERSION_TAG.match(tag))


def main() -> int:
    failures: list[str] = []
    checked = 0
    for path in FILES:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, service in (data.get("services") or {}).items():
            raw = str((service or {}).get("image") or "").strip()
            if not raw:
                continue
            checked += 1
            image = _default_image(raw)
            if not _is_pinned(image):
                failures.append(f"{path.name}:{name}: {raw}")
    if failures:
        print("mutable or unversioned container images:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print(f"container image pin guard passed: {checked} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
