"""IRR-F01 — hydraulic path resolution over v171 (pure logic)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "services" / "sahool-platform" / "api" / "irrigation_path_query.py"
spec = importlib.util.spec_from_file_location("irrigation_path_query", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

HydraulicEdge = module.HydraulicEdge
PathStatus = module.PathStatus
resolve_source_paths = module.resolve_source_paths
MAX_PATH_DEPTH = module.MAX_PATH_DEPTH


def edges(*pairs: tuple[str, str]):
    return [HydraulicEdge(a, b) for a, b in pairs]


def test_unique_path_reports_full_source_to_terminal_order() -> None:
    # well -> pump -> mainline -> valve -> pivot
    result = resolve_source_paths(
        edges(("well", "pump"), ("pump", "mainline"), ("mainline", "valve"), ("valve", "pivot")),
        terminal_node_id="pivot",
        source_node_ids=["well"],
    )
    assert result.status is PathStatus.UNIQUE
    assert result.path_count == 1
    assert result.path == ("well", "pump", "mainline", "valve", "pivot")
    assert result.bottleneck_node_id is None


def test_multiple_paths_are_reported_not_silently_first_picked() -> None:
    # well feeds pivot via two mainlines.
    result = resolve_source_paths(
        edges(
            ("well", "main_a"),
            ("well", "main_b"),
            ("main_a", "pivot"),
            ("main_b", "pivot"),
        ),
        terminal_node_id="pivot",
        source_node_ids=["well"],
    )
    assert result.status is PathStatus.MULTIPLE
    assert result.path_count == 2
    assert result.path is None  # never a silently-picked first path
    assert len(result.alternatives) == 2
    assert result.bottleneck_node_id is None


def test_unreachable_when_no_source_connected() -> None:
    result = resolve_source_paths(
        edges(("junction", "valve"), ("valve", "pivot")),
        terminal_node_id="pivot",
        source_node_ids=["well"],  # well is not in the graph
    )
    assert result.status is PathStatus.UNREACHABLE
    assert result.path_count == 0
    assert result.path is None


def test_cycle_fails_closed_as_invalid_cycle() -> None:
    result = resolve_source_paths(
        edges(("a", "b"), ("b", "c"), ("c", "a"), ("c", "pivot")),
        terminal_node_id="pivot",
        source_node_ids=["well"],
    )
    assert result.status is PathStatus.INVALID_CYCLE
    assert result.path is None
    assert result.path_count == 0


def test_depth_cap_is_enforced_and_surfaced() -> None:
    # A long chain longer than the cap, terminating before a source is reached.
    chain = edges(*[(f"n{i}", f"n{i + 1}") for i in range(MAX_PATH_DEPTH + 5)])
    result = resolve_source_paths(
        chain,
        terminal_node_id=f"n{MAX_PATH_DEPTH + 5}",
        source_node_ids=["well"],
        max_depth=MAX_PATH_DEPTH,
    )
    assert result.depth_capped is True
    assert result.status is PathStatus.UNREACHABLE  # capped walk never reached a source


def test_bottleneck_is_never_declared_from_topology() -> None:
    result = resolve_source_paths(
        edges(("well", "pivot")),
        terminal_node_id="pivot",
        source_node_ids=["well"],
    )
    assert result.status is PathStatus.UNIQUE
    assert result.bottleneck_node_id is None


def test_recursive_cte_is_tenant_and_project_scoped_and_depth_bounded() -> None:
    sql = module.PERSISTED_UPSTREAM_PATH_CTE
    assert "WITH RECURSIVE" in sql
    assert "s.tenant_id = $1 AND s.project_id = $2" in sql
    assert "u.depth < $4" in sql  # depth cap
    assert "= ANY(u.path)" in sql  # cycle guard
    assert "irrigation_hydraulic_segments" in sql and "irrigation_hydraulic_nodes" in sql
