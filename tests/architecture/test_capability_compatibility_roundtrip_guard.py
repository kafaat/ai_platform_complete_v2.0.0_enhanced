from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/ci/capability_compatibility_roundtrip_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("roundtrip_guard", SOURCE)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_shipped_projection_roundtrip_is_converged():
    assert _load().inspect() == []


# ── مسارات الفشل: «يمرّ على شجرة سليمة» ليس دليلاً أنّ القاعدة حيّة ──────────


class _FakeProjection:
    """إسقاطٌ مزيّف يُرجِع ما نمليه — يعزل قاعدة الحارس عن حالة الشجرة."""

    def __init__(self, drift, synced):
        self._drift = drift
        self._synced = synced

    def drift(self):
        return self._drift, self._synced, ["owner"]


def _shipped_rows(m):
    import json

    return json.loads(m.LEGACY.read_text(encoding="utf-8"))


def test_a_planted_projection_drift_is_reported(monkeypatch):
    m = _load()
    doc = _shipped_rows(m)
    fake = _FakeProjection(["INT-004:owner"], doc)
    monkeypatch.setattr(m, "_projection_module", lambda: fake)
    monkeypatch.setattr(
        m, "subprocess", type("S", (), {"run": staticmethod(lambda *a, **k: _ok())})
    )
    assert "projection_drift:INT-004:owner" in m.inspect()


def test_a_foreign_field_touched_by_projection_is_reported(monkeypatch):
    import copy

    m = _load()
    doc = _shipped_rows(m)
    synced = copy.deepcopy(doc)
    synced["capabilities"][0]["title"] = "TAMPERED"
    fake = _FakeProjection([], synced)
    monkeypatch.setattr(m, "_projection_module", lambda: fake)
    monkeypatch.setattr(
        m, "subprocess", type("S", (), {"run": staticmethod(lambda *a, **k: _ok())})
    )
    cid = doc["capabilities"][0]["id"]
    assert f"projection_touched_foreign_field:{cid}:title" in m.inspect()


def test_a_failing_subcheck_is_reported(monkeypatch):
    m = _load()
    doc = _shipped_rows(m)
    fake = _FakeProjection([], doc)
    monkeypatch.setattr(m, "_projection_module", lambda: fake)
    monkeypatch.setattr(
        m, "subprocess", type("S", (), {"run": staticmethod(lambda *a, **k: _fail())})
    )
    findings = m.inspect()
    assert "traceability_check_failed" in findings
    assert "reconciliation_check_failed" in findings


class _Proc:
    def __init__(self, rc):
        self.returncode = rc


def _ok():
    return _Proc(0)


def _fail():
    return _Proc(1)
