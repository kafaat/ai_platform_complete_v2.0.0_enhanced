#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "config/indicators_registry.json"
PLAT = ROOT / "services/sahool-platform/api/indicator_catalog.generated.json"
VEG = ROOT / "services/vegetation-analysis-service/indicator_capabilities.generated.json"
# manifest الواجهة يملكه المولِّد المُثبَت generate_indicators_frontend_manifest.py
# (شكل snake_case + source_class/availability + REGISTRY_VERSION/DIGEST الذي تعتمده
# useIndicatorRegistry) — هذا المولِّد يتولّى كتالوجَي المنصّة وvegetation فقط.


def canonical():
    return json.loads(REG.read_text(encoding="utf-8"))


def payloads():
    r = canonical()
    inds = r["indicators"]
    platform = [
        {
            k: e.get(k)
            for k in (
                "id",
                "category",
                "name_ar",
                "name_en",
                "unit",
                "source",
                "renderable",
                "status",
                "owning_service",
            )
        }
        for e in inds
    ]
    veg = []
    for e in inds:
        if e.get("category") in {"vegetation", "water"}:
            comp = e.get("computation") or {}
            veg.append(
                {
                    "id": e["id"],
                    "kind": "observed"
                    if e.get("source") == "real"
                    else "derived"
                    if e.get("owning_service") == "vegetation-analysis-service"
                    and e.get("status") == "implemented"
                    else e.get("source", "derived"),
                    "range": e.get("range"),
                    "unit": e.get("unit") or "index",
                    "owner": e.get("owning_service"),
                    "raster_alias": comp.get("raster_alias"),
                    "decision_eligible": e.get("source") == "real"
                    and e.get("status") == "implemented",
                    "min_valid_pixel_pct": 60.0,
                }
            )
    return (
        json.dumps(
            {
                "schema_version": r.get("schema_version", "indicator-registry.v1"),
                "indicators": platform,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        json.dumps(
            {
                "schema_version": r.get("schema_version", "indicator-registry.v1"),
                "capabilities": veg,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    vals = payloads()
    paths = (PLAT, VEG)
    bad = []
    for p, v in zip(paths, vals, strict=True):
        if a.check:
            if not p.exists() or p.read_text(encoding="utf-8") != v:
                bad.append(str(p.relative_to(ROOT)))
        else:
            p.write_text(v, encoding="utf-8")
    if bad:
        raise SystemExit("generated indicator artifacts drift: " + ", ".join(bad))
    print("indicator_artifacts_ok")


if __name__ == "__main__":
    main()
