from __future__ import annotations

import copy
import importlib.util
import json
import shutil
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/architecture/rag_direct_qdrant_boundary_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("rag_direct_qdrant_boundary_guard", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules.
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _minimal_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs/architecture").mkdir(parents=True)
    state = json.loads(
        (ROOT / "docs/architecture/rag_authority_convergence.json").read_text(encoding="utf-8")
    )
    registry = json.loads(
        (ROOT / "docs/architecture/component_registry.json").read_text(encoding="utf-8")
    )
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    (root / "docs/architecture/rag_authority_convergence.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    (root / "docs/architecture/component_registry.json").write_text(
        json.dumps(registry), encoding="utf-8"
    )
    (root / "docker-compose.v9.yml").write_text(yaml.safe_dump(compose), encoding="utf-8")
    return root


def test_current_tree_has_exact_authority_sensitive_direct_consumers():
    m = _load()
    rows = m.inventory(ROOT)
    roles = {row.component_id: row.role for row in rows}
    assert roles == {
        "local-ai-rag": "temporary_response_path_exception",
        "qdrant-seed": "bootstrap_writer",
        "rag-retrieval": "canonical_retrieval",
    }
    assert m.findings(ROOT) == []


def test_new_runtime_qdrant_consumer_is_rejected(tmp_path):
    m = _load()
    root = _minimal_root(tmp_path)
    compose_path = root / "docker-compose.v9.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    svc = compose["services"]["sahool-ai-agronomist"]
    env = svc.setdefault("environment", {})
    env["QDRANT_URL"] = "http://sahool-qdrant:6333"
    compose_path.write_text(yaml.safe_dump(compose), encoding="utf-8")
    findings = m.findings(root)
    assert "unauthorized direct Qdrant runtime consumer: ai_agronomist" in findings


def test_unregistered_direct_qdrant_deployment_is_rejected(tmp_path):
    m = _load()
    root = _minimal_root(tmp_path)
    compose_path = root / "docker-compose.v9.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    compose["services"]["rogue-rag"] = {
        "image": "example.invalid/rogue:1",
        "environment": {"QDRANT_URL": "http://sahool-qdrant:6333"},
    }
    compose_path.write_text(yaml.safe_dump(compose), encoding="utf-8")
    findings = m.findings(root)
    assert "unauthorized direct Qdrant runtime consumer: UNREGISTERED:rogue-rag" in findings


def test_cutover_state_rejects_remaining_temporary_exception(tmp_path):
    m = _load()
    root = _minimal_root(tmp_path)
    state_path = root / "docs/architecture/rag_authority_convergence.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["stage"] = "cutover"
    state["authority_state"] = "CUTOVER_CAPABLE"
    state["cutover_requirements"] = {k: True for k in state["cutover_requirements"]}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    findings = m.findings(root)
    assert "direct_qdrant_exception must be removed after cutover" in findings
    assert any(
        "post-cutover direct Qdrant response path remains: local-ai-rag" == x for x in findings
    )


def test_bootstrap_writer_cannot_be_promoted_to_domain_authority(tmp_path):
    m = _load()
    root = _minimal_root(tmp_path)
    reg_path = root / "docs/architecture/component_registry.json"
    registry = json.loads(reg_path.read_text(encoding="utf-8"))
    registry["components"]["qdrant-seed"]["authority_kind"] = "system_of_record"
    reg_path.write_text(json.dumps(registry), encoding="utf-8")
    findings = m.findings(root)
    assert "Qdrant bootstrap job must not own domain authority: qdrant-seed" in findings


def test_policy_cannot_silently_allow_new_runtime_exceptions(tmp_path):
    m = _load()
    root = _minimal_root(tmp_path)
    state_path = root / "docs/architecture/rag_authority_convergence.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["direct_qdrant_policy"]["new_runtime_exceptions_forbidden"] = False
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert "direct_qdrant_policy must forbid new runtime exceptions" in m.findings(root)
