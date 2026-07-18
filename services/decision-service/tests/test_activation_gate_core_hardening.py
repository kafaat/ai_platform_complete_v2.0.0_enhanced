from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from activation_gate_core import (
    ActivationGateCore,
    ActivationProbeDenied,
    GateConfig,
    deploy_build_sha,
)


def _core() -> ActivationGateCore:
    return ActivationGateCore(
        GateConfig("g", "t", "e", frozenset({"c"}), frozenset({"p"}), "probe", "v1")
    )


def test_deploy_build_sha_is_fail_closed(monkeypatch):
    monkeypatch.delenv("DEPLOY_BUILD_SHA", raising=False)
    with pytest.raises(RuntimeError):
        deploy_build_sha()
    monkeypatch.setenv("DEPLOY_BUILD_SHA", "a" * 40)
    assert deploy_build_sha() == "a" * 40


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "not-hex-value", "abc123", "g" * 40, "a" * 39, "a" * 41, "a" * 63, "a" * 65],
)
def test_deploy_build_sha_rejects_absent_or_invalid_identity(monkeypatch, bad):
    # Condition-1: an absent OR malformed build identity (wrong length / non-hex) fails closed —
    # the gate cannot operate against an unknown build. Only 40- or 64-char lowercase hex passes.
    monkeypatch.setenv("DEPLOY_BUILD_SHA", bad)
    with pytest.raises(RuntimeError):
        deploy_build_sha()


def test_gate_build_sha_fails_closed_when_deploy_identity_invalid(monkeypatch):
    # The failure propagates through the gate operation that binds a verdict to the build: an
    # invalid DEPLOY_BUILD_SHA makes build_sha() raise rather than fingerprint against nothing.
    item = {
        "producer": "p",
        "check_name": "c",
        "provenance": "ci",
        "valid_until": "x",
        "build_sha": "d" * 40,
    }
    monkeypatch.setenv("DEPLOY_BUILD_SHA", "nope")
    with pytest.raises(RuntimeError):
        _core().build_sha([item])
    monkeypatch.delenv("DEPLOY_BUILD_SHA", raising=False)
    with pytest.raises(RuntimeError):
        _core().build_sha([item])


def test_probe_secret_is_fail_closed(monkeypatch):
    monkeypatch.delenv("ACTIVATION_PROBE_SIGNING_KEY", raising=False)
    with pytest.raises(ActivationProbeDenied):
        _core().probe_signature("env")


def test_evidence_contract_checks_observed_at_provenance_and_exact_environment():
    now = datetime.now(UTC)
    item = {
        "producer": "p",
        "check_name": "c",
        "environment_id": "123",
        "observed_at": (now - timedelta(seconds=1)).isoformat(),
        "valid_until": (now + timedelta(minutes=1)).isoformat(),
        "result": "pass",
        "provenance": "ci/run/1",
    }
    assert _core()._evidence_admissible(item, "123", now)
    assert not _core()._evidence_admissible({**item, "environment_id": 123}, "123", now)
    assert not _core()._evidence_admissible({**item, "provenance": ""}, "123", now)
    assert not _core()._evidence_admissible(
        {**item, "observed_at": (now + timedelta(minutes=1)).isoformat()}, "123", now
    )


def test_evidence_window_is_capped_at_24h_and_provenance_is_canonical():
    now = datetime.now(UTC)
    base = {
        "producer": "p",
        "check_name": "c",
        "environment_id": "env",
        "observed_at": now.isoformat(),
        "valid_until": (now + timedelta(hours=24)).isoformat(),
        "result": "pass",
        "provenance": "ci/run:123.sha-abc",
    }
    # exactly 24h is admissible; one second beyond the cap is not.
    assert _core()._evidence_admissible(base, "env", now)
    assert not _core()._evidence_admissible(
        {**base, "valid_until": (now + timedelta(hours=24, seconds=1)).isoformat()}, "env", now
    )
    # provenance is a canonical, whitespace-free identifier — free text with spaces is rejected.
    assert not _core()._evidence_admissible({**base, "provenance": " CI run 123 "}, "env", now)
    assert not _core()._evidence_admissible({**base, "provenance": "UPPER"}, "env", now)
