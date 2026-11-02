"""كلّ workflow يُعلن كتلة `permissions:` علويّة (I5، تدقيق 2026-11-01).

بلا كتلةٍ علويّة يرث `GITHUB_TOKEN` الصلاحيّةَ الافتراضيّة للمستودع، وقد تكون كتابةً شاملة. كان
٣٧ ملفّاً (ثمّ ٤٠ عند الإصلاح) بلا كتلة؛ الحارس `github_actions_policy_guard.py` يمنع العودة.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "ci" / "github_actions_policy_guard.py"
WORKFLOWS = ROOT / ".github" / "workflows"


def _guard(monkeypatch, root: Path):
    spec = importlib.util.spec_from_file_location("github_actions_policy_guard_t", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "WORKFLOWS", root / ".github" / "workflows")
    return module


def _write(root: Path, name: str, text: str) -> None:
    target = root / ".github" / "workflows" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


_BODY = "jobs:\n  a:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: true\n"


def test_every_repository_workflow_declares_top_level_permissions():
    missing = [
        p.name
        for p in sorted(WORKFLOWS.glob("*.y*ml"))
        if "permissions" not in (yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    ]
    assert missing == [], f"workflows بلا permissions علويّة: {missing}"


def test_the_policy_guard_rejects_a_workflow_without_permissions(monkeypatch, tmp_path, capsys):
    _write(tmp_path, "w.yml", "name: w\non:\n  pull_request:\n" + _BODY)
    assert _guard(monkeypatch, tmp_path).main() == 1
    assert "top-level permissions block is required" in capsys.readouterr().err


def test_the_policy_guard_accepts_a_read_only_workflow(monkeypatch, tmp_path):
    _write(
        tmp_path,
        "w.yml",
        "name: w\non:\n  pull_request:\npermissions:\n  contents: read\n" + _BODY,
    )
    assert _guard(monkeypatch, tmp_path).main() == 0


def test_a_job_level_block_alone_does_not_satisfy_the_guard(monkeypatch, tmp_path):
    """كتلةُ وظيفةٍ مُزاحة لا تحمي الوظائف الأخرى في الملفّ."""
    body = _BODY.replace("    runs-on:", "    permissions:\n      contents: read\n    runs-on:")
    _write(tmp_path, "w.yml", "name: w\non:\n  pull_request:\n" + body)
    assert _guard(monkeypatch, tmp_path).main() == 1
