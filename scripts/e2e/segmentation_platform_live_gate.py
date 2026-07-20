#!/usr/bin/env python3
"""Live segmentation platform contract gate.

Validates the production trust boundary:
  browser/API -> nginx /api/segmentation/ -> sahool-platform -> field-segmentation -> SAM2.

By default this is a safe live contract gate: it requires a user JWT and calls the public
platform route.  Set SEGMENTATION_REQUIRE_MODEL=true to require the SAM2 service to report
model_loaded=true and to execute an auto/hybrid request that should reach /predict.

Environment:
  SAHOOL_BASE_URL=https://localhost
  SAHOOL_JWT=<user jwt>
  SEGMENTATION_MODE=auto|hybrid|manual        default: auto
  SEGMENTATION_BBOX=minLon,minLat,maxLon,maxLat
  SEGMENTATION_REQUIRE_MODEL=true|false       default: false
  SAM2_BASE_URL=http://localhost:8080
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request

BASE_URL = os.getenv("SAHOOL_BASE_URL", "https://localhost").rstrip("/")
SAM2_BASE_URL = os.getenv("SAM2_BASE_URL", "http://localhost:8080").rstrip("/")
JWT = os.getenv("SAHOOL_JWT", "").strip()
MODE = os.getenv("SEGMENTATION_MODE", "auto").strip() or "auto"
REQUIRE_MODEL = os.getenv("SEGMENTATION_REQUIRE_MODEL", "false").lower() in {"1", "true", "yes"}
BBOX = os.getenv("SEGMENTATION_BBOX", "44.15,15.35,44.17,15.37")


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from shared.security.tls_policy import tls_context as _tls_context  # noqa: E402


def _ctx():
    # Local v9 uses self-signed dev TLS. Insecure only for loopback + INSECURE_TLS=1
    # (central policy shared.security.tls_policy); a remote host verifies normally.
    return _tls_context(BASE_URL)


def get_json(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=12, context=_ctx()) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(body)
        except Exception:
            payload = {"raw": body}
        return e.code, payload


def post_json(url: str, payload: dict) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if JWT:
        headers["Authorization"] = f"Bearer {JWT}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(body)
        except Exception:
            payload = {"raw": body}
        return e.code, payload


def main() -> int:
    if not JWT:
        print(
            "segmentation-platform-live-gate: SKIP/FAIL: set SAHOOL_JWT to exercise platform JWT path",
            file=sys.stderr,
        )
        return 2

    sam2_status, sam2_ready = get_json(f"{SAM2_BASE_URL}/readyz")
    print("sam2 /readyz", sam2_status, sam2_ready)
    if REQUIRE_MODEL and not sam2_ready.get("model_loaded"):
        print(
            "segmentation-platform-live-gate: FAIL: SEGMENTATION_REQUIRE_MODEL=true but SAM2 model_loaded is not true",
            file=sys.stderr,
        )
        return 1

    try:
        bbox = [float(x.strip()) for x in BBOX.split(",")]
    except Exception as exc:  # noqa: BLE001
        print(
            f"segmentation-platform-live-gate: FAIL: invalid SEGMENTATION_BBOX: {exc}",
            file=sys.stderr,
        )
        return 1
    if len(bbox) != 4:
        print(
            "segmentation-platform-live-gate: FAIL: SEGMENTATION_BBOX must contain 4 numbers",
            file=sys.stderr,
        )
        return 1

    payload: dict = {"mode": MODE, "bbox": bbox}
    if MODE == "hybrid":
        payload["hints"] = [[(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]]
    if MODE == "manual":
        min_lon, min_lat, max_lon, max_lat = bbox
        payload["user_polygon"] = [
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat],
        ]

    status, body = post_json(f"{BASE_URL}/api/segmentation/segment", payload)
    print("platform /api/segmentation/segment", status, body)
    if status != 200:
        print(
            "segmentation-platform-live-gate: FAIL: platform segmentation request failed",
            file=sys.stderr,
        )
        return 1
    if body.get("geometry", {}).get("type") != "Polygon":
        print(
            "segmentation-platform-live-gate: FAIL: response did not include GeoJSON Polygon",
            file=sys.stderr,
        )
        return 1
    if MODE in {"auto", "hybrid"} and REQUIRE_MODEL:
        if body.get("source") not in {"sam2", "geosam", "segmentation"}:
            print(
                "segmentation-platform-live-gate: FAIL: unexpected source for model-backed segmentation",
                file=sys.stderr,
            )
            return 1
        if "metadata" not in body:
            print(
                "segmentation-platform-live-gate: FAIL: model-backed response did not include metadata",
                file=sys.stderr,
            )
            return 1
    print("segmentation-platform-live-gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
