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
