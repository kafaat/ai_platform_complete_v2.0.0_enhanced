"""Production-oriented MLOps primitives for SAHOOL Phase 10."""

from .agronomic_candidate import assess_agronomic_model_candidate
from .runtime import (
    DatasetVersion,
    agricultural_evaluation_profile,
    apply_model_promotion,
    build_model_card,
    register_dataset_version,
    register_model_version,
    resolve_serving_alias,
    rollback_serving_alias,
)

__all__ = [
    "DatasetVersion",
    "assess_agronomic_model_candidate",
    "agricultural_evaluation_profile",
    "apply_model_promotion",
    "build_model_card",
    "register_dataset_version",
    "register_model_version",
    "resolve_serving_alias",
    "rollback_serving_alias",
]
