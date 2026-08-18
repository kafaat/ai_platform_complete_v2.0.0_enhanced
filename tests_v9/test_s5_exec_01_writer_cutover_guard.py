from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/s5_exec_01_writer_cutover_guard.py"
spec = importlib.util.spec_from_file_location("s5_exec_01_writer_cutover_guard", SCRIPT)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _sandbox(tmp_path: Path, monkeypatch):
    freeze = json.loads(
        (ROOT / "docs/architecture/s5_exec_01_edge_freeze.json").read_text(encoding="utf-8")
    )
    (tmp_path / "docs/architecture").mkdir(parents=True)
    (tmp_path / "docs/architecture/s5_exec_01_edge_freeze.json").write_text(
        json.dumps(freeze), encoding="utf-8"
    )
    for item in freeze["writer_cutover_set_runtime_only"]:
        for rel in item["writers"]:
            dst = tmp_path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text((ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "FREEZE", tmp_path / "docs/architecture/s5_exec_01_edge_freeze.json")
    return freeze


def test_current_frozen_writer_set_has_cutover_contracts():
    assert mod.findings() == []


def test_new_frozen_writer_without_contract_fails_closed(tmp_path, monkeypatch):
    freeze = _sandbox(tmp_path, monkeypatch)
    freeze["writer_cutover_set_runtime_only"][0]["writers"].append(
        "services/sahool-platform/api/new_writer.py"
    )
    (tmp_path / "docs/architecture/s5_exec_01_edge_freeze.json").write_text(
        json.dumps(freeze), encoding="utf-8"
    )
    assert any("FROZEN_WRITER_WITHOUT_CUTOVER_CONTRACT" in x for x in mod.findings())


def test_removing_strict_mode_marker_is_blocked(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    rel = "services/sahool-platform/api/routers/recommendations.py"
    p = tmp_path / rel
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "if mode.strict_decision_service_required:", "if False:", 1
        ),
        encoding="utf-8",
    )
    assert any("CUTOVER_MARKER_MISSING recommendation_outcomes" in x for x in mod.findings())


def test_dispatch_writer_must_be_retired_in_strict_mode(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    rel = "services/sahool-platform/api/routers/decision_dispatch.py"
    p = tmp_path / rel
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "legacy_dispatch_writer_retired_after_decision_sor_cutover",
            "legacy_dispatch_still_live",
            1,
        ),
        encoding="utf-8",
    )
    assert any("CUTOVER_MARKER_MISSING dispatch_decisions" in x for x in mod.findings())
