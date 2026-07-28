"""Compatibility re-export for the canonical platform route policy.

New code must import ``scripts.ci.platform_route_classification`` directly.
"""

from scripts.ci.platform_route_classification import (  # noqa: F401
    HTTP_METHODS,
    INFRASTRUCTURE_ROUTES,
    RouteDeclaration,
    assert_infrastructure_allowlist_is_used,
    collect_platform_routes,
    extract_routes,
    is_infrastructure_route,
    normalize_route_method,
    normalize_route_path,
    normalized_route_key,
    partition_routes,
)

# Backward-compatible names retained for existing architecture guards.
DiscoveredRoute = RouteDeclaration
normalize_method = normalize_route_method
normalize_path = normalize_route_path
normalized_route = normalized_route_key
discover_routes = collect_platform_routes
