"""Guard: pip Dockerfiles default to official PyPI, with Alibaba mirror override.

This replaces the stale Tencent-mirror decision. Build-time dependency resolution should
not be pinned to Tencent by default; operators can still select Alibaba Cloud PyPI with
``--build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/`` or any private
mirror. Every pip install in Dockerfiles must include explicit retry/timeout controls so
PyPI or mirror flakiness is bounded and observable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SCAN_DIRS = ["services", "agents", "bots"]
_PYPI = "https://pypi.org/simple"
_ALIBABA = "https://mirrors.aliyun.com/pypi/simple/"
_TENCENT = "mirrors.cloud.tencent.com/pypi/simple"
_MIN_PIP_DOCKERFILES = 25

_ARG_INDEX = re.compile(r"^\s*ARG\s+PIP_INDEX_URL=(\S+)", re.MULTILINE)
_PIP_INSTALL_LINE = re.compile(r"^.*(?:python\s+-m\s+)?pip\s+install\b.*$", re.MULTILINE)


def _pip_dockerfiles() -> list[Path]:
    out: list[Path] = []
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.is_dir():
            continue
        for df in base.rglob("Dockerfile*"):
            if ".claude" in df.parts:
                continue
            try:
                text = df.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "pip install" in text:
                out.append(df)
    return sorted(out)


def test_pip_dockerfiles_default_to_pypi_with_alibaba_override_and_bounded_installs():
    dockerfiles = _pip_dockerfiles()
    assert len(dockerfiles) >= _MIN_PIP_DOCKERFILES, (
        f"only {len(dockerfiles)} pip Dockerfiles found; expected >={_MIN_PIP_DOCKERFILES} "
        "(check the scan path or a service-deletion regression)"
    )

    offenders: list[str] = []
    for df in dockerfiles:
        text = df.read_text(encoding="utf-8")
        rel = str(df.relative_to(_ROOT))
        m = _ARG_INDEX.search(text)
        if m is None:
            offenders.append(f"{rel}: runs pip install but declares no ARG PIP_INDEX_URL")
        elif m.group(1) != _PYPI:
            offenders.append(f"{rel}: PIP_INDEX_URL default is {m.group(1)!r}, not official PyPI {_PYPI!r}")
        if _TENCENT in text:
            offenders.append(f"{rel}: stale Tencent mirror reference remains")
        if _ALIBABA not in text:
            offenders.append(f"{rel}: Alibaba mirror override is not documented in the Dockerfile")
        for line in _PIP_INSTALL_LINE.findall(text):
            if "--timeout" not in line or "--retries" not in line:
                offenders.append(f"{rel}: pip install line lacks --timeout/--retries: {line.strip()}")

    assert not offenders, (
        "Dockerfiles must default PIP_INDEX_URL to official PyPI, document Alibaba override, "
        "and bound pip install with retry/timeout controls:\n  " + "\n  ".join(offenders)
    )
