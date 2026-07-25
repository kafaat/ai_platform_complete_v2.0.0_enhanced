#!/usr/bin/env python3
"""Live video/ZLMediaKit wiring gate for Sahool v9.

Run after v9 is up. It checks that ZLMediaKit is reachable and that video-processor
readiness reports ZLMediaKit and edge-inference dependency status.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request


def _origin(u: str) -> str:
    """Reduce any URL/host to scheme://host:port, ignoring a path the caller may append.

    Tolerant: if someone sets ZLMEDIAKIT_PUBLIC_URL to the full API endpoint
    (…/index/api/getMediaList) or omits the scheme, we still build the request once
    (avoids the doubled-path 404: …/getMediaList/index/api/getMediaList)."""
    p = urllib.parse.urlsplit(u if "//" in u else f"http://{u}")
    return f"{p.scheme or 'http'}://{p.netloc or p.path}"


ZLM_ORIGIN = _origin(os.getenv("ZLMEDIAKIT_PUBLIC_URL", "http://localhost:8188"))
VIDEO_BASE = os.getenv("VIDEO_PROCESSOR_BASE_URL", "https://localhost/api/video")
# ZLMediaKit protects /index/api/* with a shared secret; must match the container's
# ZLM_API_SECRET (compose default sahool-zlm-dev-secret) or the API returns code -100.
ZLM_SECRET = os.getenv("ZLMEDIAKIT_API_SECRET", "sahool-zlm-dev-secret")
# The dev gateway serves a self-signed cert on :443; the host gate reaches video-processor
# only through nginx. TLS is verified by default now; to accept the self-signed loopback
# cert set INSECURE_TLS=1 (central policy shared.security.tls_policy — insecure only for
# loopback unless INSECURE_TLS_ALLOW_REMOTE=1). A real cert needs no flag.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from shared.security.tls_policy import tls_context as _tls_context  # noqa: E402

_CTX = _tls_context(VIDEO_BASE)


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10, context=_CTX) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"video-zlmediakit-live-gate: FAIL: {url}: {type(e).__name__}: {e}", file=sys.stderr)
        return 0, ""


def main() -> int:
    zq = urllib.parse.urlencode({"secret": ZLM_SECRET}) if ZLM_SECRET else ""
    zurl = ZLM_ORIGIN + "/index/api/getMediaList" + (f"?{zq}" if zq else "")
    zstatus, zbody = get(zurl)
    print("zlmediakit", zstatus, zbody[:300])
    if zstatus != 200:
        return 1
    # This is a WIRING/reachability gate: any well-formed ZLMediaKit JSON reply proves the
    # media server is up and answering on the network — which is what we verify here.
    #   code 0    → secret matched (full API control).
    #   code -100 → reachable but auth-gated. The zlmediakit/zlmediakit image auto-generates
    #               a RANDOM api.secret on boot and does NOT read ZLM_API_SECRET, so a fixed
    #               secret won't match without mounting a config.ini. That is a stream-control
    #               config detail, NOT a wiring failure — reachability is satisfied. (WARN.)
    #   other/non-JSON → unexpected, fail.
    try:
        zcode = json.loads(zbody).get("code")
    except Exception:  # noqa: BLE001
        zcode = None
    if zcode == 0:
        print("zlmediakit: secret OK — full API control available")
    elif zcode == -100:
        print(
            "zlmediakit: reachable (auth-gated). WARN: api.secret not matched — the base "
            "image auto-generates a random secret. To control streams, mount a config.ini "
            "with a fixed [api] secret (or read the container's actual secret). Not a wiring "
            "failure; continuing."
        )
    else:
        print(
            f"video-zlmediakit-live-gate: FAIL: unexpected ZLMediaKit reply code={zcode}",
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
