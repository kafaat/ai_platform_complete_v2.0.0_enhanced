"""AC-1 point-in-time policy: a feature is eligible only when available_at <= decision cutoff.
Violations are TYPED reasons (fail-closed), never silently dropped or synthesized."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from shared.contracts.soil import validate_soil_profile_snapshot

from .contracts import CONTEXT_GROUPS, QUALITY_STATES, ContextComposeIn


def validate_composition(payload: ContextComposeIn) -> list[dict[str, Any]]:
    """Return the list of typed violations; empty list == composition is admissible."""
    violations: list[dict[str, Any]] = []
    cutoff: datetime = payload.decision_cutoff_time
    if payload.as_of_time > cutoff:
        violations.append(
            {"code": "as_of_after_cutoff", "detail": "as_of_time is after the decision cutoff"}
        )
    missing_groups = [g for g in CONTEXT_GROUPS if g not in payload.context]
    if missing_groups:
        violations.append({"code": "missing_context_groups", "groups": missing_groups})

    require_soil_profile = (
        os.getenv("DECISION_REQUIRE_SOIL_PROFILE", "").strip().lower() in {"1", "true", "yes", "on"}
        or os.getenv("SAHOOL_ENV", "development").strip().lower() == "production"
    )
    if require_soil_profile:
        soil_snapshot, soil_issues = validate_soil_profile_snapshot(payload.context.get("soil"))
        if soil_snapshot is None:
            violations.append(
                {
                    "code": "canonical_soil_profile_required",
                    "issues": soil_issues,
                }
            )
        elif not soil_snapshot.quality_gate.passed:
            violations.append({"code": "soil_profile_quality_gate_failed"})
    for f in payload.features:
        if f.quality_status not in QUALITY_STATES:
            violations.append({"code": "invalid_quality_status", "feature": f.name})
        if f.observed_at > f.available_at:
            violations.append({"code": "observed_after_available", "feature": f.name})
        if f.available_at > cutoff:
            # future leakage: the value was not available when the decision would be made.
            violations.append(
                {
                    "code": "future_leakage",
                    "feature": f.name,
                    "available_at": f.available_at.isoformat(),
                    "cutoff": cutoff.isoformat(),
                }
            )
    h = payload.historical
    if h.history_to > payload.as_of_time:
        violations.append({"code": "history_extends_past_as_of"})
    if h.history_from >= h.history_to:
        violations.append({"code": "empty_history_window"})
    return violations
