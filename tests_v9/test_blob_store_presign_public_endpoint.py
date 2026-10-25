"""Presigned logbook URLs are signed for a host clients can resolve — or refused.

SEASON-LOGBOOK-PRESIGNED-URL-SIGNED-FOR-INTERNAL-MINIO-HOST-01: ``presigned_get_url``
signed with a client bound to ``S3_ENDPOINT`` (``http://sahool-minio:9000`` in Compose,
docker-compose.v9.yml), a name no browser resolves. SigV4 query signing covers the Host
header (``X-Amz-SignedHeaders=host``), so the host cannot be rewritten afterwards.

No network, no database. Two layers:

- recording fake ``boto3`` (always runs): which endpoint the signing client is bound to,
  and that internal-only signing hosts are refused before any client is built;
- real ``boto3``/``botocore`` when installed (offline: presigning makes no request, and
  sockets are blocked): the URL host is the public host, ``host`` is a signed header,
  and an independent SigV4 recomputation shows the signature verifies for the public
  host and not for the internal one.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import os
import socket
import sys
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
from urllib.parse import parse_qsl, quote, urlsplit

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
REF = "s3://sahool-scout-ingest/season-logbooks/t1/s1/page.jpg"
CREDS = {"S3_ACCESS_KEY": "AKIDEXAMPLE", "S3_SECRET_KEY": "wJalrXUtnFEMI-example-secret"}


def _load_blob(name: str):
    with patch.dict(os.environ, {"S3_BUCKET": "", "S3_ENDPOINT": ""}):
        spec = importlib.util.spec_from_file_location(name, ROOT / "shared/storage/blob_store.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


def _configure(stack: ExitStack, blob, **values) -> None:
    base = {
        "S3_BUCKET": "sahool-scout-ingest",
        "S3_ENDPOINT": "http://sahool-minio:9000",
        "S3_USE_SSL": "false",
        "S3_ALLOW_PLAINTEXT_INTERNAL": "true",
        "S3_ALLOW_PLAINTEXT_LOOPBACK": "false",
        "S3_PUBLIC_ENDPOINT": "",
    }
    base.update(values)
    for attr, value in base.items():
        stack.enter_context(patch.object(blob, attr, value, create=True))
    stack.enter_context(patch.dict(os.environ, CREDS))


class _FakeBoto:
    """Records ``boto3.client`` kwargs; the client signs a URL for the bound endpoint."""

    def __init__(self, url_host: str | None = None):
        self.calls: list[dict] = []
        self.url_host = url_host

    def modules(self) -> dict[str, ModuleType]:
        boto3 = ModuleType("boto3")
        botocore = ModuleType("botocore")
        botocore_client = ModuleType("botocore.client")

        class Config:
            def __init__(self, **kw):
                self.kw = kw

        recorder = self

        class Client:
            def __init__(self, endpoint_url):
                self.endpoint_url = endpoint_url

            def generate_presigned_url(self, op, Params, ExpiresIn):
                root = self.endpoint_url
                if recorder.url_host is not None:
                    root = f"https://{recorder.url_host}"
                return (
                    f"{root}/{Params['Bucket']}/{Params['Key']}"
                    f"?X-Amz-Expires={ExpiresIn}&X-Amz-SignedHeaders=host&X-Amz-Signature=x"
                )

        def client(name, **kwargs):
            recorder.calls.append(kwargs)
            return Client(kwargs["endpoint_url"])

        boto3.client = client
        botocore_client.Config = Config
        return {"boto3": boto3, "botocore": botocore, "botocore.client": botocore_client}


@pytest.fixture
def blob():
    return _load_blob("candidate_blob_presign_public")


def _with_fake(stack: ExitStack, fake: _FakeBoto) -> None:
    stack.enter_context(patch.dict(sys.modules, fake.modules()))


# ── signing client is bound to the public endpoint ────────────────────────────────


def test_presign_client_is_bound_to_public_endpoint(blob):
    fake = _FakeBoto()
    with ExitStack() as stack:
        _configure(stack, blob, S3_PUBLIC_ENDPOINT="https://files.sahool.example:9443")
        _with_fake(stack, fake)
        url = blob.presigned_get_url(REF, 300)
    assert [c["endpoint_url"] for c in fake.calls] == ["https://files.sahool.example:9443"]
    assert urlsplit(url).hostname == "files.sahool.example"
    assert fake.calls[0]["config"].kw["s3"] == {"addressing_style": "path"}


def test_public_endpoint_ignores_internal_ssl_flag(blob):
    """S3_USE_SSL=false describes the internal hop; it must not veto an https public origin."""
    fake = _FakeBoto()
    with ExitStack() as stack:
        _configure(stack, blob, S3_USE_SSL="false", S3_PUBLIC_ENDPOINT="files.sahool.example")
        _with_fake(stack, fake)
        blob.presigned_get_url(REF, 300)
    # A bare host defaults to HTTPS, exactly as for S3_ENDPOINT.
    assert fake.calls[0]["endpoint_url"] == "https://files.sahool.example"


def test_upload_and_head_still_use_internal_endpoint(blob):
    fake = _FakeBoto()
    with ExitStack() as stack:
        _configure(stack, blob, S3_PUBLIC_ENDPOINT="https://files.sahool.example")
        _with_fake(stack, fake)
        blob._s3_client()
    assert fake.calls[0]["endpoint_url"] == "http://sahool-minio:9000"


# ── fail-closed without a public endpoint ─────────────────────────────────────────


@pytest.mark.parametrize(
    "endpoint, extra",
    [
        ("http://sahool-minio:9000", {}),
        ("https://sahool-minio:9000", {"S3_USE_SSL": None}),
        ("https://sahool-minio.railway.internal:9000", {"S3_USE_SSL": None}),
        ("https://minio.storage.svc", {"S3_USE_SSL": None}),
        ("https://minio.storage.svc.cluster.local:9000", {"S3_USE_SSL": None}),
        ("https://objectstore:9000", {"S3_USE_SSL": None}),
    ],
)
def test_internal_signing_host_refused_without_public_endpoint(blob, endpoint, extra):
    fake = _FakeBoto()
    with ExitStack() as stack:
        _configure(stack, blob, S3_ENDPOINT=endpoint, **extra)
        _with_fake(stack, fake)
        with pytest.raises(blob.BlobStoreError, match="presign refused"):
            blob.presigned_get_url(REF, 300)
    assert fake.calls == []  # refused before any client is built


@pytest.mark.parametrize(
    "endpoint, extra, host",
    [
        ("https://s3.vendor.example:9443", {"S3_USE_SSL": None}, "s3.vendor.example"),
        # Loopback is allowed on purpose: a store the service reaches on loopback runs on
        # the developer's own machine, where the browser is too. HTTP needs the opt-in.
        (
            "http://localhost:9000",
            {"S3_ALLOW_PLAINTEXT_LOOPBACK": "true"},
            "localhost",
        ),
        (
            "http://127.0.0.1:9000",
            {"S3_ALLOW_PLAINTEXT_LOOPBACK": "true"},
            "127.0.0.1",
        ),
    ],
)
def test_client_resolvable_signing_host_presigns_without_public_endpoint(
    blob, endpoint, extra, host
):
    fake = _FakeBoto()
    with ExitStack() as stack:
        _configure(stack, blob, S3_ENDPOINT=endpoint, **extra)
        _with_fake(stack, fake)
        url = blob.presigned_get_url(REF, 300)
    assert urlsplit(url).hostname == host


# ── the public endpoint is held to the same policy as S3_ENDPOINT ─────────────────


@pytest.mark.parametrize(
    "public, extra, match",
    [
        ("http://files.sahool.example", {}, "plaintext_external_forbidden"),
        ("https://user:pw@files.sahool.example", {}, "userinfo_forbidden"),
        ("https://files.sahool.example/minio", {}, "endpoint_must_be_host_only"),
        ("ftp://files.sahool.example", {}, "unsupported_scheme"),
        ("https://sahool-scout-ingest.files.example", {}, "bucket_prefixed_endpoint"),
        ("http://localhost:9000", {}, "plaintext_loopback_requires_opt_in"),
        # Plaintext-internal is never honoured for the public origin.
        ("http://sahool-minio:9000", {}, "plaintext_internal_requires_opt_in"),
        ("https://sahool-minio:9000", {}, "internal-only host"),
        ("https://sahool-minio.railway.internal", {}, "internal-only host"),
    ],
)
def test_unsafe_public_endpoint_is_refused(blob, public, extra, match):
    fake = _FakeBoto()
    with ExitStack() as stack:
        _configure(stack, blob, S3_PUBLIC_ENDPOINT=public, **extra)
        _with_fake(stack, fake)
        with pytest.raises(blob.BlobStoreError, match=match) as exc:
            blob.presigned_get_url(REF, 300)
    assert fake.calls == []
    assert "pw" not in str(exc.value)


def test_url_for_a_host_other_than_the_signing_host_is_refused(blob):
    fake = _FakeBoto(url_host="sahool-scout-ingest.files.sahool.example")
    with ExitStack() as stack:
        _configure(stack, blob, S3_PUBLIC_ENDPOINT="https://files.sahool.example")
        _with_fake(stack, fake)
        with pytest.raises(blob.BlobStoreError, match="other than the signing host"):
            blob.presigned_get_url(REF, 300)


# ── unchanged behaviour ───────────────────────────────────────────────────────────


def test_file_ref_dev_behaviour_unchanged(blob):
    with ExitStack() as stack:
        _configure(stack, blob, S3_BUCKET="", S3_PUBLIC_ENDPOINT="https://files.sahool.example")
        ref = "file:///tmp/sahool-logbooks/season-logbooks/t1/s1/page.jpg"
        assert blob.presigned_get_url(ref, 300) == ref


def test_ttl_contract_checked_before_endpoint(blob):
    with ExitStack() as stack:
        _configure(stack, blob)
        with pytest.raises(blob.BlobStoreError, match="presign TTL out of contract"):
            blob.presigned_get_url(REF, 301)


def test_route_maps_store_refusal_to_503():
    """The route turns BlobStoreError into the existing 503, never a 200 with a dead URL."""
    src = (ROOT / "services/scout-ingest-service/season_api.py").read_text(encoding="utf-8")
    call = src.index("blob_store.presigned_get_url(ref, PRESIGN_TTL_S)")
    handler = src[call : call + 300]
    assert "except blob_store.BlobStoreError" in handler
    assert 'status_code=503, detail="logbook_store_unavailable"' in handler


# ── real botocore, offline ────────────────────────────────────────────────────────


def _sigv4_query_signature(url: str, host_header: str, secret: str) -> str:
    """Independent SigV4 query-string signature (S3 presigned GET, UNSIGNED-PAYLOAD)."""
    parts = urlsplit(url)
    params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    query = "&".join(
        f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}"
        for k, v in sorted(params)
        if k != "X-Amz-Signature"
    )
    q = dict(params)
    signed = q["X-Amz-SignedHeaders"]
    assert signed == "host"
    canonical = "\n".join(
        ["GET", parts.path, query, f"host:{host_header}\n", signed, "UNSIGNED-PAYLOAD"]
    )
    _, date, region, service, term = q["X-Amz-Credential"].split("/")
    scope = f"{date}/{region}/{service}/{term}"
    to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            q["X-Amz-Date"],
            scope,
            hashlib.sha256(canonical.encode()).hexdigest(),
        ]
    )
    key = ("AWS4" + secret).encode()
    for part in (date, region, service, term):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    return hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()


def test_real_botocore_signs_for_the_public_host_offline(blob):
    pytest.importorskip("boto3")
    pytest.importorskip("botocore")

    def _no_network(*_a, **_k):
        raise AssertionError("presigning must not open a connection")

    with ExitStack() as stack:
        _configure(stack, blob, S3_PUBLIC_ENDPOINT="https://files.sahool.example:9443")
        stack.enter_context(patch.dict(os.environ, {"AWS_DEFAULT_REGION": "us-east-1"}))
        stack.enter_context(patch.object(socket.socket, "connect", _no_network))
        url = blob.presigned_get_url(REF, 300)

    parts = urlsplit(url)
    q = dict(parse_qsl(parts.query))
    assert parts.hostname == "files.sahool.example"
    assert parts.port == 9443
    assert parts.path == "/sahool-scout-ingest/season-logbooks/t1/s1/page.jpg"
    assert "host" in q["X-Amz-SignedHeaders"].split(";")
    assert q["X-Amz-Expires"] == "300"
    secret = CREDS["S3_SECRET_KEY"]
    # Valid for the host the browser sends …
    assert _sigv4_query_signature(url, parts.netloc, secret) == q["X-Amz-Signature"]
    # … and invalid for the internal host: a host rewrite cannot rescue a URL.
    assert _sigv4_query_signature(url, "sahool-minio:9000", secret) != q["X-Amz-Signature"]
