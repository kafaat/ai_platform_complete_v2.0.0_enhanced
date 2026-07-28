#!/usr/bin/env python3
"""WS-E — CI consumer-contract gate.

WS-A..D each landed a *canonical producer* and rewired *consumers* to honor it. The producer
sides are already guarded (raster_validated_product_guard, indicators_registry_gate,
weather_engine_formula_guard). The **consumer side of the canonical-weather-state Views and their
lineage had no unifying structural guard** — this gate closes that, so a future edit cannot
silently reintroduce a parallel computation or drop lineage on a consumer path.

Technique (mirrors decision_candidate_boundary_gate): parse each target file, strip docstrings and
comments via AST so a *mention* of a forbidden token in prose never false-trips, isolate the
consumer function, then assert REQUIRED contract tokens are present and FORBIDDEN direct-kernel
tokens are absent on the executable path. Value-strings are kept (so "et0_view"/"derived_from"
literals are still seen).

Contracts enforced (all currently landed by WS-A..D; this locks them):
  WS-C.1  Canonical-weather-state Views carry lineage (et0_view/vpd_view/current_view/
          weather_state_report/gdd_view expose derived_from|reads_from + canonical_state_id/version
          + source_snapshot_id).
  WS-C.2  weather_runtime consumer handlers delegate to the Views and do NOT call the raw kernels
          (et0_agro_product/compute_vpd/gdd_agro_product) directly — the engine is reached only
          through build_canonical_weather_state/build_canonical_daily_series.
  WS-C.3  current_weather returns the "current" View, not the provider payload — the base
          observation is a state slot like every derived product (WX-10.4).
  WS-A    the vegetation consumer reads the ValidatedIndicatorProduct envelope
          (indicator_product + quality_score + provenance), not bare stats.mean alone. The
          three-container boundary (20260712) routes this through a single validated
          observation-bundle: run_analysis consumes _real_observation_bundle_from_raster and
          still unwraps the ValidatedIndicatorProduct envelope per index.
  WS-D    the irrigation consumer routes depletion through the canonical water-stress guard
          (missing != zero), never treating a missing depletion as 0.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

WEATHER = ROOT / "services/weather-service"
CWS = WEATHER / "canonical_weather_state.py"
CDS = WEATHER / "canonical_daily_weather_series.py"
WRUNTIME = WEATHER / "weather_runtime.py"
VEG = ROOT / "services/vegetation-analysis-service/vegetation_runtime.py"
IRRIG = ROOT / "services/sahool-platform/api/routers/irrigation_recommendation.py"

LINEAGE_KEYS = (
    "derived_from",
    "canonical_state_id",
    "canonical_state_version",
    "source_snapshot_id",
)


def _strip_docstrings(node: ast.AST) -> None:
    """Blank every docstring in the tree so prose mentions of forbidden tokens are not scanned."""
    for sub in ast.walk(node):
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = getattr(sub, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body[0].value.value = ""


def _func_source(text: str, name: str) -> str | None:
    """Return the executable source of a top-level or nested function, docstrings stripped."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            _strip_docstrings(node)
            return ast.unparse(node)
    return None


def _check_func(
    violations: list[str],
    path: Path,
    text: str,
    name: str,
    required: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
) -> None:
    src = _func_source(text, name)
    rel = path.relative_to(ROOT)
    if src is None:
        violations.append(
            f"{rel}: consumer function {name}() not found (contract cannot be verified)"
        )
        return
    for token in required:
        if token not in src:
            violations.append(f"{rel}::{name}: missing required contract token {token!r}")
    for token in forbidden:
        if token in src:
            violations.append(
                f"{rel}::{name}: forbidden direct-kernel token {token!r} on the consumer path "
                "(reach the engine only via build_canonical_weather_state/build_canonical_daily_series)"
            )


def collect_violations() -> list[str]:
    violations: list[str] = []
    for path in (CWS, CDS, WRUNTIME, VEG, IRRIG):
        if not path.exists():
            violations.append(f"{path.relative_to(ROOT)}: missing (consumer-contract target)")
    if violations:
        return violations

    cws = CWS.read_text(encoding="utf-8")
    cds = CDS.read_text(encoding="utf-8")
    wrt = WRUNTIME.read_text(encoding="utf-8")
    veg = VEG.read_text(encoding="utf-8")
    irrig = IRRIG.read_text(encoding="utf-8")

    # WS-C.1 — Views carry lineage.
    _check_func(violations, CWS, cws, "et0_view", required=LINEAGE_KEYS)
    _check_func(violations, CWS, cws, "vpd_view", required=LINEAGE_KEYS)
    _check_func(violations, CWS, cws, "current_view", required=LINEAGE_KEYS)
    _check_func(violations, CWS, cws, "weather_state_report", required=("reads_from", "state_id"))
    _check_func(
        violations,
        CDS,
        cds,
        "gdd_view",
        required=("derived_from", "gdd_lineage_id", "contributing_state_ids"),
    )

    # WS-C.2 — consumer handlers delegate to Views, never the raw kernels directly.
    _check_func(
        violations,
        WRUNTIME,
        wrt,
        "agro_et0",
        required=("build_canonical_weather_state", "et0_view"),
        forbidden=("et0_agro_product(",),
    )
    _check_func(
        violations,
        WRUNTIME,
        wrt,
        "agro_vpd",
        required=("build_canonical_weather_state", "vpd_view"),
        forbidden=("compute_vpd(",),
    )
    _check_func(
        violations,
        WRUNTIME,
        wrt,
        "agro_gdd",
        required=("build_canonical_daily_series", "gdd_view"),
        forbidden=("gdd_agro_product(",),
    )
    _check_func(
        violations,
        WRUNTIME,
        wrt,
        "agro_weather_state_report",
        required=("weather_state_report",),
    )
    # WS-C.3 (WX-10.4) — "current" is a state slot, not a provider passthrough. The edge handler
    # may still fetch (I/O belongs at the edge) but must return the View, never the raw payload.
    _check_func(
        violations,
        WRUNTIME,
        wrt,
        "current_weather",
        required=("build_canonical_weather_state", "current_view"),
    )

    # WS-A — vegetation consumer reads the ValidatedIndicatorProduct envelope, not bare stats.mean.
    # Three-container boundary: the consumer path is run_analysis over a single validated
    # observation-bundle (_real_observation_bundle_from_raster), still unwrapping the envelope.
    _check_func(
        violations,
        VEG,
        veg,
        "run_analysis",
        required=(
            "_real_observation_bundle_from_raster",
            "indicator_product",
            "quality_score",
            "provenance",
        ),
    )

    # WS-D — irrigation consumer routes depletion through the canonical water-stress guard.
    for token in ("irrigation_state_guard", "canonical_water_stress", "depletion_mm"):
        if token not in irrig:
            violations.append(
                f"{IRRIG.relative_to(ROOT)}: missing WS-D consumer token {token!r} "
                "(depletion must route through the canonical water-stress guard; missing != zero)"
            )

    return violations


def main() -> int:
    violations = collect_violations()
    if violations:
        print("consumer_contract_gate_failed")
        print("\n".join(violations))
        return 1
    print("consumer_contract_gate_ok (WS-C views+delegation · WS-A envelope · WS-D depletion)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
