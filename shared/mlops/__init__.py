"""Production-oriented MLOps primitives for SAHOOL Phase 10."""

from .runtime import (
    apply_model_promotion,
    build_model_card,
    register_model_version,
    resolve_serving_alias,
    rollback_serving_alias,
)

__all__ = [
    "apply_model_promotion",
    "build_model_card",
    "register_model_version",
    "resolve_serving_alias",
    "rollback_serving_alias",
]
