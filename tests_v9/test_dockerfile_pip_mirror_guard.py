"""Guard: every service Dockerfile that runs ``pip install`` defaults its index to the
Tencent Cloud PyPI mirror (overridable), not the public PyPI.

Operational reason (reported by the operator 2026-07-08): image builds against
``pypi.org`` fail constantly from our network even with a VPN. The Tencent Cloud mirror
(``https://mirrors.cloud.tencent.com/pypi/simple/``) is reliable, so it is pinned as the
build-time default via ``ARG PIP_INDEX_URL`` — still overridable with
``--build-arg PIP_INDEX_URL=https://pypi.org/simple`` for global builds.

Static scan (no image build) — Unit Tests tier. For every Dockerfile under services/ (plus
agents/ and bots/) that runs ``pip install``, assert it declares an ``ARG PIP_INDEX_URL``
whose default is the Tencent mirror and never the public PyPI host. Safety floor: at least
25 such Dockerfiles must be found so the guard cannot pass silently empty.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SCAN_DIRS = ["services", "agents", "bots"]
_TENCENT = "mirrors.cloud.tencent.com/pypi/simple"
_MIN_PIP_DOCKERFILES = 25

# Default value of the ARG PIP_INDEX_URL declaration (the build-time default).
_ARG_INDEX = re.compile(r"^\s*ARG\s+PIP_INDEX_URL=(\S+)", re.MULTILINE)


def _pip_dockerfiles() -> list[Path]:
    out: list[Path] = []
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.is_dir():
            continue
        for df in base.rglob("Dockerfile*"):
            if ".claude" in df.parts:  # skip other branches' worktrees
                continue
            try:
                text = df.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "pip install" in text:
                out.append(df)
    return sorted(out)


def test_pip_dockerfiles_default_to_tencent_mirror():
    dockerfiles = _pip_dockerfiles()
    assert len(dockerfiles) >= _MIN_PIP_DOCKERFILES, (
        f"only {len(dockerfiles)} pip Dockerfiles found; expected >={_MIN_PIP_DOCKERFILES} "
        "(check the scan path or a service-deletion regression)"
    )

    offenders: list[str] = []
    for df in dockerfiles:
        text = df.read_text(encoding="utf-8")
        m = _ARG_INDEX.search(text)
        rel = str(df.relative_to(_ROOT))
        if m is None:
            offenders.append(f"{rel}: runs pip install but declares no ARG PIP_INDEX_URL")
            continue
        default = m.group(1)
        if _TENCENT not in default:
            offenders.append(f"{rel}: PIP_INDEX_URL default is {default!r}, not the Tencent mirror")

    assert not offenders, (
        "Dockerfiles must default PIP_INDEX_URL to the Tencent mirror "
        f"({_TENCENT}) so builds don't hit unreachable pypi.org:\n  " + "\n  ".join(offenders)
    )
