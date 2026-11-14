"""AC-1 point-in-time policy: a feature is eligible only when available_at <= decision cutoff.
Violations are TYPED reasons (fail-closed), never silently dropped or synthesized."""

from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Any

from shared.contracts.soil import validate_soil_profile_snapshot

from .contracts import CONTEXT_GROUPS, QUALITY_STATES, ContextComposeIn


def _non_finite_path(value: Any, path: str) -> str | None:
    """Path of the first non-finite float inside ``value`` (dicts, lists and tuples walked
    recursively), or ``None`` when every number is finite."""
    if isinstance(value, float):
        return None if math.isfinite(value) else path
    if isinstance(value, dict):
        for key, item in value.items():
            found = _non_finite_path(item, f"{path}.{key}")
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = _non_finite_path(item, f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _non_finite_numbers(payload: ContextComposeIn) -> list[dict[str, Any]]:
    """Typed violations for NaN/Infinity anywhere the composer hashes or persists.

    ``model_dump(mode="json")`` turns them into ``null``, so the manifest hash would cover a
    value nobody supplied; jsonb refuses them outright. The detail names a path only — never the
    value, which has no JSON spelling.
    """
    out: list[dict[str, Any]] = []
    for f in payload.features:
        found = _non_finite_path(f.value, "value")
        if found is not None:
            out.append({"code": "non_finite_number", "feature": f.name, "path": found})
    for root, value in (("context", payload.context), ("history", payload.historical.history)):
        found = _non_finite_path(value, root)
        if found is not None:
            out.append({"code": "non_finite_number", "path": found})
    return out


def _naive_timestamps(payload: ContextComposeIn) -> list[dict[str, Any]]:
    """Typed violations for every timestamp without a timezone.

    The contracts declare these fields ``AwareDatetime``, so a validated payload never carries
    one; this is the second line for a payload built without validation (``model_construct``,
    ``model_copy(update=...)``). Comparing a naive with an aware value raises ``TypeError``
    (HTTP 500) — the class of DECISION-PLAN-MIXED-TIMEZONE-500-01 — and even an all-naive
    payload has no defined instant to hold against the cutoff, so neither is compared.
    """
    stamps: list[tuple[str, str | None, Any]] = [
        ("as_of_time", None, payload.as_of_time),
        ("decision_cutoff_time", None, payload.decision_cutoff_time),
        ("history_from", None, payload.historical.history_from),
        ("history_to", None, payload.historical.history_to),
    ]
    for f in payload.features:
        stamps.append(("observed_at", f.name, f.observed_at))
        stamps.append(("available_at", f.name, f.available_at))
    out: list[dict[str, Any]] = []
    for field, feature, stamp in stamps:
        if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
            item: dict[str, Any] = {"code": "naive_timestamp", "field": field}
            if feature is not None:
                item["feature"] = feature
            out.append(item)
    return out


def validate_composition(payload: ContextComposeIn) -> list[dict[str, Any]]:
    """Return the list of typed violations; empty list == composition is admissible."""
    naive = _naive_timestamps(payload)
    if naive:
        # fail closed before any ordering comparison can raise TypeError
        return naive + _non_finite_numbers(payload)
    violations: list[dict[str, Any]] = _non_finite_numbers(payload)
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
