"""Production-oriented feature store primitives for SAHOOL Phase 10.

The implementation is intentionally dependency-light so it can run in CI, but
all outputs are shaped as manifests that can be backed by Postgres/Redis/MinIO
or replaced by Feast-compatible adapters later.
"""

from .runtime import (
    build_feature_lineage_manifest,
    build_point_in_time_snapshot,
    materialize_online_feature_values,
    register_feature_definitions,
    write_offline_feature_dataset,
)

__all__ = [
    "build_feature_lineage_manifest",
    "build_point_in_time_snapshot",
    "materialize_online_feature_values",
    "register_feature_definitions",
    "write_offline_feature_dataset",
]
