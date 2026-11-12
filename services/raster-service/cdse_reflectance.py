"""Compute mixed-resolution indices on the coarser output grid.

CDSE exposes nearest, bilinear and bicubic resampling for an entire S2 input.
Request all reflectances, SCL, dataMask and scene ordinal on one nearest-sampled
working grid. Average the reflectances within each output cell before computing the index.
This grid is tied to the requested footprint, not the native UTM detector grid.
"""

import hashlib
import json
from dataclasses import replace

import cdse_native_product as native


def build_evalscript(index, bands, factors):
    channels = ", ".join(f"s.{band}" for band in bands)
    empty = ", ".join("NaN" for _ in bands)
    inputs = json.dumps([*bands, "SCL", "dataMask"])
    return (
        "//VERSION=3\n"
        f"// sahool/block-mean-v1 {index} {factors[0]}x{factors[1]}\n"
        "function setup() { return { "
        f"input: [{{bands: {inputs}}}], "
        f'output: {{bands: {len(bands) + 3}, sampleType: "FLOAT32"}}, mosaicking: "TILE" }}; }}\n'
        "function evaluatePixel(samples) {\n"
        "  for (let i = 0; i < samples.length; i++) { const s = samples[i];\n"
        f"    if (s.dataMask === 1) return [{channels}, s.SCL, 1, i+1];\n"
        f"  }} return [{empty}, 0, 0, 0];\n}}\n"
        "function updateOutputMetadata(scenes, inputMetadata, outputMetadata) {\n"
        f"  outputMetadata.userData = {{schema: {json.dumps(native.SCHEMA)}, "
        "tiles: scenes.tiles.map(t => ({id: String(t.shId), date: t.date}))};\n}\n"
    )


def _index_from_means(index, means, np):
    from band_math import ccci, chlorophyll_index, msi, normalized_difference
    from soil_indices import compute_bsi

    nir = means["B08"]
    if index == "ccci":
        return ccci(means["B04"], nir, means["B05"], np)
    if index == "bsi":
        return compute_bsi(means["B02"], means["B04"], nir, means["B12"], np)
    if index == "reci":
        return chlorophyll_index(nir, means["B05"], np)
    if index == "msi":
        return msi(nir, means["B11"], np)
    reference = {"ndre": "B05", "ndmi": "B11", "moisture": "B11", "nbr": "B12"}[index]
    return normalized_difference(nir, means[reference], np)


def finish(content, index, bands, payload, factors, with_native_qa):
    import numpy as np
    import rasterio
    from affine import Affine

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

    def blocks(array):
        return array.reshape(rows, fy, cols, fx)

    axes = (1, 3)
    wire_count = len(bands) + 3
    with rasterio.MemoryFile(product.tiff if product else content) as mem, mem.open() as src:
        if (
            src.count != wire_count
            or src.dtypes != ("float32",) * wire_count
            or src.crs is None
            or (src.width, src.height) != (width, height)
        ):
            raise ValueError("cdse_reflectance_grid_invalid")
        native._assert_requested_grid(src, grid)
        scl, mask, scene = src.read((wire_count - 2, wire_count - 1, wire_count))
        band_valid = np.ones((rows, cols), dtype=bool)
        means = {}
        for number, band in enumerate(bands, start=1):
            values = src.read(number)
            valid = (src.read_masks(number) > 0) & np.isfinite(values) & (values >= 0)
            band_valid &= blocks(valid).all(axis=axes)
            means[band] = blocks(values).mean(axis=axes, dtype="float64")
        transform = src.transform * Affine.scale(fx, fy)
        crs = src.crs

    present = mask == 1
    if not np.isin(mask, (0, 1)).all() or not np.isin(scl[present], range(12)).all():
        raise ValueError("cdse_reflectance_qa_invalid")
    if not np.isin(scene[present], range(1, (len(product.tiles) if product else 256) + 1)).all():
        raise ValueError("cdse_reflectance_scene_invalid")

    full = blocks(present).all(axis=axes)
    cloudy = blocks(np.isin(scl, (3, 8, 9, 10, 11))).any(axis=axes)
    clear = blocks(np.isin(scl, (2, 4, 5, 6, 7))).all(axis=axes)
    lower_scene = blocks(scene).min(axis=axes)
    if np.any(full & (lower_scene != blocks(scene).max(axis=axes))):
        raise ValueError("cdse_reflectance_mixed_contributor_block")
    usable = full & clear & band_valid
    result = np.where(usable, _index_from_means(index, means, np), np.nan).astype("float32")

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
