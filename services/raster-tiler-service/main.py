"""SAHOOL TiTiler wrapper with immutable runtime identity."""

from __future__ import annotations

from titiler.application.main import app

from shared.runtime_identity import load_build_identity


@app.get("/runtime-identity", include_in_schema=False)
def runtime_identity() -> dict[str, object]:
    return load_build_identity("raster-tiler-service")
