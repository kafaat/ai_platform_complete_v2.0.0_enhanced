#!/usr/bin/env python3
"""Disposable real MinIO, botocore SigV4/path-style and GDAL COG acceptance.

Explicitly refuses non-loopback endpoints, and requires a lab-only opt-in.
No changes to GitHub, Railway, managed databases, or existing object stores.
This program creates synthetic objects in a fresh bucket and does NOT delete
any existing user resources; run it only with the isolated tmpfs Compose lab.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError(f"unexpected_http_redirect_{code}")


def validate_test_target(endpoint: str, explicitly_disposable: bool) -> tuple[str, int]:
    """Unconditional stop before any network activity or storage write."""
    parsed = urlsplit(endpoint)
    if not explicitly_disposable:
        raise ValueError("disposable_lab_opt_in_missing")
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
    return parsed.hostname, parsed.port


def _load(relative: str, label: str):
    spec = importlib.util.spec_from_file_location(label, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"missing_module_{label}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


def _health(endpoint: str) -> int:
    opener = build_opener(RejectRedirects())
    try:
        with opener.open(endpoint + "/minio/health/live", timeout=7) as resp:
            return resp.status
    except HTTPError as exc:
        return exc.code


def run(endpoint: str, report: Path) -> dict:
    import numpy as np
    import rasterio
    from rasterio.shutil import copy as rasterio_copy
    from rasterio.transform import from_origin

    access_key = os.environ["S3_TEST_ROOT_USER"]
    secret_key = os.environ["S3_TEST_ROOT_PASSWORD"]
    # Never emit the secret in the stdout or report. Lab socket only.
    settings = {
        "S3_ENDPOINT": endpoint,
        "S3_BUCKET": "sahool-acceptance-" + uuid4().hex[:16],
        "S3_REGION": "us-east-1",
        "S3_USE_SSL": "false",
        "S3_ALLOW_PLAINTEXT_LOOPBACK": "true",
        "S3_ALLOW_PLAINTEXT_INTERNAL": "false",
        "S3_ALLOW_FILE_FALLBACK": "false",
        "S3_ACCESS_KEY": access_key,
        "S3_SECRET_KEY": secret_key,
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    os.environ.update(settings)
    # When imported the raster adapter configures GDAL /vsis3/ variables.
    raster = _load("services/raster-service/object_store.py", "live_minio_raster_adapter")
    blob = _load("shared/storage/blob_store.py", "live_minio_blob_adapter")
    bucket = settings["S3_BUCKET"]
    client = blob._s3_client()
    assert client.meta.config.s3 == {"addressing_style": "path"}
    assert client.meta.config.signature_version == "s3v4"
    assert os.environ["AWS_S3_ENDPOINT"] == urlsplit(endpoint).netloc
    assert os.environ["AWS_HTTPS"] == "NO"
    assert os.environ["AWS_VIRTUAL_HOSTING"] == "FALSE"
    assert _health(endpoint) == 200, "MinIO API returned error/redirect; required HTTP 200"

    client.create_bucket(Bucket=bucket)  # unique disposable bucket in tmpfs
    with tempfile.TemporaryDirectory(prefix="sahool-s3-cog-") as tmp:
        src = str(Path(tmp) / "generated.tif")
        cog = str(Path(tmp) / "acceptance.tif")
        arr = np.arange(64 * 64, dtype="uint16").reshape(64, 64)
        with rasterio.open(
            src, "w", driver="GTiff", width=64, height=64, count=1, dtype="uint16",
            transform=from_origin(44.5, 16, .001, .001), crs="EPSG:4326",
            tiled=True, blockxsize=16, blockysize=16,
        ) as dst:
            dst.write(arr, 1)
        rasterio_copy(src, cog, driver="COG", compress="LZW", blocksize=256)
        cog_key = "synthetic/verification.tif"
        ref = raster.upload_cog(cog, cog_key)
        assert ref == f"s3://{bucket}/{cog_key}"
        assert client.head_object(Bucket=bucket, Key=cog_key)["ContentLength"] > 100
        assert blob.upload_bytes("synthetic/check.txt", b"S3 acceptance", "text/plain") == f"s3://{bucket}/synthetic/check.txt"
        assert blob.object_exists(f"s3://{bucket}/synthetic/check.txt")
        assert client.get_object(Bucket=bucket, Key="synthetic/check.txt")["Body"].read() == b"S3 acceptance"
        assert not blob.object_exists(f"s3://{bucket}/{bucket}/synthetic/check.txt")
        presign = blob.presigned_get_url(f"s3://{bucket}/synthetic/check.txt", 60)
        assert urlsplit(presign).path == f"/{bucket}/synthetic/check.txt"
        with rasterio.Env():
            with rasterio.open(f"/vsis3/{bucket}/{cog_key}") as ds:
                assert np.array_equal(ds.read(1), arr)
    result = {
        "schema": "sahool.s3-minio-gdal-disposable-acceptance.v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "endpoint_scope": "127.0.0.1-disposable-docker-tmpfs",
        "minio_health_http": 200,
        "http_to_https_redirect": False,
        "auth": "synthetic_generated_credentials_not_serialized",
        "signature": "s3v4",
        "boto3_addressing": "path",
        "path_double_bucket": False,
        "native_gdal_vsi_cog": "PASS",
        "actual_minio": True,
        "docker_image_id": os.environ.get("S3_TEST_IMAGE_ID", "NOT_CAPTURED"),
        "docker_image_ref": os.environ.get("S3_TEST_MINIO_IMAGE", "NOT_CAPTURED"),
        "docker_image_evidence_note": "Local Docker image ID plus pinned image reference; NOT an OCI attestation or registry verification",
        "bucket": bucket,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    validate_test_target(
        args.endpoint,
        explicitly_disposable=os.getenv("SAHOOL_S3_ACCEPTANCE_DISPOSABLE") == "1",
    )
    result = run(args.endpoint, args.report)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
