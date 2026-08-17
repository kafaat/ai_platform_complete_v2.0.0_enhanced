from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/architecture/authority_cutover_guard.py"
spec = importlib.util.spec_from_file_location("authority_cutover_guard", PATH)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_current_s4_contract_is_closed_at_declared_states():
    assert mod.findings() == []


def test_decision_state_contract_is_declared_correctly():
    c = json.loads((ROOT / "docs/architecture/authority_cutovers.json").read_text(encoding="utf-8"))
    d = c["authorities"]["decision"]
    assert d["cutover_capability"] == "CUTOVER_CAPABLE"
    assert d["declared_state"] == "INTERIM"
    assert d["authority_state"] == "NOT_YET_AUTHORITATIVE"


def test_field_state_contract_requires_restricted_application_role_live_proof():
    c = json.loads((ROOT / "docs/architecture/authority_cutovers.json").read_text(encoding="utf-8"))
    f = c["authorities"]["field_management"]
    assert f["cutover_capability"] == "NOT_YET_CUTOVER_CAPABLE"
    assert "LIVE_APPLICATION_ROLE_RLS_PROOF_REQUIRED" in f["blocking_reasons"]


def test_kg_current_physical_implementation_is_not_in_platform():
    old = (ROOT / "services/sahool-platform/core/knowledge_graph/sqlite_graph.py").read_text(
        encoding="utf-8"
    )
    assert "class SQLiteAgGraphStore" not in old, (
        "ملكيّة المتجر فيزيائيّة لا إعلانيّة — صنفٌ باسمه هنا يعني أنّ sahool-platform "
        "ما تزال تستضيف تطبيقاً منافساً، فتعود المِلكيّة المُعلَنة تسميةً بلا أثر"
    )
    assert "import sqlite3" not in old, (
        "استيراد sqlite3 في الشاهدة يُعيد ربط المنصّة بمحرّك التخزين — "
        "والنقل يُقاس بغياب الاعتماد لا بغياب الاسم"
    )
    main = (ROOT / "services/knowledge-graph/main.py").read_text(encoding="utf-8")
    assert "from kg_store import" in main
    assert (ROOT / "services/knowledge-graph/kg_store.py").is_file()


def test_kg_owner_store_rejects_prescriptive_edges():
    p = ROOT / "services/knowledge-graph/kg_store.py"
    s = importlib.util.spec_from_file_location("kg_store_test", p)
    assert s is not None and s.loader is not None
    m = importlib.util.module_from_spec(s)
    sys.modules[s.name] = m
    s.loader.exec_module(m)
    with pytest.raises(ValueError):
        m.GraphEdge("e", "a", "controls", "b")


def _sandbox(tmp_path, monkeypatch):
    import shutil

    needed = [
        "docs/architecture/authority_cutovers.json",
        "services/sahool-platform/api/decision_sor_mode.py",
        "tests_v9/test_decision_sor_platform_revoke_static.py",
        "services/decision-service/tests/test_decision_sor_db_privilege_cutover.py",
        "services/field-management-service/tests/test_field_management_pg_isolation_integration.py",
        "services/knowledge-graph/main.py",
        "services/knowledge-graph/Dockerfile",
        "services/knowledge-graph/kg_store.py",
        "services/sahool-platform/core/knowledge_graph/sqlite_graph.py",
    ]
    for rel in needed:
        src = ROOT / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "CONTRACT", tmp_path / "docs/architecture/authority_cutovers.json")
    return tmp_path


def test_decision_is_cutover_capable_but_not_yet_authoritative(tmp_path, monkeypatch):
    root = _sandbox(tmp_path, monkeypatch)
    c = json.loads((root / "docs/architecture/authority_cutovers.json").read_text(encoding="utf-8"))
    c["authorities"]["decision"]["authority_state"] = "AUTHORITATIVE"
    (root / "docs/architecture/authority_cutovers.json").write_text(json.dumps(c), encoding="utf-8")
    assert "decision prematurely authoritative" in mod.findings()


def test_field_requires_restricted_application_role_live_proof(tmp_path, monkeypatch):
    root = _sandbox(tmp_path, monkeypatch)
    p = (
        root
        / "services/field-management-service/tests/test_field_management_pg_isolation_integration.py"
    )
    p.write_text(
        p.read_text(encoding="utf-8").replace("NOBYPASSRLS", "BYPASSRLS"), encoding="utf-8"
    )
    assert "field RLS proof does not fail honestly when restricted role is absent" in mod.findings()


def test_kg_physical_implementation_is_not_in_platform(tmp_path, monkeypatch):
    root = _sandbox(tmp_path, monkeypatch)
    p = root / "services/sahool-platform/core/knowledge_graph/sqlite_graph.py"
    p.write_text(
        p.read_text(encoding="utf-8") + "\nclass SQLiteAgGraphStore: pass\n", encoding="utf-8"
    )
    assert "sahool-platform still physically hosts KG store" in mod.findings()


def test_kg_image_ships_the_module_its_entrypoint_imports(tmp_path, monkeypatch):
    root = _sandbox(tmp_path, monkeypatch)
    p = root / "services/knowledge-graph/Dockerfile"
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "COPY services/knowledge-graph/kg_store.py /app/kg_store.py\n", ""
        ),
        encoding="utf-8",
    )
    assert "KG image does not ship an imported owned module: kg_store.py" in mod.findings()
