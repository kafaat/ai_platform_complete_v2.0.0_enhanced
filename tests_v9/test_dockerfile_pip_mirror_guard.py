"""Guard: every service Dockerfile that runs ``pip install`` defaults its index to the
public PyPI, not the Tencent Cloud mirror, and every such ``pip install`` passes
``--timeout``/``--retries`` so a transient network hiccup doesn't fail the whole build.

Operational history:
- 2026-07-08: the operator reported ``pypi.org`` unreachable from our network even with a
  VPN, so ``ARG PIP_INDEX_URL`` was pinned to the Tencent Cloud mirror
  (``https://mirrors.cloud.tencent.com/pypi/simple/``) as the build-time default.
- 2026-07-09: the Tencent mirror was found to serve a corrupted ``pip`` package (bad
  hash), breaking builds outright. The default was switched back to the public PyPI
  (commit "fixing pip mirrors") — still overridable via
  ``--build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/`` or similar.
- Same day: a `sahool-ai-agronomist` build failed against the new PyPI default with
  "Could not find a version that satisfies the requirement pydantic-core==2.46.4
  (from versions: none)" while ~30 other images built in parallel — a transient
  index-connectivity hiccup, not a missing package (pydantic-core 2.46.4 exists on
  PyPI). Its Dockerfile was the one holdout still missing ``--timeout``/``--retries``
  that every sibling Dockerfile already had. Both defects are now guarded here.

Every mention of the Tencent host in this file is a stale Tencent mirror reference kept
for operational history — the guard *forbids* it as a default, never requires it.

Static scan (no image build) — Unit Tests tier. For every Dockerfile under services/,
agents/, and bots/ that runs ``pip install``, assert: (1) it declares an
``ARG PIP_INDEX_URL`` whose default is the public PyPI, never the Tencent mirror, and
(2) every ``pip install`` invocation that hits the network (i.e. not a bare
``--upgrade pip`` with no index-resolved package) passes ``--timeout`` and ``--retries``.
Safety floor: at least 25 such Dockerfiles must be found so the guard cannot pass
silently empty.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SCAN_DIRS = ["services", "agents", "bots"]
_TENCENT = "mirrors.cloud.tencent.com/pypi/simple"
_PYPI = "pypi.org/simple"
_MIN_PIP_DOCKERFILES = 25

# Default value of the ARG PIP_INDEX_URL declaration (the build-time default).
_ARG_INDEX = re.compile(r"^\s*ARG\s+PIP_INDEX_URL=(\S+)", re.MULTILINE)
# Every `pip install` / `python -m pip install` invocation, keeping the rest of the
# line (and a lookahead for a `\`-continued next line) so we can check for the flags.
_PIP_INSTALL = re.compile(
    r"pip install\b[^\n]*(?:\\\n[^\n]*)*",
)


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


def test_pip_dockerfiles_default_to_public_pypi():
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
        if _TENCENT in default:
            offenders.append(
                f"{rel}: PIP_INDEX_URL default is still the Tencent mirror ({default!r}) — "
                "it serves a corrupted pip package, switch the default to public PyPI"
            )
        elif _PYPI not in default:
            offenders.append(f"{rel}: PIP_INDEX_URL default is {default!r}, not public PyPI")

    assert not offenders, (
        "Dockerfiles must default PIP_INDEX_URL to public PyPI "
        f"({_PYPI}) — the Tencent mirror serves a corrupted pip package:\n  "
        + "\n  ".join(offenders)
    )


def test_pip_installs_pass_timeout_and_retries():
    """Every network-resolving `pip install` must retry — one missing pair caused a
    real build failure (sahool-ai-agronomist, 2026-07-09) under concurrent-build load."""
    dockerfiles = _pip_dockerfiles()

    offenders: list[str] = []
    for df in dockerfiles:
        text = df.read_text(encoding="utf-8")
        rel = str(df.relative_to(_ROOT))
        for match in _PIP_INSTALL.finditer(text):
            line = match.group(0)
            # `pip install --upgrade pip` alone doesn't resolve a versioned dependency
            # graph against the index the way a requirements/package install does, but
            # every occurrence in this codebase installs at least one real package
            # (setuptools/wheel or a pinned requirement), so require the flags uniformly.
            if "--timeout" not in line or "--retries" not in line:
                offenders.append(f"{rel}: pip install missing --timeout/--retries: {line!r}")

    assert not offenders, (
        "Every pip install in a Dockerfile must pass --timeout 300 --retries 10 (or "
        "equivalent) so a transient index hiccup under concurrent builds doesn't fail "
        "the whole image:\n  " + "\n  ".join(offenders)
    )
