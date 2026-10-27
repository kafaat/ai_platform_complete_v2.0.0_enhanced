"""A rejected S3 endpoint names the setting that fixes it, without ever quoting the input.

The policy error itself stays a fixed code (``str(exc) == code``); the hint is a separate,
static ASCII string appended only where the error is reported (blob_store, raster
object_store, the GDAL entry gate). A local Compose upgrade that kept an old ``.env``
used to stop at ``plaintext_internal_requires_opt_in`` with no pointer to
``S3_ALLOW_PLAINTEXT_INTERNAL``.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GATE = ROOT / "shared" / "storage" / "gdal_s3_env_gate.py"


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def policy():
    return _load("shared/storage/s3_endpoint_security.py", "hint_test_s3_policy")


@pytest.fixture(scope="module")
def stores():
    with patch.dict(os.environ, {"S3_BUCKET": "", "S3_ENDPOINT": ""}):
        blob = _load("shared/storage/blob_store.py", "hint_test_blob_store")
        raster = _load("services/raster-service/object_store.py", "hint_test_raster_store")
    return blob, raster


def test_internal_plaintext_hint_names_the_opt_in_variable(policy):
    hint = policy.hint_for("plaintext_internal_requires_opt_in")
    assert "S3_ALLOW_PLAINTEXT_INTERNAL=true" in hint
    assert "sahool-minio" in hint


def test_every_hint_is_static_ascii_and_keyed_by_a_real_code(policy):
    source = (ROOT / "shared/storage/s3_endpoint_security.py").read_text(encoding="utf-8")
    for code, hint in policy.ENDPOINT_ERROR_HINTS.items():
        # A hint for a code the policy never raises would be dead text.
        assert f'EndpointPolicyError("{code}")' in source, code
        # Windows consoles decode stderr with a legacy code page: non-ASCII breaks there.
        assert hint.isascii(), code
        assert hint.strip() == hint and hint, code


def test_unknown_code_gets_no_hint(policy):
    assert policy.hint_for("no_such_code") == ""
    assert policy.hint_for(None) == ""


def test_policy_error_text_stays_the_bare_code(policy):
    with pytest.raises(policy.EndpointPolicyError) as exc:
        policy.resolve_configured_s3_endpoint("http://sahool-minio:9000", None, None, None)
    assert str(exc.value) == "plaintext_internal_requires_opt_in"


def test_blob_store_error_carries_the_hint(stores):
    blob, _ = stores
    with ExitStack() as stack:
        for attr, value in {
            "S3_ENDPOINT": "http://sahool-minio:9000",
            "S3_USE_SSL": None,
            "S3_ALLOW_PLAINTEXT_INTERNAL": "false",
        }.items():
            stack.enter_context(patch.object(blob, attr, value))
        with pytest.raises(blob.BlobStoreError) as exc:
            blob._endpoint_url()
    msg = str(exc.value)
    assert "plaintext_internal_requires_opt_in" in msg
    assert "S3_ALLOW_PLAINTEXT_INTERNAL=true" in msg


def test_raster_object_store_error_carries_the_hint(stores):
    _, raster = stores
    with ExitStack() as stack:
        for attr, value in {
            "S3_ENDPOINT": "http://sahool-minio:9000",
            "S3_USE_SSL": None,
            "S3_ALLOW_PLAINTEXT_INTERNAL": "false",
        }.items():
            stack.enter_context(patch.object(raster, attr, value))
        with pytest.raises(raster.ObjectStoreUploadError) as exc:
            raster._s3_endpoint_decision()
    msg = str(exc.value)
    assert "plaintext_internal_requires_opt_in" in msg
    assert "S3_ALLOW_PLAINTEXT_INTERNAL=true" in msg


def test_gdal_gate_stderr_carries_the_hint_and_no_input():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("S3_", "AWS_"))}
    env.update({"S3_ENDPOINT": "http://sahool-minio:9000", "S3_BUCKET": "sahool-rasters"})
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(GATE), sys.executable, "-c", "print('ran')"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 78, result.stderr
    assert "plaintext_internal_requires_opt_in" in result.stderr
    assert "S3_ALLOW_PLAINTEXT_INTERNAL=true" in result.stderr
    assert "ran" not in result.stdout
    # The hint is static: the configured endpoint is never echoed back.
    assert "sahool-minio:9000" not in result.stderr
