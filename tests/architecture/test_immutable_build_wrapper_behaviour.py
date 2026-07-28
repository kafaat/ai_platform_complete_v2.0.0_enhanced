"""The bash wrapper must *behave*, not merely contain the right strings.

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
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

WRAPPER = Path(__file__).resolve().parents[2] / "scripts" / "build-immutable.sh"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def _repo(tmp_path: Path) -> Path:
    """A throwaway git repo carrying a copy of the wrapper."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "build-immutable.sh").write_bytes(WRAPPER.read_bytes())
    (root / "scripts" / "build-immutable.sh").chmod(0o755)
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
        f'echo "TESTED_SHA=${{TESTED_SHA:-<unset>}} BUILD_ID=${{SAHOOL_BUILD_ID:-<unset>}} $*" >> {log}\n'
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


def test_the_guard_is_the_check_not_the_wording(tmp_path: Path):
    """Falsification: strip the dirty-tree check and the dirty tree must start building.

    Without this, the test above could pass for the wrong reason — a wrapper that fails
    on something else entirely would look identical.
    """
    root, bin_dir = _repo(tmp_path), _stub_docker(tmp_path)
    script = root / "scripts" / "build-immutable.sh"
    text = script.read_text(encoding="utf-8")
    start = text.index('if [[ -n "$(git status --porcelain)" ]]; then')
    end = text.index("fi", start) + len("fi")
    script.write_text(text[:start] + text[end:], encoding="utf-8")

    (root / "docker-compose.v9.yml").write_text("services: {tampered: {}}\n", encoding="utf-8")
    result = _run(root, bin_dir)
    assert result.returncode == 0, "removing the check should let the dirty build through"
    assert (tmp_path / "docker.log").exists(), "docker should have been reached"
