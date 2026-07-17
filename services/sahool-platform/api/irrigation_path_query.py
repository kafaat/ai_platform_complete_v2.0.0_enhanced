"""IRR-F01 hydraulic path resolution over the EXISTING v171 graph.

Replaces the deferred closure/version tables with a live query over the persisted
`irrigation_hydraulic_nodes` / `irrigation_hydraulic_segments` topology. This module
is pure (no DB/HTTP/IO): the runtime fetches the tenant+project-scoped segments and
calls :func:`resolve_source_paths`; the canonical in-DB recursive CTE is provided as
:data:`PERSISTED_UPSTREAM_PATH_CTE` for callers that prefer to recurse in Postgres.

Contract (per IRR-F01 review):
  * tenant + project scoping is mandatory (enforced by the caller's WHERE / the CTE);
  * a hard depth cap and an explicit cycle guard — an invalid (cyclic) graph fails
    closed as ``invalid_cycle`` rather than silently yielding a path;
  * multiple source→terminal paths are reported as ``multiple`` with ``path_count``
    and every alternative — never a silently-picked "first path";
  * ``bottleneck_node_id`` is ALWAYS ``None`` here: a bottleneck is a v175 capability
    concern, not something topology alone may declare. Capacity/derating lives in the
    reservation/evaluation path.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

# Hard cap on path length; also bounds the cycle search. A real hydraulic path
# (source→pump→…→terminal) is far shorter than this.
MAX_PATH_DEPTH = 32

# Nodes that terminate an upstream walk (the water origin).
SOURCE_NODE_TYPES = frozenset({"source", "reservoir"})


class PathStatus(StrEnum):
    UNIQUE = "unique"
    MULTIPLE = "multiple"
    UNREACHABLE = "unreachable"
    INVALID_CYCLE = "invalid_cycle"


@dataclass(frozen=True, slots=True)
class HydraulicEdge:
    """A directed segment: water flows from ``from_node_id`` to ``to_node_id``."""

    from_node_id: str
    to_node_id: str


@dataclass(frozen=True, slots=True)
class PathResolution:
    status: PathStatus
    path_count: int
    # The single source→terminal path when unique; None when multiple/unreachable/cyclic.
    path: tuple[str, ...] | None
    # Every enumerated source→terminal path (ordered) — the ambiguity set when multiple.
    alternatives: tuple[tuple[str, ...], ...]
    # Always None: topology must not declare a hydraulic bottleneck (that is v175's job).
    bottleneck_node_id: None
    # True when the depth cap truncated the search (an incomplete, not-to-be-trusted walk).
    depth_capped: bool


def resolve_source_paths(
    edges: Iterable[HydraulicEdge],
    terminal_node_id: str,
    source_node_ids: Iterable[str],
    *,
    max_depth: int = MAX_PATH_DEPTH,
) -> PathResolution:
    """Resolve source→terminal hydraulic paths by walking segments upstream.

    Deterministic and fail-closed: a cycle on the current walk returns
    ``INVALID_CYCLE`` immediately; hitting ``max_depth`` marks ``depth_capped``.
    """

    reverse: dict[str, list[str]] = {}
    for edge in edges:
        reverse.setdefault(edge.to_node_id, []).append(edge.from_node_id)
    for node in reverse:
        reverse[node] = sorted(reverse[node])  # deterministic enumeration

    sources = frozenset(source_node_ids)
    complete_paths: list[tuple[str, ...]] = []
    state = {"cycle": False, "depth_capped": False}

    def walk(node: str, path: list[str], on_path: frozenset[str]) -> None:
        if state["cycle"]:
            return
        if node in sources:
            complete_paths.append(tuple(reversed(path)))  # source → terminal order
            return
        if len(path) >= max_depth:
            state["depth_capped"] = True
            return
        for parent in reverse.get(node, []):
            if parent in on_path:
                state["cycle"] = True
                return
            walk(parent, [*path, parent], on_path | {parent})

    walk(terminal_node_id, [terminal_node_id], frozenset({terminal_node_id}))

    if state["cycle"]:
        return PathResolution(PathStatus.INVALID_CYCLE, 0, None, (), None, state["depth_capped"])

    count = len(complete_paths)
    if count == 0:
        return PathResolution(PathStatus.UNREACHABLE, 0, None, (), None, state["depth_capped"])
    if count == 1:
        return PathResolution(
            PathStatus.UNIQUE,
            1,
            complete_paths[0],
            tuple(complete_paths),
            None,
            state["depth_capped"],
        )
    ordered = tuple(sorted(complete_paths))
    return PathResolution(PathStatus.MULTIPLE, count, None, ordered, None, state["depth_capped"])


# Canonical in-DB alternative: a tenant+project-scoped recursive walk with an
# explicit cycle flag (via the accumulated path array) and depth cap. Parameters:
#   $1 tenant_id, $2 project_id, $3 terminal_node_id, $4 max_depth.
# The application still classifies the returned rows through PathResolution so the
# fail-closed cycle/ambiguity semantics stay in one tested place.
PERSISTED_UPSTREAM_PATH_CTE = """
WITH RECURSIVE upstream AS (
    SELECT
        s.from_node_id AS node_id,
        ARRAY[$3::uuid, s.from_node_id] AS path,
        1 AS depth,
        (s.from_node_id = $3) AS cycle
    FROM irrigation_hydraulic_segments s
    WHERE s.tenant_id = $1 AND s.project_id = $2 AND s.to_node_id = $3
    UNION ALL
    SELECT
        s.from_node_id,
        u.path || s.from_node_id,
        u.depth + 1,
        s.from_node_id = ANY(u.path)
    FROM upstream u
    JOIN irrigation_hydraulic_segments s
        ON s.tenant_id = $1 AND s.project_id = $2 AND s.to_node_id = u.node_id
    WHERE NOT u.cycle AND u.depth < $4
)
SELECT u.node_id, u.path, u.depth, u.cycle, n.node_type
FROM upstream u
JOIN irrigation_hydraulic_nodes n ON n.id = u.node_id AND n.tenant_id = $1
ORDER BY u.depth, u.node_id
"""
