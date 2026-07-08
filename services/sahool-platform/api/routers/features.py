"""features.py — runtime feature registry for UI/navigation alignment.

Exposes backend FEATURE_* flag state so the Web shell can hide/disable advanced pages
whose backend routes are intentionally guarded. This prevents active navigation items
from pointing at 404 feature-flag guards while keeping direct URLs honest with a
feature-disabled state.
"""

from __future__ import annotations

import os

from fastapi import APIRouter

from api.feature_registry import FEATURE_FLAGS, TRUTHY, is_enabled

router = APIRouter(tags=["features"])

# Backend flag → frontend page + Vite flag. Keep this map in lock-step with
# frontend/src/lib/featureFlags.ts. Missing values are returned as null rather than
# hiding the backend flag from the registry.
_FEATURE_UI_MAP: dict[str, dict[str, str]] = {
    "FEATURE_NATURAL_LANGUAGE_GIS": {"page": "nl-gis", "frontend_flag": "VITE_ENABLE_NL_GIS"},
    "FEATURE_DECISION_STUDIO": {
        "page": "decision-studio",
        "frontend_flag": "VITE_ENABLE_DECISION_STUDIO",
    },
    "FEATURE_DECISION_CONFIDENCE": {
        "page": "decision-confidence",
        "frontend_flag": "VITE_ENABLE_DECISION_CONFIDENCE",
    },
    "FEATURE_EXECUTION_FEEDBACK": {
        "page": "execution-feedback",
        "frontend_flag": "VITE_ENABLE_EXECUTION_FEEDBACK",
    },
    "FEATURE_UNIFIED_LINEAGE": {"page": "lineage", "frontend_flag": "VITE_ENABLE_UNIFIED_LINEAGE"},
    "FEATURE_LEARNING_DASHBOARD": {
        "page": "learning-dashboard",
        "frontend_flag": "VITE_ENABLE_LEARNING_DASHBOARD",
    },
    "FEATURE_EVIDENCE_MAP": {"page": "evidence-map", "frontend_flag": "VITE_ENABLE_EVIDENCE_MAP"},
    "FEATURE_REPLAY_MAP": {"page": "replay-map", "frontend_flag": "VITE_ENABLE_REPLAY_MAP"},
    "FEATURE_OPERATIONS_WALL": {
        "page": "operations-wall",
        "frontend_flag": "VITE_ENABLE_OPERATIONS_WALL",
    },
    "FEATURE_IRRIGATION_NETWORK": {
        "page": "irrigation-network",
        "frontend_flag": "VITE_ENABLE_IRRIGATION_NETWORK",
    },
    "FEATURE_PORTFOLIO_COMMAND": {
        "page": "portfolio-command",
        "frontend_flag": "VITE_ENABLE_PORTFOLIO_COMMAND",
    },
    "FEATURE_DEVICE_TWIN": {"page": "device-twin", "frontend_flag": "VITE_ENABLE_DEVICE_TWIN"},
}


@router.get("/api/v1/features")
async def get_features() -> dict[str, object]:
    """Return backend feature-flag state for frontend navigation alignment.

    The endpoint is intentionally cheap and DB-free. It reports every documented
    backend flag, whether currently enabled by env, and the matching frontend page
    when one exists. Unknown/non-page backend flags remain visible to operators.
    """
    features: list[dict[str, object]] = []
    for name, description in sorted(FEATURE_FLAGS.items()):
        ui = _FEATURE_UI_MAP.get(name, {})
        features.append(
            {
                "backend_flag": name,
                "enabled": is_enabled(name, os.getenv(name)),
                "description": description,
                "page": ui.get("page"),
                "frontend_flag": ui.get("frontend_flag"),
                "source": "env",
            }
        )
    return {
        "features": features,
        "truthy": sorted(TRUTHY),
        "default": "disabled-until-backend-env-truthy",
    }
