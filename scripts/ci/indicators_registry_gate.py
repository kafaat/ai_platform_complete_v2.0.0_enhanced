#!/usr/bin/env python3
"""Guard: config/indicators_registry.json is the single source of truth for indicators.

Dependency-free static cross-check (no service imports, no JS parser). It fails CI
if the scattered indicator catalogs drift from the canonical registry, and it enforces
the honesty contract (an estimated index must never claim to be raster-real).

Checks:
  (a) every computation.formula_ref of the form raster_quality.INDICATOR_FORMULAS.<k>
      resolves to a real key in services/raster-service/raster_quality.py.
  (b) every registry entry with source="real" + kind="raster_formula" is a raster
      formula key OR is bridged via raster_alias / _RASTER_REAL_INDEX.
  (c) every id in analytics_shapers.py _INDICATOR_CATALOG is present in the registry.
  (d) every id in HybridIndexPage.tsx INDICATOR_CATALOG is present in the registry.
  (e) every renderable=true registry id appears in layerRegistry.ts as a kind='index'.
  (f) HONESTY: an id that vegetation-analysis computes only as a synthetic estimate
      (no raster formula key) must NOT be labelled source="real"/status="implemented".
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config/indicators_registry.json"
RASTER_QUALITY = ROOT / "services/raster-service/raster_quality.py"
VEGETATION = ROOT / "services/vegetation-analysis-service/vegetation_runtime.py"
ANALYTICS = ROOT / "services/sahool-platform/api/analytics_shapers.py"
HYBRID = ROOT / "frontend/src/sections/HybridIndexPage.tsx"
LAYER_REGISTRY = ROOT / "frontend/src/lib/layerRegistry.ts"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _slice(text: str, start_marker: str, end_marker: str) -> str:
    """Return the substring between the first start_marker and the next end_marker."""
    i = text.index(start_marker)
    j = text.index(end_marker, i + len(start_marker))
    return text[i:j]


def _raster_formula_keys() -> set[str]:
    """Keys of INDICATOR_FORMULAS in raster_quality.py."""
    block = _slice(_read(RASTER_QUALITY), "INDICATOR_FORMULAS", "\n}")
    return set(re.findall(r'"([a-z0-9_]+)":', block))


def _raster_real_index() -> dict[str, str]:
    """_RASTER_REAL_INDEX mapping {veg_id: raster_id} from vegetation_runtime.py."""
    veg = _read(VEGETATION)
    block = _slice(veg, "_RASTER_REAL_INDEX", "}")
    pairs = re.findall(r'"([a-z0-9_]+)"\s*:\s*"([a-z0-9_]+)"', block)
    return dict(pairs)


def _vegetation_index_ids() -> set[str]:
    """Indicator ids the vegetation service returns as computed indices ("k": round(...))."""
    return set(re.findall(r'"([a-z0-9_]+)":\s*round\(', _read(VEGETATION)))


def _backend_catalog_ids() -> set[str]:
    block = _slice(_read(ANALYTICS), "_INDICATOR_CATALOG", "def _shape_indicator_catalog")
    return set(re.findall(r'"id":\s*"([a-z0-9_]+)"', block))


def _frontend_catalog_ids() -> set[str]:
    block = _slice(_read(HYBRID), "const INDICATOR_CATALOG", "] as const;")
    return set(re.findall(r"id:\s*'([a-z0-9_]+)'", block))


def _layer_index_ids() -> set[str]:
    """ids of LAYER_REGISTRY entries whose kind is 'index'."""
    text = _read(LAYER_REGISTRY)
    ids: set[str] = set()
    for m in re.finditer(r"id:\s*'([\w-]+)',[\s\S]{0,240}?kind:\s*'(\w+)'", text):
        if m.group(2) == "index":
            ids.add(m.group(1))
    return ids


def main() -> int:
    reg = json.loads(_read(REGISTRY))
    indicators = reg["indicators"]
    by_id = {e["id"]: e for e in indicators}

    formula_keys = _raster_formula_keys()
    real_index = _raster_real_index()
    real_index_targets = set(real_index.values())
    veg_ids = _vegetation_index_ids()
    backend_ids = _backend_catalog_ids()
    frontend_ids = _frontend_catalog_ids()
    # Universe of real indicator ids across the scattered catalogs (guards against the
    # veg regex catching unrelated round(...) fields like metrics).
    known_ids = set(by_id) | backend_ids | frontend_ids
    # Honesty set: vegetation-estimated ids that have NO real raster formula key and
    # are NOT bridged to a real raster index — these are estimate-only (lai/cwsi/recl).
    veg_estimate_only = {
        v for v in veg_ids if v not in formula_keys and v not in real_index and v in known_ids
    }

    errors: list[str] = []

    if not formula_keys:
        errors.append("could not parse INDICATOR_FORMULAS keys from raster_quality.py")

    # (a) formula_ref must resolve to a real raster formula key.
    for e in indicators:
        ref = (e.get("computation") or {}).get("formula_ref")
        if not ref:
            continue
        m = re.fullmatch(r"raster_quality\.INDICATOR_FORMULAS\.([a-z0-9_]+)", ref)
        if not m:
            errors.append(f"(a) {e['id']}: unrecognised formula_ref '{ref}'")
        elif m.group(1) not in formula_keys:
            errors.append(
                f"(a) {e['id']}: formula_ref key '{m.group(1)}' not in raster_quality.INDICATOR_FORMULAS"
            )

    # (b) real spectral entries must be a formula key or bridged via alias/_RASTER_REAL_INDEX.
    for e in indicators:
        if e.get("source") != "real":
            continue
        if (e.get("computation") or {}).get("kind") != "raster_formula":
            continue
        iid = e["id"]
        comp = e.get("computation") or {}
        alias = comp.get("raster_alias")
        ref = comp.get("formula_ref") or ""
        ref_m = re.fullmatch(r"raster_quality\.INDICATOR_FORMULAS\.([a-z0-9_]+)", ref)
        ref_key = ref_m.group(1) if ref_m else None
        ok = (
            iid in formula_keys
            or alias in formula_keys
            or iid in real_index_targets
            or (ref_key is not None and ref_key in formula_keys)
        )
        if not ok:
            errors.append(
                f"(b) {iid}: source=real spectral but not a raster formula key nor bridged "
                f"(alias={alias}, formula_ref={ref or None})"
            )

    # (c) backend catalog ids all present.
    for iid in sorted(backend_ids):
        if iid not in by_id:
            errors.append(f"(c) backend _INDICATOR_CATALOG id '{iid}' missing from registry")

    # (d) frontend HybridIndexPage catalog ids all present.
    for iid in sorted(frontend_ids):
        if iid not in by_id:
            errors.append(f"(d) frontend INDICATOR_CATALOG id '{iid}' missing from registry")

    # (e) renderable ids must exist as kind='index' in layerRegistry.ts.
    layer_ids = _layer_index_ids()
    if not layer_ids:
        errors.append("(e) could not parse kind='index' ids from layerRegistry.ts")
    for e in indicators:
        if e.get("renderable") and e["id"] not in layer_ids:
            errors.append(
                f"(e) renderable id '{e['id']}' has no kind='index' entry in layerRegistry.ts"
            )

    # (f) honesty: estimate-only vegetation ids must not claim real/implemented.
    for iid in sorted(veg_estimate_only):
        e = by_id.get(iid)
        if e is None:
            continue
        if e.get("source") == "real" or e.get("status") == "implemented":
            errors.append(
                f"(f) HONESTY: '{iid}' is a vegetation synthetic estimate but registry marks "
                f"source={e.get('source')} status={e.get('status')}"
            )

    # Extra honesty invariant: source=estimated must never be status=implemented.
    for e in indicators:
        if e.get("source") == "estimated" and e.get("status") == "implemented":
            errors.append(f"(f) HONESTY: '{e['id']}' has source=estimated but status=implemented")

    if errors:
        print("indicators_registry_gate FAILED:")
        for err in errors:
            print(f"  - {err}")
        raise SystemExit(1)

    print(
        f"indicators_registry_gate_ok ({len(indicators)} indicators, "
        f"{sum(1 for e in indicators if e.get('renderable'))} renderable, "
        f"estimate_only={sorted(veg_estimate_only)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
