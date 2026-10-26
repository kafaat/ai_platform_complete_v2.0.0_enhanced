"""The owner-run X-Real-IP probe refuses every run it was not explicitly given, and never runs in CI.

``scripts/staging/rate_limit_real_ip_probe.py`` (RATE-LIMIT-KEY-IS-A-RAILWAY-NODE-NOT-THE-CLIENT-01)
sends two requests to a live gateway, so these tests make no network request: the real
sender is replaced by one that fails the test if reached, and refusals are checked both
in-process and through the script's own entry point.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/staging/rate_limit_real_ip_probe.py"
TARGET = "https://sahool-frontend-staging.example.invalid"
NO_CI: dict[str, str] = {}

_spec = importlib.util.spec_from_file_location("rate_limit_real_ip_probe", SCRIPT)
probe = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = probe
_spec.loader.exec_module(probe)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("the probe tried to reach the network in a test")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


def _unreachable(_url, _headers):
    raise AssertionError("a refused run must not send anything")


@pytest.mark.parametrize(
    ("argv", "env", "reason"),
    [
        ([], NO_CI, "--i-am-the-owner-run"),
        (["--target", TARGET], NO_CI, "--i-am-the-owner-run"),
        (["--i-am-the-owner-run"], NO_CI, "without --target"),
        (["--i-am-the-owner-run", "--target", TARGET], {"CI": "true"}, "CI"),
        (["--i-am-the-owner-run", "--target", TARGET], {"GITHUB_ACTIONS": "true"}, "CI"),
        (["--i-am-the-owner-run", "--target", "http://staging.example.invalid"], NO_CI, "https"),
        (["--i-am-the-owner-run", "--target", f"{TARGET}/api/"], NO_CI, "bare origin"),
        (
            ["--i-am-the-owner-run", "--target", "https://u:p@staging.example.invalid"],
            NO_CI,
            "bare",
        ),
        (["--i-am-the-owner-run", "--target", "https://sahool.example.invalid"], NO_CI, "staging"),
        (["--i-am-the-owner-run", "--target", TARGET, "--tag", "a b"], NO_CI, "--tag"),
    ],
)
def test_refuses_without_an_explicit_owner_run_and_target(argv, env, reason, capsys):
    assert probe.main(argv, env=env, send=_unreachable) == probe.REFUSED
    err = capsys.readouterr().err
    assert "refus" in err and reason in err, err


def test_ci_refusal_wins_even_with_every_flag():
    args = probe._parser().parse_args(
        ["--i-am-the-owner-run", "--target", TARGET, "--allow-non-staging-target"]
    )
    with pytest.raises(probe.Refused, match="CI"):
        probe.validate(args, {"CI": "1"})
    assert probe.validate(args, {"CI": "false"}) == TARGET


def test_the_script_entry_point_refuses_with_no_arguments():
    env = {"PATH": "/usr/bin:/bin"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        encoding="utf-8",
        env=env,
        timeout=30,
        check=False,
    )
    assert result.returncode == probe.REFUSED
    assert "refusing to run without --i-am-the-owner-run" in result.stderr
    assert result.stdout == ""


def test_an_owner_run_sends_one_spoofed_and_one_plain_get(capsys):
    sent = []

    def record(url, headers):
        sent.append((url, dict(headers)))
        return 200

    argv = ["--i-am-the-owner-run", "--target", TARGET + "/", "--tag", "t1"]
    assert probe.main(argv, env=NO_CI, send=record) == 0
    assert [url for url, _ in sent] == [
        f"{TARGET}/?sahool_real_ip_probe=t1-spoofed",
        f"{TARGET}/?sahool_real_ip_probe=t1-plain",
    ]
    assert sent[0][1]["X-Real-IP"] == "203.0.113.7"
    assert "X-Real-IP" not in sent[1][1]
    assert all("X-Forwarded-For" not in headers for _, headers in sent)
    out = capsys.readouterr().out
    assert 'xrip="' in out and "2nd-from-right" in out and "152.233.30.0/24" in out


def test_no_workflow_runs_the_probe():
    name = SCRIPT.name
    hits = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / ".github").rglob("*"))
        if path.is_file() and name in path.read_text(encoding="utf-8", errors="replace")
    ]
    assert hits == [], f"{name} must never run in CI: {hits}"
