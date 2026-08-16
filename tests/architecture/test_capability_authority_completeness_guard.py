from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/ci/capability_authority_completeness_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("guard_under_test", SOURCE)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _fixture(root: Path, field="id", spec=None):
    p = root / "docs/capability-registry/field_authority_policy.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "schema": "sahool.capability-field-authority/v1",
                "field_authority": {
                    field: spec or {"authority": "canonical_capability_definition"}
                },
            }
        ),
        encoding="utf-8",
    )
    r = root / "capabilities/registry/capabilities.json"
    r.parent.mkdir(parents=True, exist_ok=True)
    r.write_text(json.dumps({"capabilities": [{"id": "X", field: "v"}]}), encoding="utf-8")


def test_shipped_schema_has_total_authority_coverage():
    m = _load()
    findings, fields = m.inspect()
    assert findings == []
    assert len(fields) >= 20


def test_unclassified_legacy_field_fails(tmp_path):
    m = _load()
    _fixture(tmp_path)
    r = tmp_path / "capabilities/registry/capabilities.json"
    d = json.loads(r.read_text(encoding="utf-8"))
    d["capabilities"][0]["mystery"] = 1
    r.write_text(json.dumps(d), encoding="utf-8")
    findings, _ = m.inspect(tmp_path)
    assert "mystery:unclassified" in findings


def test_unknown_authority_fails(tmp_path):
    m = _load()
    _fixture(tmp_path, spec={"authority": "magic_registry"})
    findings, _ = m.inspect(tmp_path)
    assert findings == ["id:unknown_authority:magic_registry"]


def test_canonical_field_cannot_reauthorize_legacy_writer(tmp_path):
    m = _load()
    _fixture(
        tmp_path,
        spec={
            "authority": "canonical_capability_definition",
            "legacy_writer": "repository_traceability_projection",
        },
    )
    findings, _ = m.inspect(tmp_path)
    assert "id:canonical_field_has_legacy_writer" in findings
