from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/ci/capability_writer_authority_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("writer_guard", SOURCE)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_shipped_writer_boundaries_are_clean():
    assert _load().inspect() == []


def test_linker_reacquiring_canonical_owner_is_blocked(tmp_path):
    m = _load()
    for rel in [m.POLICY, m.LINKER, m.RUNTIME_APPLY]:
        dst = tmp_path / rel.relative_to(m.ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(rel.read_bytes())
    p = tmp_path / m.LINKER.relative_to(m.ROOT)
    p.write_text(p.read_text(encoding="utf-8") + "\ncap['owner'] = 'x'\n", encoding="utf-8")
    assert "capability_linker:unauthorized_canonical_write:owner" in m.inspect(tmp_path)


def test_runtime_apply_cannot_write_production_certified(tmp_path):
    m = _load()
    for rel in [m.POLICY, m.LINKER, m.RUNTIME_APPLY]:
        dst = tmp_path / rel.relative_to(m.ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(rel.read_bytes())
    p = tmp_path / m.RUNTIME_APPLY.relative_to(m.ROOT)
    p.write_text(
        p.read_text(encoding="utf-8") + "\nrow['production_certified'] = True\n",
        encoding="utf-8",
    )
    assert (
        "runtime_verification_apply:unauthorized_certification_write:production_certified"
        in m.inspect(tmp_path)
    )


def test_a_malformed_policy_is_a_named_finding_not_a_stack_trace(tmp_path):
    """سياسة بلا field_authority (أو ليست كائناً) تُبلَّغ باسمها — لا KeyError
    صاخب (رفعته مراجعة آليّة وأصابت)."""
    import json as _json

    m = _load()
    for rel in [m.LINKER, m.RUNTIME_APPLY]:
        dst = tmp_path / rel.relative_to(m.ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(rel.read_bytes())
    p = tmp_path / m.POLICY.relative_to(m.ROOT)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(["not", "an", "object"]), encoding="utf-8")
    assert m.inspect(tmp_path) == ["policy:malformed_field_authority"]

    p.write_text(_json.dumps({"schema": "x", "field_authority": "not-a-dict"}), encoding="utf-8")
    assert m.inspect(tmp_path) == ["policy:malformed_field_authority"]
