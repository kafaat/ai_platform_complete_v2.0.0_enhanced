"""Field runtime cohesion API adapter.

This adapter exposes the unification layer without creating a second field brain:
callers must pass the result produced by core.field_intelligence_coordinator.
"""

from __future__ import annotations

from typing import Any

from shared.field_runtime_cohesion import run_cohesive_field_runtime


def build_field_runtime_payload(
    field_intelligence_result: Any,
    *,
    economics: dict | None = None,
    equipment: dict | None = None,
    irrigation: dict | None = None,
) -> dict:
    """Return the canonical-state → twin → recommendation lifecycle payload."""
    return run_cohesive_field_runtime(
        field_intelligence_result=field_intelligence_result,
        economics=economics,
        equipment=equipment,
        irrigation=irrigation,
    )
