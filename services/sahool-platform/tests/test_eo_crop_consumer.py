"""Execute the unmodified compose function AST with explicit service test doubles."""

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from core.crop_intelligence.spectral import build_canonical_spectral_state


@pytest.mark.parametrize("mode", ["server", "failed", "disabled"])
def test_compose_preserves_product_and_source_ids(mode):
    path = Path(__file__).parents[1] / "api/routers/crop_twin.py"
    node = next(
        n
        for n in ast.parse(path.read_text()).body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_compose_state"
    )
    product = build_canonical_spectral_state(
        ndvi=0.4,
        ndmi=-0.1,
        msi=1.22,
        quality_status="validated",
        product_ids=["ndvi-scene", "ndmi-scene", "msi-scene"],
        index_provenance={"ndvi": {"scene_id": "ndvi-scene"}, "ndmi": {"scene_id": "ndmi-scene"}},
        source_authority="raster-service",
        temporal_compatible=None,
    )
    calls = []
    captured = {}

    async def resolve(**kw):
        calls.append(kw)
        return product if mode == "server" else None

    async def weather(**kw):
        return {"daily_gdd": []}

    def twin(*a, **kw):
        captured.update(kw)
        return {}

    def build(**kw):
        if mode == "server":
            pytest.fail("server product rebuilt")
        return build_canonical_spectral_state(**kw)

    ns = dict(
        CropTwinComposeRequest=NS,
        ComposeForecastDay=NS,
        TwinDay=NS,
        soil_water_params=lambda *a, **kw: {"taw_mm": 100, "texture_known": True},
        compose_server_authoritative_spectral_enabled=lambda: mode != "disabled",
        resolve_canonical_spectral_state=resolve,
        kc_map_for_crop=lambda c: ({}, None),
        kc_from_ndvi=lambda n, *a: (n, None),
        build_canonical_spectral_state=build,
        crop_gdd_policy=lambda c: (10, 30),
        get_gdd_product=weather,
        crop_twin_state=twin,
        assess_data_quality=lambda a: {"assumptions": a},
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    req = NS(
        soil=NS(texture="silt", root_depth_m=1, raw_fraction=0.5, taw_mm=100),
        management=NS(target_uptake_kg_ha=100, initial_depletion_mm=10, auto_irrigate=False),
        ndvi=0.2,
        ndre=None,
        ndmi=None,
        msi=None,
        spectral_acquisition_date=None,
        spectral_product_ids=["client-id"],
        spectral_quality_status=None,
        spectral_temporal_compatible=None,
        field_id="field",
        season_id="season",
        crop="wheat",
        stage="mid",
        forecast=[],
    )
    result = asyncio.run(ns["_compose_state"](req, tenant_id="tenant"))
    if mode == "server":
        assert captured["spectral_state"] is product
        assert captured["source_ids"] == product["evidence_ids"]
        assert result["dyn_kc"] == 0.4
    else:
        assert captured["source_ids"] == ["client-id"]
        assert result["dyn_kc"] == 0.2
    assert len(calls) == (0 if mode == "disabled" else 1)
    assert result["spectral_unverified"] is (mode == "failed")
