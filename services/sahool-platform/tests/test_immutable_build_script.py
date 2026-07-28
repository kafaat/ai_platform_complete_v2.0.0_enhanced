from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/build-immutable.ps1"


def test_script_resolves_tested_sha_from_exact_head() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "git rev-parse HEAD" in text
    assert "$env:TESTED_SHA = $sha" in text
    assert "docker compose" in text
    assert "config --quiet" in text


def test_script_refuses_dirty_tree_and_invalid_sha() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "git status --porcelain" in text
    assert "Working tree is dirty" in text
    assert "^[0-9a-f]{40}$" in text
