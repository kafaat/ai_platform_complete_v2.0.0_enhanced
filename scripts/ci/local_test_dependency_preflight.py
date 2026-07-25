#!/usr/bin/env python3
"""Give an actionable failure before the local quality gate starts test collection."""

import sys
from importlib.util import find_spec

REQUIRED = {
    "pytest": "pytest",
    "pytest_asyncio": "pytest-asyncio",
    "fastapi": "fastapi",
    "httpx": "httpx",
    "numpy": "numpy",
    "rasterio": "rasterio",
}


def main() -> int:
    missing = [package for module, package in REQUIRED.items() if find_spec(module) is None]
    if missing:
        print("local test dependency preflight: FAILED", file=sys.stderr)
        print(
            "Install the declared raster test runtime before running the local gate: "
            "python3 -m pip install -r services/raster-service/requirements.txt pytest pytest-asyncio",
            file=sys.stderr,
        )
        print(f"Missing packages: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("local test dependency preflight: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
