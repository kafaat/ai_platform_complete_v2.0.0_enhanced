from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/ci/capability_legacy_access_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("legacy_access_guard", SOURCE)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_shipped_direct_access_is_fully_classified():
    assert _load().inspect() == []


def test_new_direct_consumer_fails_closed(tmp_path):
    m = _load()
    p = tmp_path / m.POLICY.relative_to(m.ROOT)
    p.parent.mkdir(parents=True)
    p.write_bytes(m.POLICY.read_bytes())
    s = tmp_path / "scripts/ci/new_consumer.py"
    s.parent.mkdir(parents=True)
    s.write_text("X='capabilities/registry/capabilities.json'\n", encoding="utf-8")
    # copy all allowed files so stale allowances do not obscure the new-access assertion
    for rel in json.loads(m.POLICY.read_text(encoding="utf-8"))["entries"]:
        src = m.ROOT / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    assert "unclassified_direct_access:scripts/ci/new_consumer.py" in m.inspect(tmp_path)


def test_stale_allowance_is_rejected(tmp_path):
    m = _load()
    p = tmp_path / m.POLICY.relative_to(m.ROOT)
    p.parent.mkdir(parents=True)
    d = {
        "schema": "sahool.capability-legacy-access/v1",
        "default": "deny",
        "entries": {"scripts/ci/ghost.py": "projection_guard"},
    }
    p.write_text(json.dumps(d), encoding="utf-8")
    (tmp_path / "scripts/ci").mkdir(parents=True, exist_ok=True)
    assert "stale_access_allowance:scripts/ci/ghost.py" in m.inspect(tmp_path)
