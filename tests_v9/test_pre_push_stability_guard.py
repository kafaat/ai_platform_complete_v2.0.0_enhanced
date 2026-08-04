from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "ops" / "pre_push_stability_guard.py"
SPEC = importlib.util.spec_from_file_location("pre_push_stability_guard", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_guard_declares_all_known_cache_and_probe_classes() -> None:
    assert "__pycache__" in MODULE._CACHE_DIRS
    assert ".pyc" in MODULE._CACHE_SUFFIXES
    assert "probe_unadjudicated" in MODULE._PROBE_NAME_MARKERS
    assert "_probe_" in MODULE._PROBE_NAME_MARKERS


def test_guard_catches_bytecode_and_probe_in_a_fake_tree(tmp_path, monkeypatch) -> None:
    (tmp_path / "services/x/__pycache__").mkdir(parents=True)
    (tmp_path / "services/x/__pycache__/a.pyc").write_bytes(b"x")
    router = tmp_path / "services/sahool-platform/api/routers/_probe_bad.py"
    router.parent.mkdir(parents=True)
    router.write_text("# temp", encoding="utf-8")
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    monkeypatch.setattr(MODULE, "_tracked_files", lambda: [])
    found = MODULE.contamination()
    assert any("bytecode" in item for item in found)
    assert any("temporary probe" in item for item in found)


def test_process_markers_cover_the_known_tree_mutators() -> None:
    joined = " ".join(MODULE._MUTATOR_MARKERS)
    assert "verify_all_generated" in joined
    assert "build_release_bundle" in joined
    assert "pytest" in joined


def test_legitimate_runtime_probe_plan_is_not_rejected(tmp_path, monkeypatch) -> None:
    path = tmp_path / "runtime-verification/generated/runtime_probe_plan.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    monkeypatch.setattr(MODULE, "_tracked_files", lambda: [])
    assert MODULE.contamination() == []
