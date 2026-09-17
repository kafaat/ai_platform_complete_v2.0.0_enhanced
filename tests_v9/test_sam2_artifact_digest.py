"""EDGE-MODEL-ARTIFACT-DIGEST-01 — SAM2 bytes must match approved SHA-256."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "services" / "sam2-inference" / "sam2_runtime.py"


def _load_runtime():
    spec = importlib.util.spec_from_file_location("_sam2_digest_runtime", RUNTIME)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_matching_checkpoint_digest_is_verified(tmp_path):
    rt = _load_runtime()
    model = tmp_path / "sam2.pt"
    model.write_bytes(b"approved-sam2-checkpoint")
    expected = hashlib.sha256(model.read_bytes()).hexdigest()

    verified, actual, reason = rt._verify_checkpoint_artifact(str(model), expected)

    assert verified is True
    assert actual == expected
    assert reason is None


def test_missing_or_invalid_checkpoint_digest_fails_closed_before_identity_claim(tmp_path):
    rt = _load_runtime()
    model = tmp_path / "sam2.pt"
    model.write_bytes(b"unidentified-checkpoint")

    for expected in ("", "abc", "g" * 64):
        verified, actual, reason = rt._verify_checkpoint_artifact(str(model), expected)
        assert verified is False
        assert actual is None
        assert reason == "checkpoint_digest_missing_or_invalid"


def test_mismatching_checkpoint_digest_names_the_actual_bytes(tmp_path):
    rt = _load_runtime()
    model = tmp_path / "sam2.pt"
    model.write_bytes(b"wrong-checkpoint")
    actual_expected = hashlib.sha256(model.read_bytes()).hexdigest()

    verified, actual, reason = rt._verify_checkpoint_artifact(str(model), "0" * 64)

    assert verified is False
    assert actual == actual_expected
    assert reason == "checkpoint_digest_mismatch"


def test_model_load_verifies_artifact_before_importing_torch(monkeypatch):
    rt = _load_runtime()
    calls = []

    def refuse(*_args):
        calls.append("verify")
        return False, None, "checkpoint_digest_missing_or_invalid"

    monkeypatch.setattr(rt, "_verify_checkpoint_artifact", refuse)
    monkeypatch.setitem(sys.modules, "torch", None)

    rt._load_model()

    assert calls == ["verify"]
    assert rt._PREDICTOR is None
    assert rt._MODEL_ARTIFACT_DIGEST is None
    assert rt._MODEL_LOAD_REASON_CODE == "checkpoint_digest_missing_or_invalid"
