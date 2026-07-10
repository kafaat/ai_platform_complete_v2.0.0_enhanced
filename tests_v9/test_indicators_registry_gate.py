"""Unit tests for the indicators registry single-source-of-truth gate (WS-B.1)."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "scripts/ci/indicators_registry_gate.py"
REGISTRY_PATH = REPO_ROOT / "config/indicators_registry.json"


def _load_gate():
    spec = importlib.util.spec_from_file_location("indicators_registry_gate", GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_registry_json_is_valid_and_has_indicators():
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(data["indicators"], list)
    assert data["indicators"], "registry must not be empty"
    ids = [e["id"] for e in data["indicators"]]
    assert len(ids) == len(set(ids)), "duplicate indicator ids in registry"
    for e in data["indicators"]:
        assert e["source"] in {"real", "estimated", "derived"}
        assert e["status"] in {"implemented", "estimated", "not_implemented"}


@pytest.mark.unit
def test_gate_passes_on_current_registry():
    gate = _load_gate()
    assert gate.main() == 0


@pytest.mark.unit
def test_gate_fails_on_drifted_registry(tmp_path, monkeypatch):
    """Prove the gate is not a no-op: dropping a backend catalog id must fail check (c)."""
    gate = _load_gate()
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    drifted = copy.deepcopy(data)
    # Remove 'ndvi' — an id that lives in the backend _INDICATOR_CATALOG (check c) and
    # the frontend catalog (check d) — to force drift.
    drifted["indicators"] = [e for e in drifted["indicators"] if e["id"] != "ndvi"]
    bad = tmp_path / "indicators_registry.json"
    bad.write_text(json.dumps(drifted), encoding="utf-8")

    monkeypatch.setattr(gate, "REGISTRY", bad)
    with pytest.raises(SystemExit) as exc:
        gate.main()
    assert exc.value.code == 1


@pytest.mark.unit
def test_gate_fails_when_estimate_claims_real(tmp_path, monkeypatch):
    """Honesty check (f): relabelling a vegetation estimate as real/implemented must fail."""
    gate = _load_gate()
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    drifted = copy.deepcopy(data)
    for e in drifted["indicators"]:
        if e["id"] == "lai":
            e["source"] = "real"
            e["status"] = "implemented"
    bad = tmp_path / "indicators_registry.json"
    bad.write_text(json.dumps(drifted), encoding="utf-8")

    monkeypatch.setattr(gate, "REGISTRY", bad)
    with pytest.raises(SystemExit) as exc:
        gate.main()
    assert exc.value.code == 1
