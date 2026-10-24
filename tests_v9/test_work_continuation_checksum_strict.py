"""The checksum command CLAUDE.md gives for the vendored skill must catch a deleted file.

``.claude/skills/work-continuation/`` is vendored byte for byte, and CLAUDE.md tells a
session to confirm that by running ``sha256sum`` on the ``SHA256SUMS`` inside it. The
line used to read ``sha256sum -c --ignore-missing SHA256SUMS``. With that flag GNU
``sha256sum`` skips every listed file that is absent and exits 0 as long as one file
still matches, so a package that lost ``SKILL.md`` or ``scripts/validate_package.py``
passed the check it was told to run.

Before the line was made strict, every file listed in ``SHA256SUMS`` was confirmed
present (``sha256sum -c SHA256SUMS`` exits 0 on the vendored folder), so no file is
absent on purpose and the flag had nothing legitimate to skip.

The tests run the command **as CLAUDE.md writes it**, not a copy kept here, so they fail
again if the flag comes back. They only read the vendored folder; deletions happen in a
copy under ``tmp_path``.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        shutil.which("sha256sum") is None,
        reason="GNU coreutils sha256sum is not installed; CI runners have it",
    ),
]

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".claude" / "skills" / "work-continuation"
MANIFEST = "SHA256SUMS"
STRICT = ["sha256sum", "-c", MANIFEST]
LENIENT = ["sha256sum", "-c", "--ignore-missing", MANIFEST]

# A backticked `sha256sum ... SHA256SUMS` span in CLAUDE.md.
_COMMAND = re.compile(r"`(sha256sum\s[^`\n]*\bSHA256SUMS)`")


def _listed() -> list[str]:
    entries = []
    for line in (SKILL_DIR / MANIFEST).read_text(encoding="utf-8").splitlines():
        digest, sep, rel = line.partition("  ")
        assert sep and re.fullmatch(r"[0-9a-f]{64}", digest), f"bad manifest line: {line!r}"
        entries.append(rel)
    assert entries, f"{MANIFEST} lists no files"
    return entries


def _documented_command() -> list[str]:
    """The single checksum command CLAUDE.md tells a session to run, as argv."""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    found = _COMMAND.findall(text)
    assert len(found) == 1, (
        f"CLAUDE.md should give exactly one `sha256sum ... SHA256SUMS` command, found {found}"
    )
    argv = shlex.split(found[0])
    # Executed without a shell: allow only sha256sum, its flags, and the manifest name,
    # so whatever the line says can never name another program or another file.
    assert argv[0] == "sha256sum" and argv[-1] == MANIFEST, argv
    assert all(arg.startswith("-") for arg in argv[1:-1]), argv
    assert {"-c", "--check"} & set(argv), f"the documented command does not check: {argv}"
    return argv


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "LC_ALL": "C"},
        check=False,
    )


def _copy_without(tmp_path: Path, rel: str, index: int) -> Path:
    copy = tmp_path / f"case{index:02d}"
    shutil.copytree(SKILL_DIR, copy, symlinks=True)
    (copy / rel).unlink()
    return copy


def test_every_listed_file_is_present_and_the_strict_check_passes():
    """The strict form is satisfiable: no listed file is absent from the vendored folder."""
    missing = [rel for rel in _listed() if not (SKILL_DIR / rel).is_file()]
    assert missing == [], f"listed in {MANIFEST} but absent: {missing}"
    result = _run(STRICT, SKILL_DIR)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_documented_command_passes_on_the_vendored_folder():
    result = _run(_documented_command(), SKILL_DIR)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_documented_command_fails_when_any_listed_file_is_deleted(tmp_path):
    """Remove each listed file in turn from a copy; the CLAUDE.md command must fail every time."""
    argv = _documented_command()
    passed_anyway = []
    for index, rel in enumerate(_listed()):
        result = _run(argv, _copy_without(tmp_path, rel, index))
        if result.returncode == 0:
            passed_anyway.append(rel)
    assert passed_anyway == [], (
        f"`{shlex.join(argv)}` (from CLAUDE.md) exited 0 with these listed files deleted: "
        f"{passed_anyway}. Drop --ignore-missing: it skips absent files instead of failing."
    )


def test_ignore_missing_hides_a_deleted_file_that_the_strict_check_reports(tmp_path):
    """Why the flag is not used: on the same copy, strict fails and --ignore-missing passes."""
    copy = _copy_without(tmp_path, "SKILL.md", 0)

    strict = _run(STRICT, copy)
    assert strict.returncode != 0
    assert "SKILL.md" in strict.stdout + strict.stderr

    lenient = _run(LENIENT, copy)
    assert lenient.returncode == 0, (
        "expected GNU --ignore-missing to skip the deleted file and pass: "
        + lenient.stdout
        + lenient.stderr
    )
