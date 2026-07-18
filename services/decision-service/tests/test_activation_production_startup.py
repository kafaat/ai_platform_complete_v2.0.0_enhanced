"""Gate-Trust-1 Slice 2 — production-profile startup fail-closed for the activation gate.

The gate's non-spoofable guarantees (bound build_sha, signed probe, enforced refusal) depend on
runtime config that is fail-OPEN when unset. In the production profile the app must refuse to start
unless all of it is present. This tests the pure decision; the lifespan wiring mirrors the proven
production_auth_startup_error() hard-fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import main  # noqa: E402


def _arm(monkeypatch):
    monkeypatch.setenv("ACTIVATION_REQUIRE_PRODUCTION_HARDENING", "1")
    monkeypatch.delenv("SAHOOL_ENV", raising=False)


def test_dev_profile_never_blocks_startup(monkeypatch):
    monkeypatch.delenv("ACTIVATION_REQUIRE_PRODUCTION_HARDENING", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    for var in ("DEPLOY_BUILD_SHA", "ACTIVATION_PROBE_SIGNING_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert main.activation_production_startup_error() is None


def test_production_profile_requires_all_hardening(monkeypatch):
    _arm(monkeypatch)
    for var in (
        "DEPLOY_BUILD_SHA",
        "ACTIVATION_PROBE_SIGNING_KEY",
        "IRR_F01_RESERVATION_ENFORCE_ACTIVATION",
    ):
        monkeypatch.delenv(var, raising=False)
    err = main.activation_production_startup_error()
    assert err is not None
    for token in (
        "DEPLOY_BUILD_SHA",
        "ACTIVATION_PROBE_SIGNING_KEY",
        "IRR_F01_RESERVATION_ENFORCE_ACTIVATION",
    ):
        assert token in err


def test_production_profile_satisfied(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setenv("DEPLOY_BUILD_SHA", "abc123")
    monkeypatch.setenv("ACTIVATION_PROBE_SIGNING_KEY", "sign-key")
    monkeypatch.setenv("IRR_F01_RESERVATION_ENFORCE_ACTIVATION", "1")
    assert main.activation_production_startup_error() is None


def test_missing_deploy_build_sha_is_reported(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.delenv("DEPLOY_BUILD_SHA", raising=False)
    monkeypatch.setenv("ACTIVATION_PROBE_SIGNING_KEY", "sign-key")
    monkeypatch.setenv("IRR_F01_RESERVATION_ENFORCE_ACTIVATION", "1")
    err = main.activation_production_startup_error()
    assert err is not None and "DEPLOY_BUILD_SHA" in err
    assert "ACTIVATION_PROBE_SIGNING_KEY" not in err
