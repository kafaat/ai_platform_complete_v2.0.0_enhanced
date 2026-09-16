"""SAHOOL TiTiler wrapper with immutable runtime identity."""

from __future__ import annotations

from titiler.application.main import app

from shared.runtime_identity import load_build_identity


@app.get("/runtime-identity", include_in_schema=False)
def runtime_identity() -> dict[str, object]:
    return load_build_identity("raster-tiler-service")


@app.get("/metrics", include_in_schema=False)
def metrics():
    """مقاييس Prometheus. قاعدةُ `SahoolRasterTileJSONUnavailable` تسمّي وظيفة
    `raster-tiler` منذ كتابتها ولم يكن لها هدفُ سحبٍ أصلاً، فالتنبيهُ **لا يُطلِق
    أبداً** — صمتٌ يُقرأ سلامةً، وهو عكسُ العطل الذي أبلغت عنه الجولة الحيّة.
    هذه النقطةُ وهدفُها في `prometheus.yml` يجعلان القاعدة قابلةً للإطلاق."""
    from fastapi import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
