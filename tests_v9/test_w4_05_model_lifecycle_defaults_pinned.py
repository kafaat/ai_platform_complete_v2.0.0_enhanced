"""W4-05: the decision-service flag and the platform capability stay off together.

The WX-12 model-lifecycle loop is stopped by owner decision (2026-11-16). decision-service holds
the only switch (DECISION_MODEL_LIFECYCLE_ENABLED, off by default); the platform declares the
capability ``model_lifecycle`` statically dormant instead of calling the service. Turning one on
without the other would show a loop the server refuses, or hide one it runs: this test fails if
either default moves alone.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
DS_DIR = ROOT / "services" / "decision-service"
PLATFORM_CAPABILITIES = ROOT / "services" / "sahool-platform" / "core" / "capabilities.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve their module through sys.modules
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _model_lifecycle(report: dict) -> dict:
    entries = [c for c in report["capabilities"] if c["key"] == "model_lifecycle"]
    assert len(entries) == 1, "the platform must declare model_lifecycle exactly once"
    return entries[0]


def test_the_service_switch_and_the_platform_capability_are_off_together(monkeypatch):
    monkeypatch.delenv("DECISION_MODEL_LIFECYCLE_ENABLED", raising=False)
    monkeypatch.syspath_prepend(str(DS_DIR))
    persistence = _load("w4_05_ds_persistence", DS_DIR / "persistence.py")
    capabilities = _load("w4_05_platform_capabilities", PLATFORM_CAPABILITIES)

    service_on = persistence.model_lifecycle_enabled()
    platform = _model_lifecycle(capabilities.capabilities_report())

    assert service_on is False, "decision-service must default DECISION_MODEL_LIFECYCLE_ENABLED off"
    assert platform["status"] == "dormant", "the platform must declare model_lifecycle dormant"
    assert "DECISION_MODEL_LIFECYCLE_ENABLED" in platform["activation_ar"]


def test_the_platform_capability_does_not_follow_the_service_env(monkeypatch):
    """Static by design: setting the service's variable on the platform turns nothing on."""
    monkeypatch.setenv("DECISION_MODEL_LIFECYCLE_ENABLED", "1")
    capabilities = _load("w4_05_platform_capabilities_env", PLATFORM_CAPABILITIES)
    assert _model_lifecycle(capabilities.capabilities_report())["status"] == "dormant"
