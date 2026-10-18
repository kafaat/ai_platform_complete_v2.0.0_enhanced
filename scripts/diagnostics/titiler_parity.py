#!/usr/bin/env python3
"""Compare two TiTiler deployments on the requests SAHOOL actually sends.

Read-only: GET requests against two base URLs the operator names, normally the
legacy ``sahool-titiler`` (0.18.6, compose profile ``legacy-tiler``) and the
``raster-tiler-service`` wrapper (0.22.4). The request matrix is derived from
SAHOOL's only TiTiler caller, ``shared/gis/cog_tile_proxy.py``, plus the compose
healthchecks and two operator diagnostics; ``tests_v9/test_titiler_parity_harness.py``
fails if the caller's path or parameters drift away from it.

A difference is reported, never judged acceptable here. A green report means the
measured cases matched on the measured COGs; it does not prove that clients
outside this repository, other COGs, or the deployed images behave the same.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

SAHOOL_TILE_PATH = "/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png"
SAHOOL_TILE_PARAMS = ("url", "colormap_name", "rescale")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class Case:
    name: str
    path: str
    kind: str  # png | json | stats | status
    used_by: str
    params: dict = field(default_factory=dict)
    tile: str = "inside"  # inside | outside | none


def request_matrix(rescale: str) -> list[Case]:
    """Every case names the SAHOOL caller it stands for, or says it has none."""
    return [
        Case("tile", SAHOOL_TILE_PATH, "png", "sahool-platform gis_cloud_native (no colormap)"),
        Case(
            "tile_viridis",
            SAHOOL_TILE_PATH,
            "png",
            "raster-service routers/tiles.py (default colormap)",
            {"colormap_name": "viridis"},
        ),
        Case(
            "tile_viridis_rescale",
            SAHOOL_TILE_PATH,
            "png",
            "raster-service routers/tiles.py (colormap + rescale)",
            {"colormap_name": "viridis", "rescale": rescale},
        ),
        Case(
            "tile_colormap_mixed_case",
            SAHOOL_TILE_PATH,
            "png",
            "caller regex [A-Za-z0-9_-] admits mixed case",
            {"colormap_name": "RdYlGn", "rescale": rescale},
        ),
        Case(
            "tile_outside_bounds",
            SAHOOL_TILE_PATH,
            "png",
            "any caller panning off the raster",
            tile="outside",
        ),
        Case("healthz", "/healthz", "status", "compose healthchecks (status only)", tile="none"),
        Case("info", "/cog/info", "json", "operator diagnostic, no code caller", tile="none"),
        Case(
            "statistics",
            "/cog/statistics",
            "stats",
            "operator diagnostic, no code caller",
            tile="none",
        ),
        Case(
            "tile_without_tms",
            "/cog/tiles/{z}/{x}/{y}.png",
            "png",
            "no SAHOOL caller; external clients only",
        ),
    ]


def decode_png(data: bytes):
    """RGBA array, or None when the bytes are not a decodable PNG."""
    import numpy as np
    from PIL import Image

    if not data.startswith(PNG_SIGNATURE):
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            return np.asarray(image.convert("RGBA"))
    except (OSError, ValueError):
        return None


def compare_png(a: bytes, b: bytes) -> dict:
    import numpy as np

    left, right = decode_png(a), decode_png(b)
    if left is None or right is None:
        return {"verdict": "not_png", "a_png": left is not None, "b_png": right is not None}
    if left.shape != right.shape:
        return {"verdict": "shape_differs", "a_shape": left.shape, "b_shape": right.shape}
    if np.array_equal(left, right):
        return {"verdict": "identical", "shape": list(left.shape)}
    diff = np.abs(left.astype(np.int16) - right.astype(np.int16))
    pixels = int(np.any(diff > 0, axis=-1).sum())
    total = left.shape[0] * left.shape[1]
    return {
        "verdict": "pixels_differ",
        "shape": list(left.shape),
        "differing_pixels": pixels,
        "differing_fraction": round(pixels / total, 6),
        "max_abs_diff": int(diff.max()),
        "alpha_differing_pixels": int((diff[..., 3] > 0).sum()),
    }


def _short(value) -> str:
    text = json.dumps(value, sort_keys=True, default=str)
    return text if len(text) <= 200 else text[:197] + "..."


def compare_json(a, b) -> dict:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return {"verdict": "identical" if a == b else "differs", "a": _short(a), "b": _short(b)}
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    changed = {
        key: {"a": _short(a[key]), "b": _short(b[key])}
        for key in sorted(set(a) & set(b))
        if a[key] != b[key]
    }
    verdict = "identical" if not (only_a or only_b or changed) else "differs"
    return {"verdict": verdict, "only_a": only_a, "only_b": only_b, "changed": changed}


_STAT_KEYS = ("min", "max", "mean", "std", "count", "valid_pixels", "masked_pixels")


def compare_stats(a, b, rel_tol: float = 1e-6) -> dict:
    """Per band and metric; bands are matched by their key (b1, b2, ...)."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return {"verdict": "differs", "reason": "not_a_mapping"}
    if set(a) != set(b):
        return {"verdict": "differs", "a_bands": sorted(a), "b_bands": sorted(b)}
    out = {}
    for band in sorted(a):
        for key in _STAT_KEYS:
            left, right = a[band].get(key), b[band].get(key)
            if left is None and right is None:
                continue
            same = (
                isinstance(left, (int, float))
                and isinstance(right, (int, float))
                and math.isclose(left, right, rel_tol=rel_tol, abs_tol=1e-9)
            )
            if not same:
                out[f"{band}.{key}"] = {"a": left, "b": right}
    return {"verdict": "identical" if not out else "differs", "differences": out}


def response_record(status: int, content_type: str, body: bytes) -> dict:
    return {
        "status": status,
        "content_type": content_type.split(";", 1)[0].strip(),
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def compare_case(case: Case, a: tuple[int, str, bytes], b: tuple[int, str, bytes]) -> dict:
    rec_a, rec_b = response_record(*a), response_record(*b)
    result = {"case": case.name, "path": case.path, "used_by": case.used_by, "a": rec_a, "b": rec_b}
    if rec_a["status"] != rec_b["status"]:
        result["verdict"] = "status_differs"
        return result
    if rec_a["status"] != 200:
        result["verdict"] = "same_non_200"
        return result
    if case.kind == "status":
        result["verdict"] = "same_status"
        return result
    if case.kind == "png":
        detail = compare_png(a[2], b[2])
    else:
        try:
            left, right = json.loads(a[2]), json.loads(b[2])
        except ValueError:
            result["verdict"] = "not_json"
            return result
        detail = compare_stats(left, right) if case.kind == "stats" else compare_json(left, right)
    result["detail"] = detail
    result["verdict"] = detail["verdict"]
    return result


def _tile(spec: str) -> tuple[int, int, int]:
    z, x, y = (int(part) for part in spec.split("/"))
    return z, x, y


def run(legacy: str, wrapper: str, cog: str, inside: str, outside: str, rescale: str) -> dict:
    import httpx

    tiles = {"inside": _tile(inside), "outside": _tile(outside)}
    results = []
    with httpx.Client(timeout=httpx.Timeout(30, connect=5), trust_env=False) as client:
        for case in request_matrix(rescale):
            path = case.path
            params = dict(case.params)
            if case.tile != "none":
                z, x, y = tiles[case.tile]
                path = path.format(z=z, x=x, y=y)
            if case.name != "healthz":
                params["url"] = cog
            pair = []
            for base in (legacy, wrapper):
                response = client.get(base.rstrip("/") + path, params=params)
                pair.append(
                    (
                        response.status_code,
                        response.headers.get("content-type", ""),
                        response.content,
                    )
                )
            results.append(compare_case(case, pair[0], pair[1]))
    return {
        "schema": "sahool.titiler-parity.v1",
        "measured_at": datetime.now(UTC).isoformat(),
        "a": "legacy",
        "b": "wrapper",
        "cog_sha256": hashlib.sha256(cog.encode()).hexdigest(),
        "scope": "measured cases on this COG only; not a statement about other clients or images",
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--legacy", required=True, help="base URL of the legacy TiTiler")
    parser.add_argument("--wrapper", required=True, help="base URL of raster-tiler-service")
    parser.add_argument("--cog", required=True, help="COG URL or path both services can read")
    parser.add_argument("--tile", required=True, help="z/x/y inside the COG")
    parser.add_argument("--outside-tile", required=True, help="z/x/y outside the COG")
    parser.add_argument("--rescale", default="-1,1")
    parser.add_argument("--out", help="write the JSON report here")
    args = parser.parse_args(argv)
    report = run(args.legacy, args.wrapper, args.cog, args.tile, args.outside_tile, args.rescale)
    text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    for row in report["results"]:
        print(f"{row['case']:<26} {row['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
