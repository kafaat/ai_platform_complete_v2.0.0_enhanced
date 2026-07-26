"""Pin the adapter's vendored worker-assertion signer to the shared decision-service verifier.

The model-registry-adapter vendors ``worker_assertion.create_worker_assertion`` (its image ships no
``shared/``). This round-trips a signed assertion through the REAL
``shared.security.service_tenant_assertion.verify_tenant_assertion`` — the exact verifier the
decision-service worker endpoints use — so any format drift (VERSION, field order, delimiter) fails
here instead of silently breaking worker auth in production.

Lives in ``tests_v9`` (not the adapter's own ``tests/``) so it runs in the mandatory unit gate and
so importing ``shared`` here never trips the Dockerfile-shared-copy guard (the signer stays vendored
in the adapter image; only this cross-boundary contract test reaches ``shared``).
"""

from __future__ import annotations

import pathlib
import sys

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTER_DIR = REPO_ROOT / "services" / "model-registry-adapter"
for p in (str(ADAPTER_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from worker_assertion import create_worker_assertion  # noqa: E402

from shared.security.service_tenant_assertion import (  # noqa: E402
    TenantAssertionError,
    verify_tenant_assertion,
)

KEY = "worker-assertion-key-least-32-characters-long!!"
SERVICE = "model-registry-adapter"
WORKER = "adapter-alpha"
PATH = "/v1/learning/runtime-work"


def _verify(assertion: str, *, subject=WORKER, method="GET", path=PATH, request_id="rid-1"):
    return verify_tenant_assertion(
        assertion,
        {"current": KEY},
        SERVICE,
        subject,
        expected_method=method,
        expected_path=path,
        expected_request_id=request_id,
    )


def test_signed_assertion_verifies_with_shared_module() -> None:
    assertion = create_worker_assertion(
        KEY, SERVICE, WORKER, method="GET", path=PATH, request_id="rid-1"
    )
    claims = _verify(assertion)
    assert claims.service == SERVICE
    assert claims.tenant_id == WORKER  # subject rides the tenant_id slot
    assert claims.method == "GET"
    assert claims.path == PATH
    assert claims.request_id == "rid-1"


def test_tampered_subject_fails_shared_scope_check() -> None:
    assertion = create_worker_assertion(
        KEY, SERVICE, WORKER, method="GET", path=PATH, request_id="rid-2"
    )
    with pytest.raises(TenantAssertionError):
        _verify(assertion, subject="adapter-beta", request_id="rid-2")


def test_short_key_is_rejected_at_signing() -> None:
    with pytest.raises(ValueError):
        create_worker_assertion(
            "too-short", SERVICE, WORKER, method="GET", path=PATH, request_id="x"
        )
