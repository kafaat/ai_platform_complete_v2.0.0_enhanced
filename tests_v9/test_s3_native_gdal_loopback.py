"""Native boto3+GDAL /vsis3/ smoke against a process-local S3 wire fixture.

Uses REAL botocore HTTP signing and REAL GDAL C++ VFS via rasterio, but the
HTTP endpoint is a minimal in-memory test double; it is NOT real MinIO, Docker,
or production certification. A separate acceptance runner covers actual MinIO.
The server is loopback-only and tests use synthetic keys and generated pixels.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def s3_http_fixture():
    """Minimal path-style S3 fixture: HEAD/GET (incl Range)/PUT only."""
    objects: dict[str, bytes] = {}
    requests: list[dict[str, str | None]] = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            pass

        def _serve(self):
            path = urlsplit(self.path).path
            with lock:
                requests.append(
                    {
                        "method": self.command,
                        "path": path,
                        "range": self.headers.get("Range"),
                        "host": self.headers.get("Host"),
                        "auth": "provided" if self.headers.get("Authorization") else None,
                    }
                )
            if self.command == "PUT":
                length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(length)
                with lock:
                    objects[path] = payload
                self.send_response(200)
                self.send_header("ETag", '"synthetic-s3-etag"')
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path == "/sahool-data" or path == "/sahool-data/":
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            with lock:
                payload = objects.get(path)
            if payload is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            byte_range = self.headers.get("Range", "")
            found = re.fullmatch(r"bytes=(\d+)-(\d*)", byte_range)
            if found:
                start = int(found.group(1))
                end = min(len(payload) - 1, int(found.group(2)) if found.group(2) else len(payload)-1)
                if start >= len(payload):
                    self.send_response(416)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                part = payload[start:end + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
            else:
                part = payload
                self.send_response(200)
            self.send_header("Content-Type", "image/tiff")
            self.send_header("Content-Length", str(len(part)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", '"synthetic-s3-etag"')
            self.end_headers()
            if self.command == "GET":
                self.wfile.write(part)

        def do_HEAD(self):
            self._serve()

        def do_GET(self):
            self._serve()

        def do_PUT(self):
            self._serve()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], objects, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _module(path: str, label: str):
    full = ROOT / path
    spec = importlib.util.spec_from_file_location(label, full)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


def test_native_gdal_cog_roundtrip_and_blob_bucket_path(monkeypatch):
    """Actual GDAL must use the same path-style endpoint as boto3 uploads."""
    rasterio = pytest.importorskip("rasterio")
    boto3 = pytest.importorskip("boto3")  # noqa: F841  (real botocore HTTP, not mocked)
    np = pytest.importorskip("numpy")
    from rasterio.shutil import copy as rasterio_copy
    from rasterio.transform import from_origin

    with s3_http_fixture() as (port, objects, requests), TemporaryDirectory() as temp:
        # Synthetic data, loopback transport, no production credentials.
        env = {
            "S3_BUCKET": "sahool-data",
            "S3_ENDPOINT": f"http://127.0.0.1:{port}",
            "S3_USE_SSL": "false",
            "S3_ALLOW_PLAINTEXT_LOOPBACK": "true",
            "S3_ALLOW_FILE_FALLBACK": "false",
            "S3_ACCESS_KEY": "synthetic-id",
            "S3_SECRET_KEY": "synthetic-not-a-real-secret",
            "S3_REGION": "us-east-1",
            "AWS_EC2_METADATA_DISABLED": "true",
            "CPL_VSIL_CURL_CACHE_SIZE": "0",
            "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        }
        for key, val in env.items():
            monkeypatch.setenv(key, val)
        raster = _module("services/raster-service/object_store.py", "acceptance_raster_adapter")
        blob = _module("shared/storage/blob_store.py", "acceptance_blob_adapter")
        assert os.environ["AWS_S3_ENDPOINT"] == f"127.0.0.1:{port}"
        assert os.environ["AWS_HTTPS"] == "NO"
        assert os.environ["AWS_VIRTUAL_HOSTING"] == "FALSE"

        data = np.arange(64 * 64, dtype="uint16").reshape((64, 64))
        raw_tif, cog_tif = str(Path(temp) / "original.tif"), str(Path(temp) / "cog.tif")
        with rasterio.open(
            raw_tif,
            mode="w",
            driver="GTiff",
            width=64,
            height=64,
            count=1,
            dtype="uint16",
            crs="EPSG:4326",
            transform=from_origin(45, 18, 0.0001, 0.0001),
            tiled=True,
            blockxsize=16,
            blockysize=16,
        ) as ds:
            ds.write(data, 1)
        with rasterio.Env():
            rasterio_copy(raw_tif, cog_tif, driver="COG", compress="LZW", blocksize=256)
        assert raster.upload_cog(cog_tif, "source/cog.tif") == "s3://sahool-data/source/cog.tif"
        assert blob.upload_bytes("proof.bin", b"synthetic-content", "application/octet-stream") == "s3://sahool-data/proof.bin"
        assert objects["/sahool-data/source/cog.tif"] == Path(cog_tif).read_bytes()
        assert objects["/sahool-data/proof.bin"] == b"synthetic-content"
        assert "/sahool-data/sahool-data/source/cog.tif" not in objects
        assert "/sahool-data/sahool-data/proof.bin" not in objects
        with rasterio.Env():
            with rasterio.open("/vsis3/sahool-data/source/cog.tif") as ds:
                observed = ds.read(1)
                assert ds.width == 64 and ds.height == 64
                assert np.array_equal(observed, data)
        gdal_requests = [r for r in requests if r["path"] == "/sahool-data/source/cog.tif" and r["method"] == "GET"]
        assert gdal_requests, "GDAL did not request the expected S3 object"
        assert all(r["host"] == f"127.0.0.1:{port}" for r in requests)
        assert all("sahool-data.sahool-data" not in str(r["host"]) for r in requests)
        assert any(r["range"] for r in gdal_requests), "GDAL did not use HTTP Range reads"


def test_blob_real_botocore_enforces_path_style_and_s3v4(monkeypatch):
    """Native client config and presign URI must bind bucket once, on a root endpoint."""
    from botocore.config import Config  # noqa: F401  (ensures real lib is present)

    with s3_http_fixture() as (port, _objects, requests):
        for key, val in {
            "S3_ENDPOINT": f"http://127.0.0.1:{port}",
            "S3_BUCKET": "sahool-data",
            "S3_USE_SSL": "false",
            "S3_ALLOW_PLAINTEXT_LOOPBACK": "true",
            "S3_ALLOW_FILE_FALLBACK": "false",
            "S3_ACCESS_KEY": "synthetic-id",
            "S3_SECRET_KEY": "synthetic-not-a-real-secret",
            "AWS_EC2_METADATA_DISABLED": "true",
        }.items():
            monkeypatch.setenv(key, val)
        blob = _module("shared/storage/blob_store.py", "acceptance_real_path_style_blob")
        client = blob._s3_client()
        assert client.meta.config.s3 == {"addressing_style": "path"}
        assert client.meta.config.signature_version == "s3v4"
        presign = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": "sahool-data", "Key": "evidence/one.bin"},
            ExpiresIn=90,
        )
        parsed = urlsplit(presign)
        assert parsed.netloc == f"127.0.0.1:{port}"
        assert parsed.path == "/sahool-data/evidence/one.bin"
        assert "X-Amz-Signature" in parsed.query
        assert blob.upload_bytes("evidence/one.bin", b"bytes", "application/octet-stream") == "s3://sahool-data/evidence/one.bin"
        assert [r["path"] for r in requests if r["method"] == "PUT"] == [
            "/sahool-data/evidence/one.bin"
        ]


def test_bucket_prefixed_service_endpoint_refused_by_both_s3_adapters(monkeypatch):
    """A path-style client must not target an already bucket-qualified hostname."""
    from unittest.mock import patch

    monkeypatch.setenv("S3_BUCKET", "")
    monkeypatch.setenv("S3_ENDPOINT", "")
    blob = _module("shared/storage/blob_store.py", "acceptance_bucket_endpoint_blob")
    raster = _module("services/raster-service/object_store.py", "acceptance_bucket_endpoint_raster")
    with (
        patch.object(blob, "S3_ENDPOINT", "https://sahool-data.s3.vendor.example"),
        patch.object(blob, "S3_BUCKET", "sahool-data"),
        patch.object(blob, "S3_USE_SSL", None),
        patch.object(raster, "S3_ENDPOINT", "https://sahool-data.s3.vendor.example"),
        patch.object(raster, "S3_BUCKET", "sahool-data"),
        patch.object(raster, "S3_USE_SSL", None),
    ):
        with pytest.raises(blob.BlobStoreError, match="bucket_prefixed_endpoint_forbidden_in_path_style"):
            blob._endpoint_url()
        with pytest.raises(raster.ObjectStoreUploadError, match="bucket_prefixed_endpoint_forbidden_in_path_style"):
            raster._endpoint_url()


def test_blob_signing_region_pinned_to_explicit_s3_region(monkeypatch):
    """Blob signing must use the same configured AWS region as raster/GDAL."""
    with s3_http_fixture() as (port, _data, _requests):
        for key, val in {
            "S3_ENDPOINT": f"http://127.0.0.1:{port}",
            "S3_BUCKET": "sahool-data",
            "S3_USE_SSL": "false",
            "S3_ALLOW_PLAINTEXT_LOOPBACK": "true",
            "S3_ACCESS_KEY": "synthetic",
            "S3_SECRET_KEY": "synthetic-not-a-real-secret",
            "S3_REGION": "eu-west-1",
            "AWS_EC2_METADATA_DISABLED": "true",
        }.items():
            monkeypatch.setenv(key, val)
        blob = _module("shared/storage/blob_store.py", "acceptance_blob_region_contract")
        _module("services/raster-service/object_store.py", "acceptance_raster_region_contract")
        assert blob._s3_client().meta.region_name == "eu-west-1"
        assert os.environ["AWS_DEFAULT_REGION"] == "eu-west-1"
