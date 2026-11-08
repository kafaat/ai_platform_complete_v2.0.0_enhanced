import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci import execution_dependency_audit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "execution-audit" / "generated"


def test_audit_contract_is_conservative():
    data = json.loads((OUT / "execution_dependency_audit.json").read_text())
    assert data["summary"]["runtime_verified"] is False
    assert data["summary"]["automatic_deletions"] == 0
    assert data["summary"]["evidence_scope"] == "static_repository_only"


def test_routes_and_candidates_are_unique():
    data = json.loads((OUT / "execution_dependency_audit.json").read_text())
    routes = [(x["file"], x["line"], x["handler"]) for x in data["routes"]]
    dead = [(x["file"], x["line"], x["symbol"]) for x in data["dead_code_candidates"]]
    assert len(routes) == len(set(routes))
    assert len(dead) == len(set(dead))


def test_generated_audit_has_no_drift():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/execution_dependency_audit.py"), "--check"],
        cwd=ROOT,
        check=True,
    )


def test_generated_audit_check_rejects_stale_output(tmp_path, monkeypatch):
    out = tmp_path / "generated"
    out.mkdir()
    (out / "audit.json").write_text("stale\n", encoding="utf-8")

    expected = tmp_path / "expected"
    expected.mkdir()
    (expected / "audit.json").write_text("fresh\n", encoding="utf-8")
    expected_digest = execution_dependency_audit.digest(expected)
    (out / ".audit.sha256").write_text(expected_digest + "\n", encoding="utf-8")

    def generate(candidate):
        (candidate / "audit.json").write_text("fresh\n", encoding="utf-8")

    monkeypatch.setattr(execution_dependency_audit, "generate", generate)
    with pytest.raises(SystemExit, match="drift detected"):
        execution_dependency_audit.check(out)
