"""Infrastructure routes must be declared at their canonical site, not merely exist.

`scripts/ci/p1_main_decomposition_guard.py` rejects ANY route decorator in
`services/sahool-platform/api/main.py`, so platform infrastructure routes belong in
`api/routers/platform_health.py` beside `/healthz`, `/readyz` and `/metrics`.

Four consecutive imported patches re-added `GET /runtime-identity` to `api/main.py`.
Each time P1 failed with a generic "platform main.py regained direct routes" message
that says nothing about where the route *should* go — so the same fix was rediscovered
by hand every round. This test states the rule in the repository itself and fails with
the destination spelled out.

Being excluded from the domain route budget (`INFRASTRUCTURE_ROUTES`) says what a route
*is*; `CANONICAL_DECLARATION_SITES` says where it *belongs*. The two are independent and
both are enforced.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM_MAIN = ROOT / "services/sahool-platform/api/main.py"


def _classification():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    name = "platform_route_classification_placement"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts/ci/platform_route_classification.py"
    )
    module = importlib.util.module_from_spec(spec)
    # @dataclass resolves sys.modules[cls.__module__] during class creation, so the
    # module must be registered before exec_module or it raises AttributeError.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_every_infrastructure_route_has_a_canonical_site():
    """The contract must cover the whole allowlist — no silently unplaced route."""
    m = _classification()
    missing = sorted(set(m.INFRASTRUCTURE_ROUTES) - set(m.CANONICAL_DECLARATION_SITES))
    assert missing == [], (
        f"infrastructure routes without a canonical declaration site: {missing}. "
        "Add them to CANONICAL_DECLARATION_SITES in scripts/ci/platform_route_classification.py."
    )


def test_infrastructure_routes_are_declared_at_their_canonical_site():
    m = _classification()
    platform_root = ROOT / "services/sahool-platform"
    declared = {(r.method, r.path): r for r in m.collect_platform_routes(platform_root)}
    violations: list[str] = []
    for key, expected in sorted(m.CANONICAL_DECLARATION_SITES.items()):
        route = declared.get(key)
        if route is None:
            continue  # presence is the allowlist guard's job, not this one's
        actual = route.source.split("services/sahool-platform/", 1)[-1]
        if actual != expected:
            violations.append(
                f"{key[0]} {key[1]} is declared in {actual}:{route.line} "
                f"but must be declared in {expected}"
            )
    assert violations == [], (
        "platform infrastructure route declared outside its canonical site:\n  "
        + "\n  ".join(violations)
        + "\n\nMove the handler to the health router. api/main.py is route-free by "
        "contract (p1_main_decomposition_guard rejects any route decorator there); "
        "classifying a route as infrastructure excludes it from the domain budget but "
        "does not permit declaring it in main.py."
    )


def test_platform_main_declares_no_runtime_identity_route():
    """Explicit regression guard for the route that keeps coming back to main.py."""
    assert "/runtime-identity" not in PLATFORM_MAIN.read_text(encoding="utf-8"), (
        "GET /runtime-identity must live in api/routers/platform_health.py, not api/main.py."
    )
