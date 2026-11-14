"""The frontend lock stays above the versions npm audit flagged on 2026-10-25.

DEP-FRONTEND-NPM-HIGH-ADVISORIES-20261025-01: `npm audit --package-lock-only` on
main@3e08bda5a found three high advisories (follow-redirects via axios in production,
vite and zod in tooling) and two moderate ones (vitest), and no gate caught them:
the blocking pip-audit covers Python only. #1271 raised the lock; this floor keeps
any later lock edit from sliding back below the fixed versions. Offline: it reads
the committed lock, no registry access.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

LOCK = Path(__file__).resolve().parents[1] / "frontend" / "package-lock.json"

# package -> (first fixed version, advisories it closes)
FLOORS = {
    "follow-redirects": ((1, 16, 1), "GHSA-q3jh-wrc6-jgq8, GHSA-8r9p-f939-6h3c"),
    "vite": ((8, 1, 6), "GHSA-587h-7wmj-h5pm and four more up to 8.1.5"),
    "zod": ((4, 6, 6), "GHSA-mrhx-c7xc-m3w5"),
    "vitest": ((5, 0, 3), "GHSA-qxg6-89mg-rqv8 / GHSA-xp26-3454-mjgp via @vitest/mocker"),
    "@vitest/mocker": ((5, 0, 3), "GHSA-qxg6-89mg-rqv8, GHSA-xp26-3454-mjgp"),
}


def _version(text: str) -> tuple[int, ...]:
    core = text.split("-", 1)[0].split("+", 1)[0]
    return tuple(int(part) for part in core.split("."))


def _installed() -> dict[str, list[str]]:
    packages = json.loads(LOCK.read_text(encoding="utf-8"))["packages"]
    found: dict[str, list[str]] = {name: [] for name in FLOORS}
    for path, meta in packages.items():
        name = path.rsplit("node_modules/", 1)[-1]
        if name in found and "version" in meta:
            found[name].append(meta["version"])
    return found


@pytest.mark.parametrize("name", sorted(FLOORS))
def test_every_locked_copy_is_at_or_above_the_fixed_version(name):
    floor, advisories = FLOORS[name]
    versions = _installed()[name]
    assert versions, f"{name} vanished from the lock; re-check the advisory floor"
    stale = [v for v in versions if _version(v) < floor]
    assert not stale, f"{name} {stale} below {'.'.join(map(str, floor))} ({advisories})"


def test_the_floor_rejects_the_audited_lock():
    """Falsifies the comparison: the versions npm audit flagged must fail it."""
    flagged = {
        "follow-redirects": "1.16.0",
        "vite": "8.0.16",
        "zod": "4.4.3",
        "vitest": "5.0.2",
        "@vitest/mocker": "5.0.2",
    }
    for name, version in flagged.items():
        assert _version(version) < FLOORS[name][0], name
    assert _version("8.3.5-beta.1") == (8, 3, 5)


# GHSA-g3hv-75wg-m249: minimatch >=7.0.0 <11.0.1. The lock reached 10.2.x through
# @typescript-eslint/typescript-estree until package.json `overrides` pinned it. eslint's
# own minimatch@3.x is outside the advisory range, so the floor applies to majors >= 7 and,
# separately, to the copy typescript-estree actually resolves (npm's nested-then-hoisted walk).
MINIMATCH_FLOOR = (11, 0, 1)
MINIMATCH_ADVISORY_FROM = (7, 0, 0)


def _resolve(packages: dict, dependent: str, name: str) -> str | None:
    """Return the lock path npm resolves `name` to from the `dependent` package path."""
    base = dependent
    while True:
        candidate = f"{base}/node_modules/{name}" if base else f"node_modules/{name}"
        if candidate in packages:
            return candidate
        if not base:
            return None
        # climb out of the innermost node_modules/<pkg> segment
        base = base.rsplit("/node_modules/", 1)[0] if "/node_modules/" in base else ""


def _minimatch_violations(packages: dict) -> list[str]:
    bad = []
    for path, meta in packages.items():
        if path.rsplit("node_modules/", 1)[-1] != "minimatch" or "version" not in meta:
            continue
        version = _version(meta["version"])
        if MINIMATCH_ADVISORY_FROM <= version < MINIMATCH_FLOOR:
            bad.append(f"{path}@{meta['version']}")
    estree = [
        p
        for p in packages
        if p.rsplit("node_modules/", 1)[-1] == "@typescript-eslint/typescript-estree"
    ]
    if not estree:
        bad.append("@typescript-eslint/typescript-estree vanished from the lock")
    for dependent in estree:
        resolved = _resolve(packages, dependent, "minimatch")
        version = packages.get(resolved, {}).get("version") if resolved else None
        if version is None or _version(version) < MINIMATCH_FLOOR:
            bad.append(f"{dependent} resolves minimatch {version} ({resolved})")
    return bad


def test_minimatch_under_typescript_estree_is_at_or_above_the_fixed_version():
    packages = json.loads(LOCK.read_text(encoding="utf-8"))["packages"]
    bad = _minimatch_violations(packages)
    assert not bad, f"minimatch below 11.0.1 (GHSA-g3hv-75wg-m249): {bad}"


def test_the_minimatch_floor_rejects_the_audited_lock():
    """Falsifier: the pre-override lock shape (10.2.6 nested under typescript-estree)."""
    estree = "node_modules/@typescript-eslint/typescript-estree"
    audited = {
        estree: {"version": "8.71.1"},
        f"{estree}/node_modules/minimatch": {"version": "10.2.6"},
        "node_modules/minimatch": {"version": "3.1.5"},
    }
    assert _minimatch_violations(audited)
    hoisted = {estree: {"version": "8.71.1"}, "node_modules/minimatch": {"version": "10.2.6"}}
    assert any("resolves minimatch 10.2.6" in v for v in _minimatch_violations(hoisted))
    fixed = {**audited, f"{estree}/node_modules/minimatch": {"version": "11.0.1"}}
    assert not _minimatch_violations(fixed)


# Strict peer policy: frontend/.npmrc says legacy-peer-deps=false; a CLI flag in an image
# build overrides .npmrc, so the Railway production image silently diverged from CI.
NPM_INSTALL_SITES = (
    "frontend/Dockerfile",
    "deploy/railway/Dockerfile.frontend",
    "run_all.sh",
    "run_all.ps1",
    "frontend/run_all.sh",
    "frontend/run_all.ps1",
)


def test_frontend_images_install_with_the_strict_peer_policy():
    root = LOCK.parents[1]
    npmrc = (root / "frontend/.npmrc").read_text(encoding="utf-8")
    assert "legacy-peer-deps=false" in npmrc
    for site in NPM_INSTALL_SITES:
        text = (root / site).read_text(encoding="utf-8")
        runs = [line for line in text.splitlines() if "npm ci" in line or "npm install" in line]
        assert runs, f"{site}: no npm install step found"
        flagged = [line for line in runs if "--legacy-peer-deps" in line]
        assert not flagged, f"{site} overrides .npmrc: {flagged}"
