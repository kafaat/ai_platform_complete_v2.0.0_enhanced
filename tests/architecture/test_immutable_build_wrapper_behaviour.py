"""Run the immutable build wrappers with a recording Docker CLI.

`test_immutable_local_build_entrypoints` scans the wrapper for literal substrings. That
catches a deleted line, but it passes just as happily if the line is commented out — the
same false-positive class that bit the router docstring and the registry `not_this` field.
Shell has no AST to lean on, so the honest substitute is to run the thing.

`docker` is stubbed to a recording script: the wrapper's job is to derive an immutable
identity and refuse a dirty tree, not to build an image, and the build itself is exactly
the part this environment cannot execute.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

WRAPPER = Path(__file__).resolve().parents[2] / "scripts" / "build-immutable.sh"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def _repo(tmp_path: Path, wrapper: Path = WRAPPER) -> Path:
    """A throwaway git repo carrying a copy of the wrapper."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    target = root / "scripts" / wrapper.name
    target.write_bytes(wrapper.read_bytes())
    target.chmod(0o755)
    (root / "docker-compose.v9.yml").write_text("services: {}\n", encoding="utf-8")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e",
    }
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", *args], cwd=root, check=True, env=env)
    return root


def _stub_docker(tmp_path: Path) -> Path:
    """A fake `docker` that records the TESTED_SHA it was invoked with."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    stub = bin_dir / "docker"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "TESTED_SHA=${{TESTED_SHA:-<unset>}} BUILD_ID=${{SAHOOL_BUILD_ID:-<unset>}} $*" >> "{log}"\n'
        'if [[ "$1" == info ]]; then echo "${ENGINE_OS:-linux}"; exit "${INFO_EXIT:-0}"; fi\n'
        'if [[ "$1 $2" == "compose version" ]]; then exit "${VERSION_EXIT:-0}"; fi\n'
        'if [[ " $* " == *" up "* ]]; then exit "${UP_EXIT:-0}"; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return bin_dir


def _run(root: Path, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["./scripts/build-immutable.sh"],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )


def test_clean_tree_exports_the_full_head_sha_to_docker(tmp_path: Path):
    """The identity handed to the build is HEAD itself — 40 characters, not a nickname."""
    root, bin_dir = _repo(tmp_path), _stub_docker(tmp_path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert FULL_SHA.match(head)

    result = _run(root, bin_dir)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Immutable build completed for TESTED_SHA={head}" in result.stdout

    invocations = (tmp_path / "docker.log").read_text(encoding="utf-8")
    assert f"TESTED_SHA={head}" in invocations, "docker was not given the resolved SHA"
    assert "TESTED_SHA=<unset>" not in invocations
    assert "TESTED_SHA=local" not in invocations, "a nickname must never reach the build"
    assert f"BUILD_ID=local-{head[:12]}" in invocations
    assert "config --quiet" in invocations, "compose must be validated before building"


def test_dirty_tree_is_refused_before_docker_is_touched(tmp_path: Path):
    """An uncommitted change means HEAD does not describe what would be built."""
    root, bin_dir = _repo(tmp_path), _stub_docker(tmp_path)
    (root / "docker-compose.v9.yml").write_text("services: {tampered: {}}\n", encoding="utf-8")

    result = _run(root, bin_dir)
    assert result.returncode == 1
    assert "Working tree is dirty" in result.stderr
    assert not (tmp_path / "docker.log").exists(), "docker ran despite the dirty tree"


@pytest.mark.parametrize(
    ("engine_os", "info_exit", "message"),
    [("windows", "0", "requires a Linux Docker Engine"), ("linux", "1", "unreachable")],
)
def test_bash_checks_engine_before_compose(tmp_path, monkeypatch, engine_os, info_exit, message):
    root, bin_dir = _repo(tmp_path), _stub_docker(tmp_path)
    monkeypatch.setenv("ENGINE_OS", engine_os)
    monkeypatch.setenv("INFO_EXIT", info_exit)
    result = _run(root, bin_dir)
    assert result.returncode != 0 and message in result.stderr
    calls = (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1 and calls[0].endswith("info --format {{.OSType}}")


def test_bash_refuses_unreadable_git_status(tmp_path):
    root, bin_dir = _repo(tmp_path), _stub_docker(tmp_path)
    (root / ".git" / "index").write_bytes(b"invalid index")
    result = _run(root, bin_dir)
    assert result.returncode != 0 and "Unable to verify" in result.stderr
    assert not (tmp_path / "docker.log").exists()


def test_the_guard_is_the_check_not_the_wording(tmp_path: Path):
    """Falsification: strip the dirty-tree check and the dirty tree must start building.

    Without this, the test above could pass for the wrong reason — a wrapper that fails
    on something else entirely would look identical.
    """
    root, bin_dir = _repo(tmp_path), _stub_docker(tmp_path)
    script = root / "scripts" / "build-immutable.sh"
    text = script.read_text(encoding="utf-8")
    start = text.index('if [[ -n "$changes" ]]; then')
    end = text.index("fi", start) + len("fi")
    script.write_text(text[:start] + text[end:], encoding="utf-8")

    (root / "docker-compose.v9.yml").write_text("services: {tampered: {}}\n", encoding="utf-8")
    result = _run(root, bin_dir)
    assert result.returncode == 0, "removing the check should let the dirty build through"
    assert (tmp_path / "docker.log").exists(), "docker should have been reached"


@pytest.fixture
def ps_build(tmp_path: Path):
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not powershell:
        pytest.skip("PowerShell is required to execute the Windows build wrapper")
    root = _repo(tmp_path, WRAPPER.with_suffix(".ps1"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    stub = bin_dir / "docker_stub.py"
    stub.write_text(
        "import os, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['DOCKER_TEST_LOG'], 'a', encoding='utf-8') as f:\n"
        "    print(os.environ.get('TESTED_SHA'), os.environ.get('SAHOOL_BUILD_ID'), *args, file=f)\n"
        "if args == ['compose', 'version']:\n"
        "    sys.exit(int(os.environ.get('VERSION_EXIT', '0')))\n"
        "if 'up' in args:\n"
        "    sys.exit(int(os.environ.get('UP_EXIT', '0')))\n"
        "if args[0] == 'info':\n"
        "    print(os.environ.get('ENGINE_OS', 'linux'))\n"
        "    if os.environ.get('INFO_EXIT') == '1':\n"
        "        print('failed to connect to dockerDesktopLinuxEngine', file=sys.stderr)\n"
        "    sys.exit(int(os.environ.get('INFO_EXIT', '0')))\n"
        "if 'config' in args:\n"
        "    sys.exit(int(os.environ.get('CONFIG_EXIT', '0')))\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        (bin_dir / "docker.cmd").write_text(
            '@echo off\n"%TEST_PYTHON%" "%DOCKER_STUB%" %*\nexit /b %ERRORLEVEL%\n',
            encoding="ascii",
        )
    else:
        launcher = bin_dir / "docker"
        launcher.write_text(
            '#!/bin/sh\nexec "$TEST_PYTHON" "$DOCKER_STUB" "$@"\n', encoding="ascii"
        )
        launcher.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "TEST_PYTHON": sys.executable,
        "DOCKER_STUB": str(stub),
        "DOCKER_TEST_LOG": str(log),
        "TESTED_SHA": "caller-value",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e",
    }
    env.pop("SAHOOL_BUILD_ID", None)

    options = ["-ExecutionPolicy", "RemoteSigned"] if os.name == "nt" else []

    def run(command: str, **overrides: str):
        return subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", *options, "-Command", command],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**env, **overrides},
            timeout=30,
        )

    return root, log, run


@pytest.mark.parametrize(
    ("overrides", "diagnosis", "config_attempts"),
    [
        ({"INFO_EXIT": "1"}, "Docker Engine is unreachable", 0),
        ({"ENGINE_OS": "windows"}, "requires a Linux Docker Engine", 0),
        ({"CONFIG_EXIT": "1"}, "config validation failed", 1),
    ],
)
def test_powershell_refuses_build_and_restores_caller_on_failure(
    ps_build, overrides, diagnosis, config_attempts
):
    _, log, run = ps_build
    result = run(
        "try { & ./scripts/build-immutable.ps1 -Gpu } catch { Write-Output $_.Exception.Message }; "
        'Write-Output "restored=$($env:TESTED_SHA)/$($env:SAHOOL_BUILD_ID)"',
        SAHOOL_BUILD_ID="operator-id",
        **overrides,
    )
    assert diagnosis in result.stdout, result.stderr
    assert "restored=caller-value/operator-id" in result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1 + config_attempts
    assert calls[0].endswith(" info --format {{.OSType}}")
    if config_attempts:
        assert calls[1].endswith(" config --quiet")


def test_powershell_uses_the_new_head_for_each_build_in_the_same_shell(ps_build):
    root, log, run = ps_build
    first = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, encoding="utf-8"
    ).strip()
    result = run(
        "$ErrorActionPreference='Stop'; $env:SAHOOL_BUILD_ID=''; "
        "$hadId = Test-Path Env:SAHOOL_BUILD_ID; & ./scripts/build-immutable.ps1 -Gpu -NoCache; "
        "git commit --quiet --allow-empty -m next; & ./scripts/build-immutable.ps1; "
        "if ((Test-Path Env:SAHOOL_BUILD_ID) -ne $hadId) { throw 'Empty build ID changed'; }; "
        'Write-Output "restored=$($env:TESTED_SHA)/$($env:SAHOOL_BUILD_ID)"'
    )
    assert result.returncode == 0, result.stderr
    assert "restored=caller-value/\n" in result.stdout
    second = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, encoding="utf-8"
    ).strip()
    assert first != second
    builds = [line for line in log.read_text(encoding="utf-8").splitlines() if " build" in line]
    assert builds == [
        f"{first} local-{first[:12]} compose -f docker-compose.v9.yml "
        "-f docker-compose.v9.gpu.yml --profile gpu build --no-cache",
        f"{second} local-{second[:12]} compose -f docker-compose.v9.yml build",
    ]


def test_powershell_fails_closed_on_unreadable_git_index(ps_build):
    root, log, run = ps_build
    (root / ".git" / "index").write_bytes(b"damaged index")
    result = run("& ./scripts/build-immutable.ps1")
    assert result.returncode != 0
    assert "Unable to verify the Git working tree" in result.stderr
    assert not log.exists()


def _install_legacy_scripts(root: Path) -> None:
    legacy = root / "scripts_v9"
    legacy.mkdir()
    for name in ("run_all.sh", "run_all.ps1", "setup.sh"):
        shutil.copy(WRAPPER.parents[1] / "scripts_v9" / name, legacy / name)
    (root / ".gitignore").write_text(".env\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "legacy entrypoints",
        ],
        cwd=root,
        check=True,
    )


@pytest.mark.parametrize("entry", ["setup.sh", "run_all.sh"])
def test_legacy_bash_bootstrap_preserves_credentials_and_requires_compose(tmp_path, entry):
    root, bin_dir = _repo(tmp_path), _stub_docker(tmp_path)
    _install_legacy_scripts(root)
    command = ["bash", str(root / "scripts_v9" / entry)]
    if entry == "run_all.sh":
        command.append("build")

    def run(*, version_exit="0"):
        return subprocess.run(
            command,
            cwd=tmp_path,
            text=True,
            encoding="utf-8",
            capture_output=True,
            env={
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "VERSION_EXIT": version_exit,
            },
        )

    log = tmp_path / "docker.log"
    env_file = root / ".env"
    first = run()
    assert first.returncode != 0 and "LOCAL_ENVIRONMENT_RUNBOOK" in first.stdout + first.stderr
    assert not env_file.exists() and not log.exists()
    env_file.write_bytes(b"VALUE=operator-private-test-value\n")
    missing_plugin = run(version_exit="8")
    assert missing_plugin.returncode != 0
    assert [call.split(" ", 2)[2] for call in log.read_text(encoding="utf-8").splitlines()] == [
        "compose version"
    ]
    for _ in range(2):
        result = run()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "operator-private-test-value" not in result.stdout + result.stderr
        assert env_file.read_bytes() == b"VALUE=operator-private-test-value\n"
    assert log.read_text(encoding="utf-8").count("config --quiet") == 2
    assert log.read_text(encoding="utf-8").count("docker-compose.v9.yml build") == 2
    assert not (tmp_path / ".env").exists()


def test_powershell_legacy_bootstrap_preserves_credentials_and_requires_compose(ps_build):
    root, log, run = ps_build
    _install_legacy_scripts(root)
    command = "& ./scripts_v9/run_all.ps1 build"
    first = run(command)
    env_file = root / ".env"
    assert first.returncode != 0 and "LOCAL_ENVIRONMENT_RUNBOOK" in first.stderr
    assert not env_file.exists() and not log.exists()
    env_file.write_bytes(b"VALUE=operator-private-test-value\r\n")
    missing_plugin = run(command, VERSION_EXIT="9")
    assert missing_plugin.returncode != 0 and "Compose v2 is unavailable" in missing_plugin.stderr
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1
    for _ in range(2):
        result = run(command)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "operator-private-test-value" not in result.stdout + result.stderr
        assert env_file.read_bytes() == b"VALUE=operator-private-test-value\r\n"
    assert log.read_text(encoding="utf-8").count("docker-compose.v9.yml build") == 2

    up = run("& ./scripts_v9/run_all.ps1 up", UP_EXIT="7")
    assert up.returncode != 0 and "Compose failed" in up.stderr
    assert "is running!" not in up.stdout
    assert "up -d --no-build" in log.read_text(encoding="utf-8")


def test_legacy_runtime_commands_preserve_identity_and_reset_only_the_project(tmp_path):
    root, bin_dir = _repo(tmp_path), _stub_docker(tmp_path)
    _install_legacy_scripts(root)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, encoding="utf-8"
    ).strip()
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "TESTED_SHA": "stale",
        "SAHOOL_BUILD_ID": "operator-id",
    }
    for args in (["down"], ["logs", "sahool-edge"], ["reset"]):
        subprocess.run(
            ["bash", str(root / "scripts_v9/run_all.sh"), *args],
            cwd=tmp_path,
            input="RESET\n",
            text=True,
            encoding="utf-8",
            check=True,
            env=env,
        )
    calls = (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines()
    assert len(calls) == 3
    assert all(f"TESTED_SHA={head} BUILD_ID=operator-id compose -f" in c for c in calls)
    assert calls[0].endswith(" down --remove-orphans")
    assert calls[1].endswith(" logs -f sahool-edge")
    assert calls[2].endswith(" down -v --remove-orphans")


def test_powershell_legacy_runtime_commands_restore_identity_and_limit_reset_to_project(ps_build):
    root, log, run = ps_build
    _install_legacy_scripts(root)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, encoding="utf-8"
    ).strip()
    result = run(
        "function Read-Host { 'RESET' }; & ./scripts_v9/run_all.ps1 down; "
        "& ./scripts_v9/run_all.ps1 logs sahool-edge; & ./scripts_v9/run_all.ps1 reset; "
        'Write-Output "restored=$($env:TESTED_SHA)/$($env:SAHOOL_BUILD_ID)"',
        SAHOOL_BUILD_ID="operator-id",
    )
    assert result.returncode == 0, result.stderr
    assert "restored=caller-value/operator-id" in result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 3 and all(c.startswith(f"{head} operator-id compose -f") for c in calls)
    assert calls[0].endswith(" down --remove-orphans")
    assert calls[1].endswith(" logs -f sahool-edge")
    assert calls[2].endswith(" down -v --remove-orphans")
