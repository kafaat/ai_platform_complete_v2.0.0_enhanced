"""S3 endpoint policy at the real boto3 and GDAL seams (blob_store, raster object_store).

No network, no real S3 client, no database. The modules under test are loaded from
this checkout; boto3/botocore are replaced by recording fakes where a client is built.
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


def load_file(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def patched(stack, module, **values):
    for attr, value in values.items():
        stack.enter_context(patch.object(module, attr, value))


class ActualS3IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"S3_BUCKET": "", "S3_ENDPOINT": ""}):
            cls.blob = load_file("shared/storage/blob_store.py", "candidate_sahool_blob_store")
            cls.raster = load_file(
                "services/raster-service/object_store.py", "candidate_sahool_raster_store"
            )

    def test_blob_preserves_explicit_https_when_flag_unset(self):
        with ExitStack() as stack:
            patched(
                stack, self.blob, S3_ENDPOINT="https://storage.example.test:9443", S3_USE_SSL=None
            )
            self.assertEqual(self.blob._endpoint_url(), "https://storage.example.test:9443")
            self.assertTrue(self.blob._use_ssl())

    def test_blob_fails_closed_explicit_https_with_false_flag(self):
        with ExitStack() as stack:
            patched(
                stack,
                self.blob,
                S3_ENDPOINT="https://storage.example.test:9443",
                S3_USE_SSL="false",
            )
            with self.assertRaisesRegex(self.blob.BlobStoreError, "scheme_flag_conflict"):
                self.blob._endpoint_url()

    def test_blob_http_external_denied_despite_internal_opt_in(self):
        with ExitStack() as stack:
            patched(
                stack,
                self.blob,
                S3_ENDPOINT="http://minio.bad-domain.example:9000",
                S3_USE_SSL="false",
                S3_ALLOW_PLAINTEXT_INTERNAL="true",
            )
            with self.assertRaisesRegex(self.blob.BlobStoreError, "plaintext_external_forbidden"):
                self.blob._endpoint_url()

    def test_blob_internal_http_explicit_opt_in_required(self):
        with ExitStack() as stack:
            patched(stack, self.blob, S3_ENDPOINT="http://sahool-minio:9000", S3_USE_SSL="false")
            with patch.object(self.blob, "S3_ALLOW_PLAINTEXT_INTERNAL", "false"):
                with self.assertRaisesRegex(
                    self.blob.BlobStoreError, "plaintext_internal_requires_opt_in"
                ):
                    self.blob._endpoint_url()
            with patch.object(self.blob, "S3_ALLOW_PLAINTEXT_INTERNAL", "true"):
                self.assertEqual(self.blob._endpoint_url(), "http://sahool-minio:9000")

    def test_blob_bad_endpoint_no_file_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            patched(
                stack,
                self.blob,
                S3_ENDPOINT="http://external.example:9000",
                S3_USE_SSL="false",
                S3_BUCKET="bucket",
                S3_ALLOW_FILE_FALLBACK="true",
                LOCAL_DIR=tmp,
            )
            with self.assertRaisesRegex(self.blob.BlobStoreError, "plaintext_external_forbidden"):
                self.blob.upload_bytes("x/test.bin", b"SECRET", "application/octet-stream")
            self.assertEqual(list(Path(tmp).rglob("*")), [])

    def test_blob_endpoint_userinfo_rejected_without_echoing_credentials(self):
        with ExitStack() as stack:
            patched(
                stack,
                self.blob,
                S3_ENDPOINT="https://user:pass@storage.example.test",
                S3_USE_SSL=None,
            )
            with self.assertRaisesRegex(self.blob.BlobStoreError, "userinfo_forbidden") as cm:
                self.blob._endpoint_url()
            self.assertNotIn("pass", str(cm.exception))

    def test_blob_presign_ttl_existing_contract(self):
        with self.assertRaisesRegex(self.blob.BlobStoreError, "presign TTL out of contract"):
            self.blob.presigned_get_url("s3://bucket/test", 301)

    def test_raster_boto_and_gdal_https_decisions_are_same(self):
        with ExitStack() as stack:
            patched(
                stack,
                self.raster,
                S3_ENDPOINT="https://raster.example.test:9443",
                S3_USE_SSL=None,
                S3_BUCKET="rasters",
            )
            stack.enter_context(patch.dict(os.environ, {}, clear=True))
            self.raster.gdal_configure()
            self.assertEqual(os.environ["AWS_S3_ENDPOINT"], "raster.example.test:9443")
            self.assertEqual(os.environ["AWS_HTTPS"], "YES")
            self.assertEqual(os.environ["AWS_VIRTUAL_HOSTING"], "FALSE")
            self.assertEqual(self.raster._endpoint_url(), "https://raster.example.test:9443")
            self.assertTrue(self.raster._use_ssl())

    def test_raster_boto_and_gdal_internal_http_explicit_opt_in(self):
        with ExitStack() as stack:
            patched(
                stack,
                self.raster,
                S3_ENDPOINT="http://sahool-minio:9000",
                S3_USE_SSL="false",
                S3_BUCKET="rasters",
                S3_ALLOW_PLAINTEXT_INTERNAL="true",
            )
            stack.enter_context(patch.dict(os.environ, {}, clear=True))
            self.raster.gdal_configure()
            self.assertEqual(os.environ["AWS_S3_ENDPOINT"], "sahool-minio:9000")
            self.assertEqual(os.environ["AWS_HTTPS"], "NO")
            self.assertEqual(self.raster._endpoint_url(), "http://sahool-minio:9000")
            self.assertFalse(self.raster._use_ssl())

    def test_raster_fails_https_flag_mismatch(self):
        with ExitStack() as stack:
            patched(
                stack, self.raster, S3_ENDPOINT="https://raster.example.test", S3_USE_SSL="false"
            )
            with self.assertRaisesRegex(self.raster.ObjectStoreUploadError, "scheme_flag_conflict"):
                self.raster._endpoint_url()

    def test_raster_fails_external_http_even_dev_fallback(self):
        with ExitStack() as stack:
            patched(
                stack,
                self.raster,
                S3_ENDPOINT="http://minio.evil.test:9000",
                S3_USE_SSL="false",
                S3_BUCKET="rasters",
                S3_ALLOW_FILE_FALLBACK="true",
                S3_ALLOW_PLAINTEXT_INTERNAL="true",
            )
            with self.assertRaisesRegex(
                self.raster.ObjectStoreUploadError, "plaintext_external_forbidden"
            ):
                self.raster.upload_cog("/tmp/does-not-exist.tif", "foo.tif")

    def test_raster_bucket_missing_endpoint_no_local_dev_fallback(self):
        with ExitStack() as stack:
            patched(stack, self.raster, S3_ENDPOINT="", S3_BUCKET="rasters")
            with self.assertRaisesRegex(
                self.raster.ObjectStoreUploadError, "bucket configured without S3 endpoint"
            ):
                self.raster.upload_cog("/tmp/does-not-exist.tif", "foo.tif")

    def test_raster_hostname_substring_not_allowlisted(self):
        with ExitStack() as stack:
            patched(
                stack,
                self.raster,
                S3_ENDPOINT="http://sahool-minio.attacker.example",
                S3_USE_SSL="false",
                S3_ALLOW_PLAINTEXT_INTERNAL="true",
            )
            with self.assertRaisesRegex(
                self.raster.ObjectStoreUploadError, "plaintext_external_forbidden"
            ):
                self.raster._endpoint_url()

    def test_compose_current_four_s3_apps_explicit_internal_opt_in(self):
        txt = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
        self.assertEqual(
            txt.count("S3_ALLOW_PLAINTEXT_INTERNAL: ${S3_ALLOW_PLAINTEXT_INTERNAL:-false}"), 4
        )
        self.assertIn(
            "S3_ALLOW_PLAINTEXT_INTERNAL=true", (ROOT / ".env.example").read_text(encoding="utf-8")
        )

    def test_no_external_network_in_helper(self):
        txt = (ROOT / "shared/storage/s3_endpoint_security.py").read_text(encoding="utf-8")
        for bad in ("requests.get(", "socket.socket(", "getaddrinfo(", "boto3.client("):
            self.assertNotIn(bad, txt)


class ClientCallsiteTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {"S3_BUCKET": "", "S3_ENDPOINT": ""}):
            self.blob = load_file("shared/storage/blob_store.py", "candidate_blob_boto3")
            self.raster = load_file(
                "services/raster-service/object_store.py", "candidate_raster_boto3"
            )

    def test_real_blob_client_constructor_receives_https_and_path_style(self):
        fake = ModuleType("boto3")
        botocore = ModuleType("botocore")
        botocore_client = ModuleType("botocore.client")

        class Config:
            def __init__(self, **kw):
                self.kw = kw

        botocore_client.Config = Config
        calls = []

        def client(name, **kwargs):
            calls.append((name, kwargs))
            return object()

        fake.client = client
        with ExitStack() as stack:
            patched(stack, self.blob, S3_ENDPOINT="https://s3.vendor.test:9443", S3_USE_SSL=None)
            stack.enter_context(
                patch.dict(os.environ, {"S3_ACCESS_KEY": "fake_id", "S3_SECRET_KEY": "fake_secret"})
            )
            stack.enter_context(
                patch.dict(
                    sys.modules,
                    {"boto3": fake, "botocore": botocore, "botocore.client": botocore_client},
                )
            )
            self.blob._s3_client()
            self.assertEqual(calls[0][0], "s3")
            self.assertEqual(calls[0][1]["endpoint_url"], "https://s3.vendor.test:9443")
            # The bucket goes in the path, never in the host (MinIO has no per-bucket DNS).
            self.assertEqual(calls[0][1]["config"].kw["s3"], {"addressing_style": "path"})

    def test_real_raster_upload_file_client_https(self):
        fake = ModuleType("boto3")
        botocore = ModuleType("botocore")
        botocore_client = ModuleType("botocore.client")

        class Config:
            def __init__(self, **kw):
                self.kw = kw

        botocore_client.Config = Config
        calls = []

        class FakeS3:
            def head_bucket(self, **kwargs):
                calls.append(("head", kwargs))

            def upload_file(self, *args):
                calls.append(("upload", args))

        def client(name, **kwargs):
            calls.append(("client", name, kwargs))
            return FakeS3()

        fake.client = client
        with tempfile.TemporaryDirectory() as t, ExitStack() as stack:
            local = str(Path(t) / "cog.tif")
            Path(local).write_bytes(b"TIFF-test")
            patched(
                stack,
                self.raster,
                S3_ENDPOINT="https://s3.vendor.test:9443",
                S3_USE_SSL=None,
                S3_BUCKET="rasters",
                S3_ACCESS_KEY="fake_id",
                S3_SECRET_KEY="fake_secret",
            )
            stack.enter_context(
                patch.dict(
                    sys.modules,
                    {"boto3": fake, "botocore": botocore, "botocore.client": botocore_client},
                )
            )
            result = self.raster.upload_cog(local, "foo.tif")
            self.assertEqual(result, "s3://rasters/foo.tif")
            self.assertEqual(calls[0][2]["endpoint_url"], "https://s3.vendor.test:9443")
            self.assertTrue(calls[0][2]["use_ssl"])
            self.assertEqual(calls[-1], ("upload", (local, "rasters", "foo.tif")))


# ── The parser itself: accepted forms, and rejections that must stay fixed codes ──
_POLICY = load_file("shared/storage/s3_endpoint_security.py", "candidate_s3_endpoint_policy")


@pytest.mark.parametrize(
    ("endpoint", "ssl", "loopback", "expected"),
    [
        ("s3.example.test", None, False, "https://s3.example.test"),
        ("HTTPS://S3.Example.Test:9443", None, False, "https://s3.example.test:9443"),
        ("https://[2001:db8::1]:9443", None, False, "https://[2001:db8::1]:9443"),
        ("http://localhost:9000", "false", True, "http://localhost:9000"),
        ("http://127.0.0.1:9000", None, True, "http://127.0.0.1:9000"),
    ],
)
def test_policy_accepts(endpoint, ssl, loopback, expected):
    decision = _POLICY.resolve_configured_s3_endpoint(endpoint, ssl, None, loopback)
    assert decision.endpoint_url == expected


@pytest.mark.parametrize(
    ("endpoint", "code"),
    [
        ("https://[::1", "invalid_host"),
        ("https://[v1.x]", "invalid_host"),
        ("http://[sahool-minio]:9000", "invalid_host"),
        ("https://-bad-.com", "invalid_dns_label"),
        ("https://1.2.3.4.5", "invalid_dns_label"),
        ("http://0x7f.1:9000", "invalid_dns_label"),
        ("http://2130706433:9000", "invalid_dns_label"),
        ("http://evil.com.localhost:9000", "plaintext_external_forbidden"),
        ("https://host.example:0", "invalid_port"),
        ("https://host.example:65536", "invalid_port"),
        ("https://host.example/bucket", "endpoint_must_be_host_only"),
        ("https://host.example?x=1", "endpoint_must_be_host_only"),
        ("ftp://host.example", "unsupported_scheme"),
    ],
)
def test_policy_rejects_with_a_fixed_code(endpoint, code):
    # Both opt-ins on: the rejection must come from the endpoint itself.
    with pytest.raises(_POLICY.EndpointPolicyError) as info:
        _POLICY.resolve_configured_s3_endpoint(endpoint, None, True, True)
    assert str(info.value) == code


@pytest.mark.parametrize(
    "endpoint",
    ["https://user:[s3cr3t]@host.example", "https://minio:s3cr3t", "https://[::1]s3cr3t"],
)
def test_policy_error_never_carries_the_input(endpoint):
    with pytest.raises(_POLICY.EndpointPolicyError) as info:
        _POLICY.resolve_configured_s3_endpoint(endpoint, None, True, True)
    assert "s3cr3t" not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__


if __name__ == "__main__":
    unittest.main()
