import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/ci/pr_capability_impact_gate.py"
spec = importlib.util.spec_from_file_location("pr_capability_impact_gate", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_known_service_change_maps_direct_and_transitive():
    data = mod.impact(["services/weather-service/main.py"])
    assert "WX-001" in data["direct"]
    assert "IRR-004" in data["transitive"]
    assert data["runtime_claims"] is False
    assert data["production_certification"] is False


def test_unrelated_document_has_no_capability_impact():
    data = mod.impact(["NOTICE-unrelated.txt"])
    assert data["affected"] == []
    declared = mod.parse_declaration_value("NONE", mod.current_snapshot().known_capabilities)
    mod.apply_declaration(data, declared, mod.current_snapshot().known_capabilities)
    assert data["decision"] == "PASS"


def test_index_includes_events_apis_and_repository_evidence():
    registry = {
        "capabilities": [
            {
                "id": "WX-001",
                "dependencies": [],
                "services": [],
                "ui_consumers": [],
                "mobile_consumers": [],
                "tests": [],
                "apis": ["GET /weather @ services/weather/api.py:12"],
                "evidence": [{"type": "repository", "path": "services/weather/core.py"}],
            }
        ]
    }
    mapping = {
        "capabilities": [
            {
                "capability_id": "WX-001",
                "events": [
                    {"value": "weather.updated @ services/weather/events.py:9", "score": 20}
                ],
            }
        ]
    }
    snapshot = mod.build_snapshot(registry, mapping, None, root=None)
    assert "services/weather/api.py" in snapshot.references
    assert "services/weather/core.py" in snapshot.references
    assert "services/weather/events.py" in snapshot.references


def test_deleted_path_is_detected_from_merge_base_snapshot_union():
    registry = {
        "capabilities": [
            {
                "id": "WX-001",
                "dependencies": [],
                "services": [],
                "ui_consumers": [],
                "mobile_consumers": [],
                "tests": [],
            }
        ]
    }
    base_mapping = {
        "capabilities": [
            {
                "capability_id": "WX-001",
                "backend": [{"path": "services/weather/deleted.py", "score": 20}],
            }
        ]
    }
    head_mapping = {"capabilities": [{"capability_id": "WX-001", "backend": []}]}
    base = mod.build_snapshot(registry, base_mapping, None, root=None)
    head = mod.build_snapshot(registry, head_mapping, None, root=None)
    data = mod.impact(["services/weather/deleted.py"], mod.merge_snapshots(base, head))
    assert data["direct"] == ["WX-001"]


def test_rename_parser_keeps_old_and_new_paths():
    payload = b"R100\0services/old.py\0services/new.py\0M\0README.md\0"
    assert mod.parse_name_status_z(payload) == [
        "README.md",
        "services/new.py",
        "services/old.py",
    ]


def test_git_changed_paths_uses_merge_base_and_reports_renames(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    old = tmp_path / "old.py"
    old.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "old.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    subprocess.run(["git", "mv", "old.py", "new.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "rename"], cwd=tmp_path, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    merge_base, paths = mod.git_changed_paths(base, head, root=tmp_path)
    assert merge_base == base
    assert paths == ["new.py", "old.py"]


def test_declaration_requires_all_direct_and_rejects_unaffected_noise():
    known = {"WX-001", "WX-002", "IRR-004"}
    data = {
        "direct": ["WX-001", "WX-002"],
        "affected": ["IRR-004", "WX-001", "WX-002"],
        "governance_wide": False,
    }
    declaration = mod.parse_declaration_value("WX-001,IRR-004", known)
    mod.apply_declaration(data, declaration, known)
    assert data["decision"] == "BLOCK"
    assert data["declaration"]["missing_direct"] == ["WX-002"]

    clean = {
        "direct": ["WX-001", "WX-002"],
        "affected": ["IRR-004", "WX-001", "WX-002"],
        "governance_wide": False,
    }
    declaration = mod.parse_declaration_value("WX-001,WX-002,IRR-004", known)
    mod.apply_declaration(clean, declaration, known)
    assert clean["decision"] == "PASS"


def test_all_is_limited_to_governance_wide_changes():
    known = {"WX-001", "WX-002"}
    declaration = mod.parse_declaration_value("ALL", known)
    ordinary = {
        "direct": ["WX-001"],
        "affected": ["WX-001"],
        "governance_wide": False,
    }
    mod.apply_declaration(ordinary, declaration, known)
    assert ordinary["decision"] == "BLOCK"
    assert "ALL is allowed only for governance-wide changes" in ordinary["declaration"]["errors"]

    governance = {
        "direct": sorted(known),
        "affected": sorted(known),
        "governance_wide": True,
    }
    mod.apply_declaration(governance, declaration, known)
    assert governance["decision"] == "PASS"


def test_roadmap_definition_change_is_governance_wide():
    snapshot = mod.current_snapshot()
    data = mod.impact([mod.ROADMAP_PATH.as_posix()], snapshot)
    assert data["governance_wide"] is True
    assert set(data["direct"]) == snapshot.known_capabilities


def test_multiple_pr_body_declarations_are_rejected():
    known = {"WX-001"}
    declaration = mod.parse_pr_body("Capability-Impact: WX-001\n\nCapability-Impact: NONE\n", known)
    assert declaration["mode"] == "invalid"
    assert declaration["errors"]


def test_path_traversal_is_rejected():
    with pytest.raises(ValueError, match="inside the repository"):
        mod.normalize_repo_path("../outside.py")


def test_index_summary_is_deterministic_and_fail_closed():
    first = mod.index_summary()
    second = mod.index_summary()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["indexed_paths"] > 100
    assert first["constraints"]["deletion_detection"] is True
    assert first["constraints"]["runtime_claims"] is False


def test_derivation_from_an_uncommitted_tree_is_refused() -> None:
    """الاشتقاق يكون بعد الالتزام لا بعد الإدراج — العطل الذي حجب #859.

    ``git_changed_paths`` يقارن ``base..head`` بمراجعَ **ملتزَمة**. فحين يكون
    ``--head`` هو نسخة العمل وفيها تعديلٌ غير ملتزَم، يُنتج الاشتقاقُ جواباً عن شجرةٍ
    أخرى غير التي ستقيسها CI. وقع فعليّاً: اشتُقّ السطر بعد ``git add`` فلم تدخل
    المصنوعات المُعاد توليدها، فسقطت ``FM-001`` و``OPS-003`` وحجبت البوّابة.

    يُقاس هنا **بشجرة اختبار حقيقيّة** لا بمحاكاة: مستودعٌ مؤقّت بالتزامَين، ثمّ
    تعديلٌ غير ملتزَم.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)

        def g(*a: str) -> None:
            subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)

        g("init", "-q")
        g("config", "user.email", "t@example.invalid")
        g("config", "user.name", "t")
        (repo / "a.txt").write_text("one\n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-qm", "base")
        base = (
            subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True)
            .stdout.decode()
            .strip()
        )
        (repo / "b.txt").write_text("two\n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-qm", "head")

        # شجرة نظيفة ⇒ لا انحراف مُبلَّغ.
        assert mod.worktree_deviation("HEAD", root=repo) == []

        # تعديلٌ مُدرَجٌ غير ملتزَم ⇒ يُبلَّغ عنه بالاسم.
        (repo / "c.txt").write_text("three\n", encoding="utf-8")
        g("add", "-A")
        assert "c.txt" in mod.worktree_deviation("HEAD", root=repo)

        # وأيضاً غير المُدرَج.
        (repo / "a.txt").write_text("changed\n", encoding="utf-8")
        assert "a.txt" in mod.worktree_deviation("HEAD", root=repo)

        # مرجعٌ تاريخيّ صريح ليس نسخة العمل ⇒ لا معنى لمقارنة الشجرة، فلا انحراف.
        assert mod.worktree_deviation(base, root=repo) == []
