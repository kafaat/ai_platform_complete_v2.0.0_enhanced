"""Unit contract for the dedicated live-PG role membership closure guard."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "ci" / "live_pg_role_closure_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("_live_pg_role_closure_guard", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = _load()


def _membership(**overrides):
    row = {
        "member": "sahool_app",
        "role": "group_role",
        "grantor": "sahool_user",
        "depth": 1,
        "admin_option": False,
        "inherit_option": False,
        "set_option": False,
    }
    row.update(overrides)
    return row


def _stub_catalogue(monkeypatch, memberships, *, exists=True):
    answers = []

    def fake_psql(sql, **kwargs):
        answers.append(sql)
        if "select exists" in sql.lower():
            return "true" if exists else "false"
        return json.dumps(memberships)

    monkeypatch.setattr(MOD, "psql", fake_psql)
    monkeypatch.setattr(MOD, "_git", lambda *a: "deadbeef")
    return answers


def test_a_standalone_role_passes(tmp_path, monkeypatch):
    _stub_catalogue(monkeypatch, [])
    evidence = tmp_path / "evidence.json"
    assert MOD.main(["--evidence", str(evidence)]) == 0
    doc = json.loads(evidence.read_text(encoding="utf-8"))
    assert doc["verdict"] == "PASS"
    assert doc["membership_closure"] == []
    assert doc["policy"]["require_zero_memberships"] is True


def test_a_direct_inherit_membership_is_rejected(tmp_path, monkeypatch):
    _stub_catalogue(monkeypatch, [_membership(inherit_option=True)])
    evidence = tmp_path / "evidence.json"
    assert MOD.main(["--evidence", str(evidence)]) == 1
    doc = json.loads(evidence.read_text(encoding="utf-8"))
    assert doc["problems"] == [MOD.ROLE_MEMBERSHIP_CLOSURE_NOT_EMPTY]


def test_a_set_role_membership_is_rejected(tmp_path, monkeypatch):
    _stub_catalogue(monkeypatch, [_membership(set_option=True)])
    assert MOD.main(["--evidence", str(tmp_path / "evidence.json")]) == 1


def test_even_an_inert_membership_is_rejected_by_the_dedicated_role_policy(tmp_path, monkeypatch):
    """The evidence role is standalone; options can change later without altering the role itself."""
    _stub_catalogue(monkeypatch, [_membership()])
    assert MOD.main(["--evidence", str(tmp_path / "evidence.json")]) == 1


def test_a_transitive_membership_is_preserved_in_evidence(tmp_path, monkeypatch):
    rows = [
        _membership(role="group_a", inherit_option=True),
        _membership(member="group_a", role="group_b", depth=2, set_option=True),
    ]
    _stub_catalogue(monkeypatch, rows)
    evidence = tmp_path / "evidence.json"
    assert MOD.main(["--evidence", str(evidence)]) == 1
    doc = json.loads(evidence.read_text(encoding="utf-8"))
    assert [row["depth"] for row in doc["membership_closure"]] == [1, 2]


def test_a_missing_role_fails_closed_and_leaves_evidence(tmp_path, monkeypatch):
    _stub_catalogue(monkeypatch, [], exists=False)
    evidence = tmp_path / "evidence.json"
    with pytest.raises(MOD.GuardExit):
        MOD.main(["--evidence", str(evidence)])
    doc = json.loads(evidence.read_text(encoding="utf-8"))
    assert doc["verdict"] == "FAIL"
    assert doc["problems"] == [MOD.RESTRICTED_ROLE_NOT_FOUND]


def test_role_name_reaches_both_catalogue_queries_escaped(monkeypatch):
    asked = _stub_catalogue(monkeypatch, [])
    assert MOD.main(["--app-role", "ops'role"]) == 0
    assert len(asked) == 2
    assert all("ops''role" in sql for sql in asked)
    assert all("ops'role" not in sql.replace("ops''role", "") for sql in asked)


def test_recursive_query_reads_all_membership_options(monkeypatch):
    asked = _stub_catalogue(monkeypatch, [])
    assert MOD.main([]) == 0
    sql = asked[1].lower()
    assert "with recursive role_walk" in sql
    assert "pg_auth_members" in sql
    assert "admin_option" in sql
    assert "inherit_option" in sql
    assert "set_option" in sql
    assert "w.depth + 1" in sql


def test_raw_psql_diagnostic_never_enters_uploaded_evidence(tmp_path, monkeypatch):
    secret = "db.internal:5435 user=sahool_user password=SUPER_SECRET_PW"

    def boom(*a, **k):
        raise MOD.GuardExit(secret, MOD.PSQL_CATALOGUE_QUERY_FAILED)

    monkeypatch.setattr(MOD, "role_exists", boom)
    monkeypatch.setattr(MOD, "_git", lambda *a: "deadbeef")
    evidence = tmp_path / "evidence.json"
    with pytest.raises(MOD.GuardExit):
        MOD.main(["--evidence", str(evidence)])
    text = evidence.read_text(encoding="utf-8")
    assert "SUPER_SECRET_PW" not in text, (
        "المصنوعة تُرفَع إلى GitHub وتبقى قابلةً للتنزيل شهوراً؛ فتشخيصُ libpq الخام "
        "يحمل كلمة المرور. المنع مقصود: الدليل يحمل أسباباً ثابتة لا سلاسل اتّصال."
    )
    assert "db.internal" not in text, (
        "والمضيف/المنفذ طوبولوجيا داخليّة: تسريبُها في مصنوعةٍ عامّة استطلاعٌ مجّانيّ. "
        "المنع مقصود لا عرَضيّ — ولذلك يُصنَّف الخطأ إلى رمزٍ قبل الكتابة."
    )
    assert MOD.PSQL_CATALOGUE_QUERY_FAILED in text, (
        "ومع ذلك يبقى **سببٌ** مقروء: حذفُ التشخيص لا يعني مصنوعةً صامتة، وإلّا "
        "صار الفشل غير قابل للتشخيص من الدليل وحده."
    )
