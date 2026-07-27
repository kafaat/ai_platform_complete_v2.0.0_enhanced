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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAIN = ROOT / "sahool-brain"
REGISTRY = ROOT / "capabilities" / "registry" / "capabilities.json"

# "<field><spaces>[:=]<spaces><digits>" — a numeric state assertion, nothing else.
_NUMERIC_CLAIM = re.compile(r"\b(runtime_verified|production_certified)\s*[:=]\s*(\d+)\b")


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
