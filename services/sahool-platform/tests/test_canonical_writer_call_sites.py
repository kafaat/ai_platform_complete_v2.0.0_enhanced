"""A writer function with no production caller is dead code inside a live module.

The module-level reachability guard (``scripts/ci/platform_module_reachability_guard.py``)
answers "can the runtime reach this FILE?". It cannot answer "does anything call this
FUNCTION?" — and for ``api/persisted_canonical_repositories.py`` the two questions have
different answers: the module is genuinely reachable, because
``api/routers/recommendations.py`` calls ``load_agronomic_context`` on it. Every writer
added beside that reader therefore inherits a reachable module and passes the module
guard while nothing in production calls it.

That is the same defect class one level down, and it is easier to miss, not harder:
adding a function to an already-wired file leaves no trace in any inventory.

This guard measures call sites for the canonical writers and pins the ones that have
none. The pinned set is SHRINK-ONLY: an entry leaves the day a route, worker or
subscriber calls it. A NEW unwired writer fails here rather than shipping as a claim.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PLATFORM = Path(__file__).resolve().parents[1]
REPO = PLATFORM.parents[1]
REPOSITORIES = PLATFORM / "api" / "persisted_canonical_repositories.py"

# Writers with no call site OUTSIDE their own module. The ratchet has fired once
# already: the three ``persist_*_projection`` functions left this set when
# ``scripts/workers/canonical_execution_learning_worker.py`` — a service registered in
# docker-compose.v9.yml — began calling them off ``agronomy.projection.requested``.
#
# The three that remain are a WEAKER claim than "dead", and the difference is recorded
# here rather than blurred: each is called by a ``persist_*_projection`` sibling in the
# same file, so each is now reached transitively from that worker. They stay listed
# because this guard deliberately does not count a module calling itself as evidence of
# wiring — that rule is what made the original six visible at all, and relaxing it now
# to claim a nicer number would retire the measurement, not satisfy it.
#
# SHRINK-ONLY — an entry leaves in the change that gives it an external caller; never
# add one without recording why a writer is landing ahead of its call site.
WRITERS_AWAITING_AN_EXTERNAL_CALL_SITE = frozenset(
    {
        "persist_nutrient_ledger",
        "persist_phenology_state",
        "persist_salinity_state",
    }
)
WRITERS_AWAITING_A_CALL_SITE = WRITERS_AWAITING_AN_EXTERNAL_CALL_SITE


def _production_files() -> list[Path]:
    """Platform modules PLUS the executable roots that live outside the package.

    Scanning only ``services/sahool-platform`` was a real blind spot, not a
    simplification: the registered worker lives at ``scripts/workers/``, so when it
    started calling three of these writers the guard went on reporting all six as
    uncalled — passing green while asserting something false. A guard that cannot see
    the caller is worse than no guard, because its silence reads as evidence.
    """
    out = []
    for path in sorted(PLATFORM.rglob("*.py")):
        rel = path.relative_to(PLATFORM).as_posix()
        if rel.startswith(("tests/", "examples/")) or "/tests/" in rel or "__pycache__" in rel:
            continue
        if path == REPOSITORIES:
            continue  # a writer calling its own sibling is not an external call site
        out.append(path)
    for extra in ("scripts/workers", "scripts/ops"):
        directory = REPO / extra
        if directory.exists():
            out.extend(p for p in sorted(directory.rglob("*.py")) if "__pycache__" not in str(p))
    return out


def _declared_writers() -> set[str]:
    tree = ast.parse(REPOSITORIES.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("persist_")
    }


def _called_names() -> set[str]:
    """Every function name called anywhere in production platform code."""
    called: set[str] = set()
    for path in _production_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:  # pragma: no cover - a broken file fails its own gate
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    return called


def test_the_declared_writers_are_exactly_the_ones_measured_as_uncalled():
    """The pinned set must match measurement — neither stale nor optimistic."""
    writers = _declared_writers()
    assert writers, "no persist_* writers found; the guard would pass vacuously"
    uncalled = {name for name in writers if name not in _called_names()}
    assert uncalled == set(WRITERS_AWAITING_A_CALL_SITE), (
        "canonical writer call sites drifted.\n"
        f"  measured uncalled: {sorted(uncalled)}\n"
        f"  pinned uncalled:   {sorted(WRITERS_AWAITING_A_CALL_SITE)}\n"
        "A writer that gained a caller must leave the pinned set; a NEW writer without "
        "one must not be added silently — 'the function exists' is not 'the path runs'."
    )


def test_the_reader_the_route_actually_uses_is_not_in_the_deferred_set():
    """Proof the measurement can distinguish wired from unwired in this same file."""
    assert "load_agronomic_context" in _called_names(), (
        "the route's reader must measure as called, or the guard above proves nothing"
    )
    assert "load_agronomic_context" not in WRITERS_AWAITING_A_CALL_SITE
