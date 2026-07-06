"""CDSE historical-backfill scene processing helper.

Kept context-based during staged decomposition because it still depends on main's
job-processing façade and compatibility API model aliases.
"""

from __future__ import annotations

import os
import uuid


def process_backfill_scene_cdse(
    ctx,
    scene: dict,
    index: str,
    field_id: str,
    tenant_id: str | None,
    clip: dict | None,
    geometry_revision,
    jid: str,
) -> None:
    import cdse_client

    dt = scene.get("datetime") or ""
    day = dt[:10]
    if len(day) != 10:
        raise RuntimeError("CDSE scene بلا تاريخ صالح")
    bbox = scene.get("bbox") or ctx._bbox_from_geojson(clip)
    if not bbox:
        raise RuntimeError("bbox مطلوب لمعالجة مشهد CDSE")
    tiff = cdse_client.get_client().process_index(
        index=index,
        bbox=bbox,
        time_from=f"{day}T00:00:00Z",
        time_to=f"{day}T23:59:59Z",
        geometry=clip,
        max_cloud_pct=40.0,
    )
    if not tiff:
        raise RuntimeError("CDSE process_index أرجع استجابة فارغة")
    tif_path = os.path.join(ctx.UPLOAD_DIR, f"cdse_bf_{index}_{uuid.uuid4().hex[:8]}.tif")
    with open(tif_path, "wb") as fh:
        fh.write(tiff)
    preq = ctx.ProcessRequest(
        tenant_id=tenant_id or "",
        field_id=field_id,
        raster_url=tif_path,
        indicator=ctx.IndicatorKind(index),
        source_format=ctx.SourceFormat.sentinel2_l2a,
        bands=ctx.BandMapping(),
        precomputed_index=True,
        provider="cdse",
        scene_id=scene.get("item_id"),
        capture_datetime=dt,
        clip_polygon_geojson=clip,
        apply_cloud_mask=False,
        geometry_revision=geometry_revision,
    )
    ctx._run_processing(jid, preq)
