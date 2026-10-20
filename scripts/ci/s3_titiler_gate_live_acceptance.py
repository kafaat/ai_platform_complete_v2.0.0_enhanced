#!/usr/bin/env python3
"""Legacy TiTiler through the S3 endpoint gate: upload a synthetic COG, read it back.

`upload` writes one COG to a fresh bucket on the disposable MinIO; `read` asks TiTiler
(started by run_s3_titiler_gate_live.sh through gdal_s3_env_gate.py) for its info and
statistics over s3://, and checks them against the pixels that were written.
Loopback endpoints and the lab opt-in only; the report carries no secret.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

BUCKET = "sahool-rasters"
KEY = "fields/titiler-gate/ndvi.tif"
SIZE = 256


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError(f"unexpected_http_redirect_{code}")


def validate_loopback(endpoint: str, explicitly_disposable: bool) -> str:
    """Unconditional stop before any network activity or storage write."""
    if not explicitly_disposable:
        raise ValueError("disposable_lab_opt_in_missing")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.port is None
        or not (1024 <= parsed.port <= 65535)
    ):
        raise ValueError("test_endpoint_must_be_exact_loopback_http_host_and_port")
    return f"http://127.0.0.1:{parsed.port}"


def _pixels():
    import numpy as np

    return np.arange(SIZE * SIZE, dtype="uint16").reshape(SIZE, SIZE) % 1000


def upload(endpoint: str) -> None:
    import boto3
    import rasterio
    from botocore.client import Config
    from rasterio.shutil import copy as rasterio_copy
    from rasterio.transform import from_origin

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["S3_TEST_ROOT_USER"],
        aws_secret_access_key=os.environ["S3_TEST_ROOT_PASSWORD"],
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    client.create_bucket(Bucket=BUCKET)
    with tempfile.TemporaryDirectory() as tmp:
        src, cog = Path(tmp, "src.tif"), Path(tmp, "cog.tif")
        profile = {
            "driver": "GTiff",
            "width": SIZE,
            "height": SIZE,
            "count": 1,
            "dtype": "uint16",
            "crs": "EPSG:4326",
            "transform": from_origin(44.0, 15.6, 0.001, 0.001),
        }
        with rasterio.open(src, "w", **profile) as dst:
            dst.write(_pixels(), 1)
        rasterio_copy(src, cog, driver="COG")
        client.upload_file(str(cog), BUCKET, KEY)
    print(f"uploaded s3://{BUCKET}/{KEY}")


def _get_json(base: str, path: str) -> dict:
    url = f"{base}{path}?url={quote(f's3://{BUCKET}/{KEY}', safe='')}"
    try:
        with build_opener(RejectRedirects()).open(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise AssertionError(f"titiler_{path}_http_{exc.code}: {body}") from None


def read(titiler: str, report: Path) -> dict:
    pixels = _pixels()
    info = _get_json(titiler, "/cog/info")
    assert (info["width"], info["height"], info["dtype"]) == (SIZE, SIZE, "uint16"), info
    assert [round(v, 6) for v in info["bounds"]] == [44.0, 15.344, 44.256, 15.6], info
    stats = _get_json(titiler, "/cog/statistics")["b1"]
    expected = {
        "min": float(pixels.min()),
        "max": float(pixels.max()),
        "count": float(pixels.size),
        "mean": float(pixels.mean()),
    }
    for name, value in expected.items():
        assert abs(stats[name] - value) < 1e-6, (name, stats[name], value)
    result = {
        "schema": "sahool.s3_titiler_gate_live_acceptance.v1",
        "at": datetime.now(UTC).isoformat(),
        "object": f"s3://{BUCKET}/{KEY}",
        "info": {k: info[k] for k in ("width", "height", "dtype", "bounds")},
        "statistics": {k: stats[k] for k in expected},
        "titiler_image": os.environ.get("S3_TEST_TITILER_IMAGE", ""),
        "verdict": "PASS",
    }
    report.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    up = sub.add_parser("upload")
    up.add_argument("--endpoint", required=True)
    rd = sub.add_parser("read")
    rd.add_argument("--titiler", required=True)
    rd.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    disposable = os.environ.get("SAHOOL_S3_ACCEPTANCE_DISPOSABLE") == "1"
    if args.action == "upload":
        upload(validate_loopback(args.endpoint, disposable))
    else:
        read(validate_loopback(args.titiler, disposable), args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
