#!/usr/bin/env python3
"""Live video/ZLMediaKit wiring gate for Sahool v9.

Run after v9 is up. It checks that ZLMediaKit is reachable and that video-processor
readiness reports ZLMediaKit and edge-inference dependency status.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

ZLM_BASE = os.getenv("ZLMEDIAKIT_PUBLIC_URL", "http://localhost:8188")
VIDEO_BASE = os.getenv("VIDEO_PROCESSOR_BASE_URL", "https://localhost/api/video")
# ZLMediaKit protects /index/api/* with a shared secret; must match the container's
# ZLM_API_SECRET (compose default sahool-zlm-dev-secret) or the API returns code -100.
ZLM_SECRET = os.getenv("ZLMEDIAKIT_API_SECRET", "sahool-zlm-dev-secret")
# The dev gateway serves a self-signed cert on :443; the host gate reaches video-processor
# only through nginx. Skip TLS verify by default (loopback dev); set E2E_TLS_VERIFY=1 once
# a real cert is installed.
_TLS_VERIFY = os.getenv("E2E_TLS_VERIFY", "0").strip().lower() in {"1", "true", "yes", "on"}
_CTX = None if _TLS_VERIFY else ssl._create_unverified_context()


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10, context=_CTX) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"video-zlmediakit-live-gate: FAIL: {url}: {type(e).__name__}: {e}", file=sys.stderr)
        return 0, ""


def main() -> int:
    zq = urllib.parse.urlencode({"secret": ZLM_SECRET}) if ZLM_SECRET else ""
    zurl = ZLM_BASE.rstrip("/") + "/index/api/getMediaList" + (f"?{zq}" if zq else "")
    zstatus, zbody = get(zurl)
    print("zlmediakit", zstatus, zbody[:300])
    if zstatus != 200:
        return 1
    # ZLMediaKit answers HTTP 200 with JSON {code}: 0 = OK, -100 = wrong/absent secret.
    try:
        zcode = json.loads(zbody).get("code")
    except Exception:  # noqa: BLE001
        zcode = None
    if zcode != 0:
        print(
            f"video-zlmediakit-live-gate: FAIL: ZLMediaKit code={zcode} "
            "(ZLMEDIAKIT_API_SECRET must match the container ZLM_API_SECRET)",
            file=sys.stderr,
        )
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
