#!/usr/bin/env python3
"""Live video/ZLMediaKit wiring gate for Sahool v9.

Run after v9 is up. It checks that ZLMediaKit is reachable and that video-processor
readiness reports ZLMediaKit and edge-inference dependency status.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

ZLM_BASE = os.getenv("ZLMEDIAKIT_PUBLIC_URL", "http://localhost:8188")
VIDEO_BASE = os.getenv("VIDEO_PROCESSOR_BASE_URL", "http://localhost/api/video")


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"video-zlmediakit-live-gate: FAIL: {url}: {type(e).__name__}: {e}", file=sys.stderr)
        return 0, ""


def main() -> int:
    zstatus, zbody = get(ZLM_BASE.rstrip("/") + "/index/api/getMediaList")
    print("zlmediakit", zstatus, zbody[:300])
    if zstatus != 200:
        return 1

    # Direct video readiness URL can be supplied if nginx path differs.
    ready_url = os.getenv("VIDEO_READYZ_URL", VIDEO_BASE.rstrip("/") + "/readyz")
    vstatus, vbody = get(ready_url)
    print("video-readyz", vstatus, vbody[:800])
    if vstatus != 200:
        return 1
    try:
        payload = json.loads(vbody)
    except Exception as e:  # noqa: BLE001
        print(f"video-zlmediakit-live-gate: FAIL: invalid JSON: {e}", file=sys.stderr)
        return 1
    deps = payload.get("dependencies") or {}
    if "zlmediakit" not in deps or "edge_inference" not in deps:
        print(
            "video-zlmediakit-live-gate: FAIL: readyz must expose zlmediakit and edge_inference dependencies",
            file=sys.stderr,
        )
        return 1
    print("video-zlmediakit-live-gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
