"""Guard: no service Dockerfile declares a ``VOLUME`` instruction.

Railway validates the Dockerfile before building and rejects ``VOLUME``
("dockerfile invalid: docker VOLUME at Line 33 is not supported"), so the build
stops before any image exists. ``services/knowledge-graph/Dockerfile`` carried
``VOLUME ["/data"]`` and could not be deployed on Railway (measured 2026-11-25 in
the integration environment). Persistence belongs to the platform instead: a
compose named volume (populated from the image's /data on first mount, so the
non-root ownership set at build time is kept), a Helm volume, or a Railway volume.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SCAN_DIRS = ("services", "agents", "bots", "deploy", "frontend")
_VOLUME = re.compile(r"^\s*VOLUME\b", re.IGNORECASE | re.MULTILINE)
_MIN_DOCKERFILES = 25


def _tracked_dockerfiles() -> list[Path] | None:
    """Every tracked Dockerfile* in the repository, wherever it lives (None outside git)."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", ":(glob)**/Dockerfile*", "Dockerfile*"],
            cwd=_ROOT,
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    names = {n for n in result.stdout.decode("utf-8", "replace").split("\0") if n}
    return sorted(_ROOT / n for n in names if (_ROOT / n).is_file())


def _dockerfiles() -> list[Path]:
    tracked = _tracked_dockerfiles()
    if tracked:
        return tracked
    out: list[Path] = []
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.is_dir():
            continue
        for df in base.rglob("Dockerfile*"):
            if ".claude" in df.relative_to(_ROOT).parts or not df.is_file():
                continue
            out.append(df)
    return sorted(out)


def test_scan_sees_the_service_dockerfiles() -> None:
    files = _dockerfiles()
    assert len(files) >= _MIN_DOCKERFILES, f"only {len(files)} Dockerfiles found"
    assert _ROOT / "services/knowledge-graph/Dockerfile" in files
    # The reviewer of #1623 noted frontend/Dockerfile sat outside the old directory list.
    assert _ROOT / "frontend/Dockerfile" in files


def test_no_dockerfile_declares_volume() -> None:
    offenders = []
    for df in _dockerfiles():
        text = df.read_text(encoding="utf-8", errors="replace")
        for m in _VOLUME.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            offenders.append(f"{df.relative_to(_ROOT)}:{line}")
    assert not offenders, (
        "VOLUME is rejected by Railway's Dockerfile validation; declare persistence in "
        "compose/Helm/Railway instead: " + ", ".join(offenders)
    )


def test_guard_catches_a_volume_line() -> None:
    assert _VOLUME.search('USER app\nVOLUME ["/data"]\nEXPOSE 8000\n')
    assert _VOLUME.search("  volume /data\n")
    assert not _VOLUME.search("# kept: no VOLUME here\nENV KG_SQLITE_PATH=/data/kg.sqlite\n")
