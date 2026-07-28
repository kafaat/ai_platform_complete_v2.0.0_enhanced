"""The Knowledge Brain may not state a verified/certified count the registry contradicts.

`scripts/ci/brain_state_transition_guard.py` stops a brain-ONLY edit from *claiming*
closure or verification without executable backing. This module is that backing: it
makes the brain's governed numbers falsifiable against the authoritative source
(`capabilities/registry/capabilities.json`), so the documentation can never drift into
asserting a runtime/production state the platform has not actually reached.

Deliberately narrow — it checks NUMERIC state assertions only (``runtime_verified: 3``,
``production_certified = 1``). Prose that mentions the tokens while *denying* a claim
(e.g. "never sets production_certified=true", "zero runtime_verified in the outputs")
is not a state assertion and must keep working; the brain has to be able to name these
fields to document them at all.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAIN = ROOT / "sahool-brain"
REGISTRY = ROOT / "capabilities" / "registry" / "capabilities.json"
PLATFORM_ROOT = ROOT / "services" / "sahool-platform"

# "<field><spaces>[:=]<spaces><digits>" — a numeric state assertion, nothing else.
_NUMERIC_CLAIM = re.compile(r"\b(runtime_verified|production_certified)\s*[:=]\s*(\d+)\b")

# The brain writes the three-layer route count in one canonical Arabic shape:
#   "خام 630 · بنية 4 · نطاق 626"   (separator may also be "/")
_ROUTE_LAYERS = re.compile(r"خام\s+(\d+)\s*[·/]\s*بنية\s+(\d+)\s*[·/]\s*نطاق\s+(\d+)")


def _registry_counts() -> dict[str, int]:
    capabilities = json.loads(REGISTRY.read_text(encoding="utf-8"))["capabilities"]
    return {
        "runtime_verified": sum(1 for c in capabilities if c.get("runtime_verified")),
        "production_certified": sum(1 for c in capabilities if c.get("production_certified")),
    }


def test_registry_runtime_and_production_state_is_zero():
    """The honest zero-baseline: no capability is runtime_verified or production_certified.

    Flipping either is a separate, reviewed step gated on real Step-3 functional
    evidence from a trusted environment. If this test ever fails, the flip must have
    arrived with that evidence — update the baseline deliberately, never casually.
    """
    counts = _registry_counts()
    assert counts["runtime_verified"] == 0, counts
    assert counts["production_certified"] == 0, counts


def test_brain_numeric_state_claims_match_registry():
    """Every numeric runtime/production figure written in the brain matches reality."""
    counts = _registry_counts()
    violations: list[str] = []
    for path in sorted(BRAIN.rglob("*.md")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for field, value in _NUMERIC_CLAIM.findall(line):
                if int(value) != counts[field]:
                    rel = path.relative_to(ROOT)
                    violations.append(
                        f"{rel}:{lineno}: {field}={value} but registry={counts[field]}"
                    )
    assert violations == [], (
        "brain states a verified/certified count the registry denies:\n" + "\n".join(violations)
    )


def _route_layer_counts() -> tuple[int, int, int]:
    """(raw, infrastructure, domain) measured from the source, not from a report."""
    sys.path.insert(0, str(ROOT / "scripts" / "ci"))
    try:
        from platform_route_classification import collect_platform_routes, partition_routes
    finally:
        sys.path.pop(0)
    routes = collect_platform_routes(PLATFORM_ROOT)
    infrastructure, domain = partition_routes(routes)
    return len(routes), len(infrastructure), len(domain)


def test_brain_route_layer_counts_match_the_measured_surface():
    """The brain's raw/infrastructure/domain triple is falsifiable against the code.

    The three-layer count is a governance claim: it is what justifies excluding four
    infrastructure endpoints from the domain ratchet without raising the budget. Left
    as prose it would rot the moment a route moves, and a stale triple in the brain
    reads as if the exclusion were larger than it is.
    """
    expected = _route_layer_counts()
    violations: list[str] = []
    found = 0
    for path in sorted(BRAIN.rglob("*.md")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for raw, infra, domain in _ROUTE_LAYERS.findall(line):
                found += 1
                stated = (int(raw), int(infra), int(domain))
                if stated != expected:
                    rel = path.relative_to(ROOT)
                    violations.append(f"{rel}:{lineno}: states {stated} but measured {expected}")
    assert violations == [], (
        "brain states a route-layer count the platform source denies "
        "(raw, infrastructure, domain):\n" + "\n".join(violations)
    )
    assert found > 0, (
        "no route-layer claim found in the brain — the counts must stay documented "
        "in the canonical 'خام N · بنية N · نطاق N' shape so this test can check them"
    )
