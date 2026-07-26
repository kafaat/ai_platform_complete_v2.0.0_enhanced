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


def _sign(
    *,
    worker=WORKER,
    method="GET",
    path=PATH,
    request_id="req-1",
    service=None,
    key=KEY,
    key_id="current",
    issued_at=None,
):
    return create_tenant_assertion(
        key,
        service or main.WORKER_ASSERTION_SERVICE,
        worker,
        key_id=key_id,
        method=method,
        path=path,
        request_id=request_id,
        issued_at=issued_at,
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


# ─────────────── WORKER-IDENTITY-HARDENING negative matrix ───────────────
# Each case is a distinct way a forged/stale/misconfigured assertion must fail closed. All exercise
# the real main._verify_worker_identity against the real shared verifier (no DB).


def _reject(monkeypatch, assertion, *, request=None, request_id="req-1", worker=WORKER):
    monkeypatch.setenv("DECISION_WORKER_ASSERTION_KEY", KEY)
    monkeypatch.delenv("DECISION_WORKER_ASSERTION_REDIS_URL", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    with pytest.raises(main.HTTPException) as ei:
        main._verify_worker_identity(
            request or _req(), worker, x_worker_assertion=assertion, x_request_id=request_id
        )
    return ei.value


def test_audience_service_mismatch_is_rejected(monkeypatch) -> None:
    # The server pins expected_service = WORKER_ASSERTION_SERVICE; a different service (audience)
    # in the assertion must not be accepted even with a correct signature.
    forged = _sign(service="some-other-service", request_id="a1")
    assert _reject(monkeypatch, forged, request_id="a1").status_code == 403


def test_method_mismatch_is_rejected(monkeypatch) -> None:
    # Signed for POST, request is GET → scope mismatch (assertions are method-bound).
    forged = _sign(method="POST", request_id="a2")
    assert (
        _reject(monkeypatch, forged, request=_req(method="GET"), request_id="a2").status_code == 403
    )


def test_expired_assertion_is_rejected(monkeypatch) -> None:
    import time

    stale = _sign(request_id="a3", issued_at=int(time.time()) - 3600)
    assert _reject(monkeypatch, stale, request_id="a3").status_code == 403


def test_not_yet_valid_future_assertion_is_rejected(monkeypatch) -> None:
    import time

    future = _sign(request_id="a4", issued_at=int(time.time()) + 3600)
    assert _reject(monkeypatch, future, request_id="a4").status_code == 403


def test_unknown_kid_is_rejected(monkeypatch) -> None:
    # A key id the server does not know (not current/previous) → unknown assertion key.
    forged = _sign(request_id="a5", key_id="attacker-kid")
    assert _reject(monkeypatch, forged, request_id="a5").status_code == 403


def test_wrong_key_signature_is_rejected(monkeypatch) -> None:
    # Correct kid ("current") but signed with a DIFFERENT key value → signature mismatch.
    forged = _sign(request_id="a6", key="a-different-worker-assertion-key-32chars!!")
    assert _reject(monkeypatch, forged, request_id="a6").status_code == 403


def test_previous_key_after_rotation_is_accepted(monkeypatch) -> None:
    # Key rotation: an assertion signed with the PREVIOUS key under the previous kid is still
    # accepted while the previous key is configured (so a rotation does not break in-flight callers).
    previous_key = "the-previous-worker-assertion-key-32chars!"
    monkeypatch.setenv("DECISION_WORKER_ASSERTION_KEY", KEY)
    monkeypatch.setenv("DECISION_WORKER_ASSERTION_PREVIOUS_KEY", previous_key)
    monkeypatch.setenv("DECISION_WORKER_ASSERTION_PREVIOUS_KEY_ID", "previous")
    monkeypatch.delenv("DECISION_WORKER_ASSERTION_REDIS_URL", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    signed = _sign(request_id="a7", key=previous_key, key_id="previous")
    # No raise = accepted under the previous kid.
    main._verify_worker_identity(_req(), WORKER, x_worker_assertion=signed, x_request_id="a7")


def test_production_replay_store_unavailable_fails_closed(monkeypatch) -> None:
    # In production a configured-but-unreachable replay store must fail closed (503) — a valid
    # signature is NOT enough if the nonce cannot be consumed exactly once.
    monkeypatch.setenv("DECISION_WORKER_ASSERTION_KEY", KEY)
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setenv("DECISION_WORKER_ASSERTION_REDIS_URL", "redis://127.0.0.1:1/0")
    with pytest.raises(main.HTTPException) as ei:
        main._verify_worker_identity(
            _req(), WORKER, x_worker_assertion=_sign(request_id="a8"), x_request_id="a8"
        )
    assert ei.value.status_code == 503
