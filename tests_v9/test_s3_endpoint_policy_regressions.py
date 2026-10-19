"""S3 TLS security regressions using SAHOOL's actual adapters.

Network interactions are simulated. This is a local review candidate and is not
proof of an external S3 service or an approved production configuration.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_file(rel: str, name: str):
    p = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, p)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class ActualS3IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"S3_BUCKET": "", "S3_ENDPOINT": ""}):
            cls.blob = load_file(
                "shared/storage/blob_store.py", "candidate_sahool_blob_store"
            )
            cls.raster = load_file(
                "services/raster-service/object_store.py", "candidate_sahool_raster_store"
            )

    def test_blob_preserves_explicit_https_when_flag_unset(self):
        with (
            patch.object(self.blob, "S3_ENDPOINT", "https://storage.example.test:9443"),
            patch.object(self.blob, "S3_USE_SSL", None),
        ):
            self.assertEqual(self.blob._endpoint_url(), "https://storage.example.test:9443")
            self.assertTrue(self.blob._use_ssl())

    def test_blob_fails_closed_explicit_https_with_false_flag(self):
        with (
            patch.object(self.blob, "S3_ENDPOINT", "https://storage.example.test:9443"),
            patch.object(self.blob, "S3_USE_SSL", "false"),
        ):
            with self.assertRaisesRegex(self.blob.BlobStoreError, "scheme_flag_conflict"):
                self.blob._endpoint_url()

    def test_blob_http_external_denied_despite_internal_opt_in(self):
        with (
            patch.object(self.blob, "S3_ENDPOINT", "http://minio.bad-domain.example:9000"),
            patch.object(self.blob, "S3_USE_SSL", "false"),
            patch.object(self.blob, "S3_ALLOW_PLAINTEXT_INTERNAL", "true"),
        ):
            with self.assertRaisesRegex(
                self.blob.BlobStoreError, "plaintext_external_forbidden"
            ):
                self.blob._endpoint_url()

    def test_blob_internal_http_explicit_opt_in_required(self):
        with (
            patch.object(self.blob, "S3_ENDPOINT", "http://sahool-minio:9000"),
            patch.object(self.blob, "S3_USE_SSL", "false"),
        ):
            with patch.object(self.blob, "S3_ALLOW_PLAINTEXT_INTERNAL", "false"):
                with self.assertRaisesRegex(
                    self.blob.BlobStoreError, "plaintext_internal_requires_opt_in"
                ):
                    self.blob._endpoint_url()
            with patch.object(self.blob, "S3_ALLOW_PLAINTEXT_INTERNAL", "true"):
                self.assertEqual(self.blob._endpoint_url(), "http://sahool-minio:9000")

    def test_blob_bad_endpoint_no_file_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(self.blob, "S3_ENDPOINT", "http://external.example:9000"),
                patch.object(self.blob, "S3_USE_SSL", "false"),
                patch.object(self.blob, "S3_BUCKET", "bucket"),
                patch.object(self.blob, "S3_ALLOW_FILE_FALLBACK", "true"),
                patch.object(self.blob, "LOCAL_DIR", tmp),
            ):
                with self.assertRaisesRegex(
                    self.blob.BlobStoreError, "plaintext_external_forbidden"
                ):
                    self.blob.upload_bytes(
                        "x/test.bin", b"SYNTHETIC", "application/octet-stream"
                    )
                self.assertEqual(list(Path(tmp).rglob("*")), [])

    def test_blob_endpoint_userinfo_rejected_without_echoing_credentials(self):
        with (
            patch.object(self.blob, "S3_ENDPOINT", "https://user:pass@storage.example.test"),
            patch.object(self.blob, "S3_USE_SSL", None),
        ):
            with self.assertRaisesRegex(
                self.blob.BlobStoreError, "userinfo_forbidden"
            ) as result:
                self.blob._endpoint_url()
            self.assertNotIn("pass", str(result.exception))

    def test_blob_malformed_ipv6_url_raises_contract_error(self):
        with (
            patch.object(self.blob, "S3_ENDPOINT", "https://[::1"),
            patch.object(self.blob, "S3_USE_SSL", None),
        ):
            with self.assertRaisesRegex(
                self.blob.BlobStoreError, "invalid_endpoint_authority"
            ):
                self.blob._endpoint_url()

    def test_helper_rejects_malformed_bracketed_endpoint(self):
        from shared.storage.s3_endpoint_security import (
            EndpointPolicyError,
            resolve_endpoint,
        )

        for value in ("https://[::1", "https://[]:9000"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    EndpointPolicyError, "invalid_endpoint_authority"
                ):
                    resolve_endpoint(value)

    def test_blob_presign_ttl_existing_contract(self):
        with self.assertRaisesRegex(
            self.blob.BlobStoreError, "presign TTL out of contract"
        ):
            self.blob.presigned_get_url("s3://bucket/test", 301)

    def test_raster_boto_and_gdal_https_decisions_are_same(self):
        with (
            patch.object(self.raster, "S3_ENDPOINT", "https://raster.example.test:9443"),
            patch.object(self.raster, "S3_USE_SSL", None),
            patch.object(self.raster, "S3_BUCKET", "rasters"),
            patch.dict(os.environ, {}, clear=True),
        ):
            self.raster.gdal_configure()
            self.assertEqual(os.environ["AWS_S3_ENDPOINT"], "raster.example.test:9443")
            self.assertEqual(os.environ["AWS_HTTPS"], "YES")
            self.assertEqual(os.environ["AWS_VIRTUAL_HOSTING"], "FALSE")
            self.assertEqual(
                self.raster._endpoint_url(), "https://raster.example.test:9443"
            )
            self.assertTrue(self.raster._use_ssl())

    def test_raster_boto_and_gdal_internal_http_explicit_opt_in(self):
        with (
            patch.object(self.raster, "S3_ENDPOINT", "http://sahool-minio:9000"),
            patch.object(self.raster, "S3_USE_SSL", "false"),
            patch.object(self.raster, "S3_BUCKET", "rasters"),
            patch.object(self.raster, "S3_ALLOW_PLAINTEXT_INTERNAL", "true"),
            patch.dict(os.environ, {}, clear=True),
        ):
            self.raster.gdal_configure()
            self.assertEqual(os.environ["AWS_S3_ENDPOINT"], "sahool-minio:9000")
            self.assertEqual(os.environ["AWS_HTTPS"], "NO")
            self.assertEqual(self.raster._endpoint_url(), "http://sahool-minio:9000")
            self.assertFalse(self.raster._use_ssl())

    def test_raster_fails_https_flag_mismatch(self):
        with (
            patch.object(self.raster, "S3_ENDPOINT", "https://raster.example.test"),
            patch.object(self.raster, "S3_USE_SSL", "false"),
        ):
            with self.assertRaisesRegex(
                self.raster.ObjectStoreUploadError, "scheme_flag_conflict"
            ):
                self.raster._endpoint_url()

    def test_raster_fails_external_http_even_dev_fallback(self):
        with (
            patch.object(self.raster, "S3_ENDPOINT", "http://minio.evil.test:9000"),
            patch.object(self.raster, "S3_USE_SSL", "false"),
            patch.object(self.raster, "S3_BUCKET", "rasters"),
            patch.object(self.raster, "S3_ALLOW_FILE_FALLBACK", "true"),
            patch.object(self.raster, "S3_ALLOW_PLAINTEXT_INTERNAL", "true"),
        ):
            with self.assertRaisesRegex(
                self.raster.ObjectStoreUploadError, "plaintext_external_forbidden"
            ):
                self.raster.upload_cog("/tmp/does-not-exist.tif", "foo.tif")

    def test_raster_bucket_missing_endpoint_no_local_dev_fallback(self):
        with (
            patch.object(self.raster, "S3_ENDPOINT", ""),
            patch.object(self.raster, "S3_BUCKET", "rasters"),
        ):
            with self.assertRaisesRegex(
                self.raster.ObjectStoreUploadError, "bucket configured without S3 endpoint"
            ):
                self.raster.upload_cog("/tmp/does-not-exist.tif", "foo.tif")

    def test_raster_hostname_substring_not_allowlisted(self):
        with (
            patch.object(self.raster, "S3_ENDPOINT", "http://sahool-minio.attacker.example"),
            patch.object(self.raster, "S3_USE_SSL", "false"),
            patch.object(self.raster, "S3_ALLOW_PLAINTEXT_INTERNAL", "true"),
        ):
            with self.assertRaisesRegex(
                self.raster.ObjectStoreUploadError, "plaintext_external_forbidden"
            ):
                self.raster._endpoint_url()

    def test_compose_current_four_s3_apps_explicit_internal_opt_in(self):
        txt = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
        self.assertEqual(
            txt.count("S3_ALLOW_PLAINTEXT_INTERNAL: ${S3_ALLOW_PLAINTEXT_INTERNAL:-false}"),
            4,
        )
        self.assertIn(
            "S3_ALLOW_PLAINTEXT_INTERNAL=true",
            (ROOT / ".env.example").read_text(encoding="utf-8"),
        )

    def test_no_external_network_in_helper(self):
        txt = (ROOT / "shared/storage/s3_endpoint_security.py").read_text(
            encoding="utf-8"
        )
        for bad in (
            "requests.get(",
            "socket.socket(",
            "getaddrinfo(",
            "boto3.client(",
        ):
            self.assertNotIn(bad, txt)


class ClientCallsiteTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"S3_BUCKET": "", "S3_ENDPOINT": ""}):
            self.blob = load_file(
                "shared/storage/blob_store.py", "candidate_blob_boto3"
            )
            self.raster = load_file(
                "services/raster-service/object_store.py", "candidate_raster_boto3"
            )

    def test_real_blob_client_constructor_receives_https(self):
        fake = ModuleType("boto3")
        calls = []

        def client(name, **kwargs):
            calls.append((name, kwargs))
            return object()

        fake.client = client  # type: ignore[attr-defined]
        with (
            patch.object(self.blob, "S3_ENDPOINT", "https://s3.vendor.test:9443"),
            patch.object(self.blob, "S3_USE_SSL", None),
            patch.dict(
                os.environ,
                {"S3_ACCESS_KEY": "fake_id", "S3_SECRET_KEY": "fake_secret"},
            ),
            patch.dict(sys.modules, {"boto3": fake}),
        ):
            self.blob._s3_client()
        assert len(calls) == 1, "boto3 client must be constructed exactly once"
        self.assertEqual(calls[0][0], "s3")
        self.assertEqual(calls[0][1]["endpoint_url"], "https://s3.vendor.test:9443")

    def test_real_raster_upload_file_client_https(self):
        fake = ModuleType("boto3")
        botocore = ModuleType("botocore")
        botocore_client = ModuleType("botocore.client")

        class Config:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        botocore_client.Config = Config  # type: ignore[attr-defined]
        calls = []

        class FakeS3:
            def head_bucket(self, **kwargs):
                calls.append(("head", kwargs))

            def upload_file(self, *args):
                calls.append(("upload", args))

        def client(name, **kwargs):
            calls.append(("client", name, kwargs))
            return FakeS3()

        fake.client = client  # type: ignore[attr-defined]
        with tempfile.TemporaryDirectory() as tmp:
            local = str(Path(tmp) / "cog.tif")
            Path(local).write_bytes(b"TIFF-test")
            with (
                patch.object(self.raster, "S3_ENDPOINT", "https://s3.vendor.test:9443"),
                patch.object(self.raster, "S3_USE_SSL", None),
                patch.object(self.raster, "S3_BUCKET", "rasters"),
                patch.object(self.raster, "S3_ACCESS_KEY", "fake_id"),
                patch.object(self.raster, "S3_SECRET_KEY", "fake_secret"),
                patch.dict(
                    sys.modules,
                    {
                        "boto3": fake,
                        "botocore": botocore,
                        "botocore.client": botocore_client,
                    },
                ),
            ):
                result = self.raster.upload_cog(local, "foo.tif")
            assert len(calls) == 3, "expected one client, one HEAD and one upload"
            self.assertEqual(result, "s3://rasters/foo.tif")
            self.assertEqual(calls[0][2]["endpoint_url"], "https://s3.vendor.test:9443")
            self.assertTrue(calls[0][2]["use_ssl"])
            self.assertEqual(calls[-1], ("upload", (local, "rasters", "foo.tif")))


if __name__ == "__main__":
    unittest.main()
