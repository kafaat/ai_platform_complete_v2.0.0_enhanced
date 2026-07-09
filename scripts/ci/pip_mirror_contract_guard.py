#!/usr/bin/env python3
"""Guard the connected-CI pip index / mirror contract.

Default package index is official PyPI. Alibaba Cloud PyPI remains a first-class operator
override for CI environments where it is faster or required. The guard is static and does
not contact the internet.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPI = "https://pypi.org/simple"
ALIBABA = "https://mirrors.aliyun.com/pypi/simple/"
TENCENT = "mirrors.cloud.tencent.com/pypi/simple"
REQUIRED = [
    ROOT / "scripts/ci/pip_mirror_env.sh",
    ROOT / "scripts/ci/compile_transitive_service_locks.sh",
    ROOT / ".github/workflows/transitive-lock-compile-manual.yml",
    ROOT / ".pip/pip-alibaba.conf",
    ROOT / "docs/runbooks/ALIBABA_PYPI_MIRROR.md",
    ROOT / "tests_v9/test_dockerfile_pip_mirror_guard.py",
]

SECRETISH_URL_RE = re.compile(r"https?://[^/\s:@]+:[^/\s@]+@")


def read(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"missing required pip mirror contract file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="ignore")


def main() -> None:
    blobs = {p: read(p) for p in REQUIRED}
    combined = "\n".join(blobs.values())
    env_script = blobs[ROOT / "scripts/ci/pip_mirror_env.sh"]
    docker_guard = blobs[ROOT / "tests_v9/test_dockerfile_pip_mirror_guard.py"]
    workflow = blobs[ROOT / ".github/workflows/transitive-lock-compile-manual.yml"]

    if PYPI not in env_script or 'DEFAULT_PYPI_INDEX_URL="https://pypi.org/simple"' not in env_script:
        raise SystemExit("pip mirror env must default to official PyPI")
    if ALIBABA not in combined or "ALIBABA_PYPI_MIRROR" not in env_script:
        raise SystemExit("Alibaba PyPI mirror must remain documented and overridable")
    if "PIP_INDEX_URL" not in combined or "PYPI_MIRROR_URL" not in combined:
        raise SystemExit("mirror contract must be overridable via PIP_INDEX_URL/PYPI_MIRROR_URL")
    if SECRETISH_URL_RE.search(combined):
        raise SystemExit("mirror URL must not contain embedded credentials")
    if TENCENT in docker_guard:
        # The string may appear as a stale-reference sentinel, but the guard must not enforce it.
        if "stale Tencent mirror reference" not in docker_guard:
            raise SystemExit("Dockerfile mirror guard must not enforce Tencent mirror defaults")
    compile_script = blobs[ROOT / "scripts/ci/compile_transitive_service_locks.sh"]
    if "source scripts/ci/pip_mirror_env.sh" not in compile_script:
        raise SystemExit("transitive lock compiler must source pip_mirror_env.sh")
    if "--index-url \"$PIP_INDEX_URL\"" not in compile_script:
        raise SystemExit("pip-compile must use the configured PIP_INDEX_URL")
    if "PIP_DEFAULT_TIMEOUT" not in env_script or "PIP_RETRIES" not in env_script:
        raise SystemExit("pip index contract must define retry/timeout environment controls")
    if "--timeout" not in docker_guard or "--retries" not in docker_guard:
        raise SystemExit("Dockerfile mirror guard must enforce pip retry/timeout controls")
    if "default: 'https://pypi.org/simple'" not in workflow:
        raise SystemExit("transitive lock manual workflow must default to official PyPI")
    print("✓ PyPI-default + Alibaba override pip mirror contract guard passed")


if __name__ == "__main__":
    main()
