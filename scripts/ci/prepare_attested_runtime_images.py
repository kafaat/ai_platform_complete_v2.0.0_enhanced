#!/usr/bin/env python3
"""Validate an externally built image manifest and generate a pull-by-digest Compose override."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
REF = re.compile(r"^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$")
MAP = {
    "weather-service": "sahool-weather-service",
    "soil-service": "sahool-soil-service",
    "sahool-platform": "sahool-platform",
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--tested-sha", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    if not SHA.fullmatch(a.tested_sha):
        print("invalid tested sha", file=sys.stderr)
        return 1
    try:
        o = json.loads(Path(a.manifest).read_text())
    except Exception as ex:
        print(f"image manifest invalid: {ex}", file=sys.stderr)
        return 1
    if o.get("schema_version") != "1.0" or o.get("source_sha") != a.tested_sha:
        print("image manifest source mismatch", file=sys.stderr)
        return 1
    images = o.get("images")
    if not isinstance(images, dict):
        print("images missing", file=sys.stderr)
        return 1
    lines = ["services:"]
    for svc, compose in MAP.items():
        row = images.get(svc, {})
        ref = str(row.get("image") or "")
        if not REF.fullmatch(ref):
            print(f"{svc}: image must be GHCR pull-by-digest reference", file=sys.stderr)
            return 1
        if row.get("source_sha") != a.tested_sha:
            print(f"{svc}: source sha mismatch", file=sys.stderr)
            return 1
        lines += [f"  {compose}:", f"    image: {ref}", "    build: null"]
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"attested_image_override_ok services={len(MAP)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
