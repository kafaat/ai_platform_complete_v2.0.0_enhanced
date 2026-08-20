"""Precision agriculture intelligence helpers for SAHOOL Phase 6."""

from .phase6_intelligence import (
    compose_digital_twin_snapshot,
    compute_profitability_map,
    compute_yield_stability,
    extract_boundary,
    generate_management_zones,
    generate_prescription_map,
)

__all__ = [
    "extract_boundary",
    "generate_management_zones",
    "generate_prescription_map",
    "compute_yield_stability",
    "compute_profitability_map",
    "compose_digital_twin_snapshot",
]

# Interchange/spatial-trial edge contracts (no new authority layer).
from .adapt_v2_edge import (
    AdaptExportBundle,
    export_field_boundary_bundle,
    geojson_polygon_to_wkt,
    import_field_boundary_bundle,
    wkt_to_geojson_polygon,
)
from .pail_om_edge import (
    PailObservationProjection,
    import_observation_projection,
    project_observation,
)
from .trial_spatial import (
    assign_rcbd_geometries,
    bind_plot_outcomes,
    design_spatial_rcbd,
    generate_rcbd_plot_geometries,
)

__all__ += [
    "AdaptExportBundle",
    "export_field_boundary_bundle",
    "geojson_polygon_to_wkt",
    "wkt_to_geojson_polygon",
    "import_field_boundary_bundle",
    "PailObservationProjection",
    "project_observation",
    "import_observation_projection",
    "assign_rcbd_geometries",
    "generate_rcbd_plot_geometries",
    "design_spatial_rcbd",
    "bind_plot_outcomes",
]
