"""WORKER-IDENTITY-BINDING (behavioral, no DB): a caller must prove it IS the worker_id.

Exercises the real ``main._verify_worker_identity`` against the real shared assertion creator:
a valid assertion for the presented worker passes; a forged/absent/other-worker/other-request
assertion fails closed (403); production without a key is 503; development without a key retains
header-only compatibility (no-op). Pure decision, no Postgres — runs in the Decision Service
Tests job alongside the other no-DB guards.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from shared.security.service_tenant_assertion import create_tenant_assertion  # noqa: E402

KEY = "worker-assertion-key-least-32-characters-long!!"
WORKER = "adapter-alpha"
PATH = "/v1/learning/runtime-work"


def _req(method: str = "GET", path: str = PATH):
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path))


def _sign(*, worker=WORKER, method="GET", path=PATH, request_id="req-1", service=None):
    return create_tenant_assertion(
        KEY,
        service or main.WORKER_ASSERTION_SERVICE,
        worker,
        method=method,
        path=path,
        request_id=request_id,
    )


def test_valid_assertion_passes(monkeypatch) -> None:
    monkeypatch.setenv("DECISION_WORKER_ASSERTION_KEY", KEY)
    monkeypatch.delenv("DECISION_WORKER_ASSERTION_REDIS_URL", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    # No raise = accepted.
    main._verify_worker_identity(
        _req(), WORKER, x_worker_assertion=_sign(request_id="r1"), x_request_id="r1"
    )


def test_absent_assertion_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("DECISION_WORKER_ASSERTION_KEY", KEY)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    with pytest.raises(main.HTTPException) as ei:
        main._verify_worker_identity(_req(), WORKER, x_worker_assertion=None, x_request_id="r1")
    assert ei.value.status_code == 403


def test_other_worker_subject_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("DECISION_WORKER_ASSERTION_KEY", KEY)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    # A valid assertion for a DIFFERENT worker must not authorize this worker_id.
    forged = _sign(worker="adapter-beta", request_id="r2")
    with pytest.raises(main.HTTPException) as ei:
        main._verify_worker_identity(_req(), WORKER, x_worker_assertion=forged, x_request_id="r2")
    assert ei.value.status_code == 403


def test_request_id_or_path_mismatch_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("DECISION_WORKER_ASSERTION_KEY", KEY)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    signed = _sign(path="/v1/learning/runtime-work", request_id="r3")
    # Same assertion, but the actual request path differs → scope mismatch.
    with pytest.raises(main.HTTPException) as ei:
        main._verify_worker_identity(
            _req(path="/v1/learning/runtime-workers/adapter-alpha/tenants"),
            WORKER,
            x_worker_assertion=signed,
            x_request_id="r3",
        )
    assert ei.value.status_code == 403


def test_production_without_key_is_503(monkeypatch) -> None:
    monkeypatch.delenv("DECISION_WORKER_ASSERTION_KEY", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "production")
    with pytest.raises(main.HTTPException) as ei:
        main._verify_worker_identity(_req(), WORKER, x_worker_assertion=None, x_request_id="r1")
    assert ei.value.status_code == 503


def test_development_without_key_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("DECISION_WORKER_ASSERTION_KEY", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    # Header-only compatibility: no key configured ⇒ no enforcement (existing installs).
    main._verify_worker_identity(_req(), WORKER, x_worker_assertion=None, x_request_id=None)
