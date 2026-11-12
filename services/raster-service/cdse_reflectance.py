"""Compute mixed-resolution normalized differences on the coarser output grid.

CDSE exposes nearest, bilinear and bicubic resampling for an entire S2 input.
Request both reflectances, SCL, dataMask and scene ordinal on one nearest-sampled
working grid. Average the reflectances within each output cell before division.
This grid is tied to the requested footprint, not the native UTM detector grid.
"""

import hashlib
import json
from dataclasses import replace

import cdse_native_product as native


def build_evalscript(index, bands, factors):
    inputs = json.dumps([*bands, "SCL", "dataMask"])
    return (
        "//VERSION=3\n"
        f"// sahool/block-mean-v1 {index} {factors[0]}x{factors[1]}\n"
        "function setup() { return { "
        f"input: [{{bands: {inputs}}}], "
        'output: {bands: 5, sampleType: "FLOAT32"}, mosaicking: "TILE" }; }\n'
        "function evaluatePixel(samples) {\n"
        "  for (let i = 0; i < samples.length; i++) { const s = samples[i];\n"
        f"    if (s.dataMask === 1) return [s.{bands[0]}, s.{bands[1]}, s.SCL, 1, i+1];\n"
        "  } return [NaN, NaN, 0, 0, 0];\n}\n"
        "function updateOutputMetadata(scenes, inputMetadata, outputMetadata) {\n"
        f"  outputMetadata.userData = {{schema: {json.dumps(native.SCHEMA)}, "
        "tiles: scenes.tiles.map(t => ({id: String(t.shId), date: t.date}))};\n}\n"
    )


def finish(content, bands, payload, factors, with_native_qa):
    import numpy as np
    import rasterio
    from affine import Affine
    from band_math import normalized_difference

    if len(content) > native.MAX_RESPONSE_BYTES:
        raise ValueError("cdse_native_response_too_large")
    product = (
        native.decode_response(content, payload["evalscript"], request_payload=payload)
        if with_native_qa
        else None
    )
    width, height = (payload["output"][key] for key in ("width", "height"))
    epsg, bbox = native._requested_grid(payload)
    grid = product or native.NativeProduct(
        b"",
        "",
        "",
        (),
        expected_width=width,
        expected_height=height,
        expected_epsg=epsg,
        expected_bbox=bbox,
    )
    fx, fy = factors
    cols, rows = width // fx, height // fy
    with rasterio.MemoryFile(product.tiff if product else content) as mem, mem.open() as src:
        if (
            src.count != 5
            or src.dtypes != ("float32",) * 5
            or src.crs is None
            or (src.width, src.height) != (width, height)
        ):
            raise ValueError("cdse_reflectance_grid_invalid")
        native._assert_requested_grid(src, grid)
        first, second, scl, mask, scene = src.read()
        band_valid = (src.read_masks(1) > 0) & (src.read_masks(2) > 0)
        transform = src.transform * Affine.scale(fx, fy)
        crs = src.crs

    present = mask == 1
    if not np.isin(mask, (0, 1)).all() or not np.isin(scl[present], range(12)).all():
        raise ValueError("cdse_reflectance_qa_invalid")
    if not np.isin(scene[present], range(1, (len(product.tiles) if product else 256) + 1)).all():
        raise ValueError("cdse_reflectance_scene_invalid")

    def blocks(array):
        return array.reshape(rows, fy, cols, fx)

    axes = (1, 3)
    full = blocks(present).all(axis=axes)
    cloudy = blocks(np.isin(scl, (3, 8, 9, 10, 11))).any(axis=axes)
    clear = blocks(np.isin(scl, (2, 4, 5, 6, 7))).all(axis=axes)
    lower_scene = blocks(scene).min(axis=axes)
    if np.any(full & (lower_scene != blocks(scene).max(axis=axes))):
        raise ValueError("cdse_reflectance_mixed_contributor_block")
    usable = (
        full
        & clear
        & blocks(
            band_valid & np.isfinite(first) & np.isfinite(second) & (first >= 0) & (second >= 0)
        ).all(axis=axes)
    )
    a, b = (blocks(band).mean(axis=axes, dtype="float64") for band in (first, second))
    nir, reference = (a, b) if bands[0] == "B08" else (b, a)
    result = np.where(usable, normalized_difference(nir, reference, np), np.nan).astype("float32")

    with rasterio.MemoryFile() as out:
        with out.open(
            driver="GTiff",
            width=cols,
            height=rows,
            count=4 if product else 1,
            dtype="float32",
            crs=crs,
            transform=transform,
        ) as dst:
            dst.write(result, 1)
            if product:
                # Preserve a real class from the block, prioritizing clouds then invalid
                # classes. No interpolation or invented majority class at field edges.
                cloud_class = blocks(np.where(np.isin(scl, (3, 8, 9, 10, 11)), scl, 0)).max(
                    axis=axes
                )
                invalid_class = blocks(np.where(np.isin(scl, (0, 1)), scl, 12)).min(axis=axes)
                output_scl = np.where(
                    cloudy, cloud_class, np.where(clear, scl[::fy, ::fx], invalid_class)
                )
                dst.write(np.where(full, output_scl, 0).astype("float32"), 2)
                dst.write(full.astype("float32"), 3)
                dst.write(np.where(full, lower_scene, 0).astype("float32"), 4)
        tiff = out.read()
    if product:
        return replace(
            product,
            tiff=tiff,
            tiff_sha256=hashlib.sha256(tiff).hexdigest(),
            source_tiff_sha256=product.tiff_sha256,
            expected_width=cols,
            expected_height=rows,
        )
    return tiff
