from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/github_actions_security_guard.py"
WORKFLOW = ROOT / ".github/workflows/github-actions-security.yml"
INSTALLER = ROOT / "scripts/ci/install_pinned_actions_security_tools.sh"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
pytestmark = pytest.mark.unit


def _module():
    spec = importlib.util.spec_from_file_location("github_actions_security_guard", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sources() -> tuple[str, str, str]:
    return (
        WORKFLOW.read_text(encoding="utf-8"),
        INSTALLER.read_text(encoding="utf-8"),
        CI_WORKFLOW.read_text(encoding="utf-8"),
    )


def test_current_github_actions_security_lane_is_guarded() -> None:
    workflow, installer, ci = _sources()
    assert _module().evaluate(workflow, installer, ci) == []


@pytest.mark.parametrize(
    ("target", "find", "replace", "expected"),
    [
        ("workflow", "--min-confidence high", "--min-confidence low", "blocking security command"),
        (
            "workflow",
            "--allowed-rules injection",
            "--allowed-rules untrusted_checkout_exec",
            "blocking security command",
        ),
        (
            "workflow",
            "persist-credentials: false",
            "persist-credentials: true",
            "persisted credentials",
        ),
        (
            "workflow",
            "permissions:\n  contents: read",
            "permissions:\n  contents: write",
            "contents:read",
        ),
        (
            "installer",
            "dd96df044a6e8538d5f423790f453bdd03d49e5b2bcc38214acc41a2f1297839",
            "0" * 64,
            "zizmor",
        ),
        (
            "ci",
            "poutine --allowed-rules injection --fail-on-violation --disable-version-check analyze_local .",
            "poutine analyze_local .",
            "required Security Scan enforcement",
        ),
    ],
)
def test_security_lane_mutations_are_killed(
    target: str, find: str, replace: str, expected: str
) -> None:
    workflow, installer, ci = _sources()
    values = {"workflow": workflow, "installer": installer, "ci": ci}
    assert find in values[target]
    values[target] = values[target].replace(find, replace, 1)
    errors = _module().evaluate(values["workflow"], values["installer"], values["ci"])
    assert any(expected in error for error in errors), errors
