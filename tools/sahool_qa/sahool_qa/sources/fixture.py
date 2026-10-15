"""GeoJSON fixture loader (offline mode, tests, demos).

A fixture is a FeatureCollection whose features carry properties.kind:
  field      -> polygon (or null geometry) + field_boundaries columns
  soil       -> point (or null) + soil_readings columns
  indicator  -> point (or null) + field_indicators columns
Top-level "sahool_qa": {"synthetic": bool, "description": str, "provenance": {...}}.

Tenant rules (same as the database loader): every record kind is filtered by
the tenant scope, and a record is admitted only if its owning field — same
tenant AND same field_id — was loaded. A record without a "tenant" property
inherits its owner's tenant only when that owner is unambiguous.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..facts import FactStore, Field, Indicator, SoilSample, parse_ts, to_float, to_float_raw
from ..geo import Geometry, parse_point


def load_fixture(
    path: str, tenant: str | None = None, all_tenants: bool = False, tenant_null: bool = False
) -> FactStore:
    if sum([tenant is not None, all_tenants, tenant_null]) != 1:
        raise ValueError("choose exactly one tenant scope: tenant, tenant_null or all_tenants")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    meta = data.get("sahool_qa", {})
    scope = (
        "ALL TENANTS"
        if all_tenants
        else "tenant_id IS NULL"
        if tenant_null
        else f"tenant_id = {tenant}"
    )
    store = FactStore(
        synthetic=bool(meta.get("synthetic", False)),
        source=f"fixture:{Path(path).name}",
        tenant_scope=scope,
        provenance=meta.get("provenance", {}),
    )

    def in_scope(t) -> bool:
        if all_tenants:
            return True
        if tenant_null:
            return t is None
        return t is not None and str(t) == str(tenant)

    feats = data.get("features", [])
    for ft in feats:
        p, g = ft.get("properties", {}), ft.get("geometry")
        if p.get("kind") != "field":
            continue
        if not in_scope(p.get("tenant")):
            store.rejected["out_of_scope_tenant"] += 1
            continue
        store.add_field(
            Field(
                id=str(p["id"]),
                name=p.get("name") or str(p["id"]),
                tenant=p.get("tenant"),
                governorate=p.get("governorate"),
                crop=p.get("crop"),
                soil_type=p.get("soil_type"),
                area_ha_stored=to_float(p.get("area_ha")),
                lat=to_float(p.get("latitude")),
                lon=to_float(p.get("longitude")),
                geom=Geometry.from_geojson(g),
            )
        )
    for ft in feats:
        p, g = ft.get("properties", {}), ft.get("geometry")
        kind = p.get("kind")
        if kind not in ("soil", "indicator"):
            continue
        if "tenant" in p:
            t = p["tenant"]
        else:
            ok, t = store.inherit_tenant(str(p.get("field_id")))
            if not ok:
                store.rejected["ambiguous_owner"] += 1
                continue
        if not in_scope(t):
            store.rejected["out_of_scope_tenant"] += 1
            continue
        common = dict(
            field_id=str(p["field_id"]),
            recorded_ts=parse_ts(p.get("recorded_at")),
            source=p.get("source"),
            point=parse_point(g) if g else None,
            tenant=t,
            record_id=None if p.get("record_id") is None else str(p["record_id"]),
        )
        if kind == "soil":
            rec = SoilSample(
                sample_id=str(p["sample_id"]),
                **{a: to_float_raw(p.get(a)) for a in SoilSample.MEASURES},
                **common,
            )
        else:
            rec = Indicator(
                indicator_id=str(p["indicator_id"]),
                value=to_float_raw(p.get("value")),
                category=p.get("category"),
                unit=p.get("unit"),
                status=p.get("status"),
                **common,
            )
        store.admit(rec)
    # Inventory is domain data: provenance must obey the same tenant/field scope as records.
    if "water_well_inventory" in store.provenance:
        store.provenance["water_well_inventory"] = {
            key: value
            for key, value in store.provenance["water_well_inventory"].items()
            if key in store.fields
        }
    return store
