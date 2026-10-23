"""Exercise production VRT + band_math against an independent pixel oracle."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/raster-service"))


def compare_window(paths, geometry, directory):
    import band_math
    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.warp import Resampling, reproject, transform_geom
    from stac_vrt import build_band_vrt

    vrt, mapping = build_band_vrt(
        paths, str(directory), clip_geometry=geometry, max_pixels=1_000_000
    )
    with rasterio.open(vrt) as src:
        if src.crs.to_epsg() is None or abs(src.res[0] - 10) > 1e-9 or abs(src.res[1] - 10) > 1e-9:
            raise ValueError("experiment requires a projected 10 m grid")
        if not src.crs.is_projected or src.crs.linear_units != "metre":
            raise ValueError("experiment requires metre units")
        shape, transform, crs = src.shape, src.transform, src.crs
        polygon = transform_geom("EPSG:4326", crs, geometry)
        inside = geometry_mask([polygon], shape, transform, invert=True)
        actual, reference = {}, {}
        for name in ("red", "nir", "scl"):
            index = mapping[name]
            raw = src.read(index, masked=True).astype("float64").filled(np.nan)
            actual[name] = (
                band_math.to_reflectance(raw, src.scales[index - 1], src.offsets[index - 1], np)
                if name != "scl"
                else raw
            )
            # Independent alignment uses reproject, not the VRT or its sidecars.
            with rasterio.open(paths[name]) as source:
                data = source.read(1, masked=True).astype("float64").filled(np.nan)
                target = np.full(shape, np.nan)
                reproject(
                    data,
                    target,
                    src_transform=source.transform,
                    src_crs=source.crs,
                    src_nodata=np.nan,
                    dst_transform=transform,
                    dst_crs=crs,
                    dst_nodata=np.nan,
                    resampling=Resampling.nearest,
                )
                reference[name] = (
                    target * source.scales[0] + source.offsets[0] if name != "scl" else target
                )

    def validity(bands):
        return (
            inside
            & np.isfinite(bands["red"])
            & np.isfinite(bands["nir"])
            & ~np.isin(bands["scl"], [3, 8, 9, 10, 11])
            & (bands["red"] >= -0.05)
            & (bands["red"] <= 1.2)
            & (bands["nir"] >= -0.05)
            & (bands["nir"] <= 1.2)
            & ((bands["red"] + bands["nir"]) != 0)
        )

    av, rv = validity(actual), validity(reference)
    if not np.array_equal(av, rv):
        raise AssertionError("validity masks differ")
    if not av.any():
        raise AssertionError("no valid pixels; cannot prove numerical equivalence")
    actual_ndvi = band_math.ndvi(actual["red"][av], actual["nir"][av], np)
    r, n = reference["red"][rv], reference["nir"][rv]
    expected = (n - r) / (n + r)
    error = float(np.max(np.abs(actual_ndvi - expected)))
    if error > 1e-5:
        raise AssertionError(f"NDVI maximum error {error} exceeds 1e-5")
    # A separate diagnostic; these operations intentionally have different meanings.
    order_delta = float(np.mean(expected) - (np.mean(n) - np.mean(r)) / (np.mean(n) + np.mean(r)))
    return {
        "valid_pixels": int(av.sum()),
        "mask_equal": True,
        "max_error": error,
        "mean_ndvi_minus_ndvi_of_means": order_delta,
        "correctness_pass": True,
        "performance_status": "NOT_MEASURED",
    }


def benchmark_windows(paths, geometries, repeats=20):
    """Repeated per-field VRT construction versus a shared scene VRT.

    This measures the named helper strategies, not the HTTP service or current
    production batch implementation. OS/provider cache is uncontrolled. Bytes
    count materialized arrays, never claimed as network transfer.
    """
    import resource

    import band_math
    import numpy as np
    import rasterio
    from rasterio.mask import mask
    from rasterio.warp import transform_geom
    from stac_vrt import build_band_vrt

    from .spatial import percentile

    if repeats < 20 or not geometries:
        raise ValueError("requires geometries and at least 20 repeats")

    def read_field(source, mapping, geometry):
        polygon = transform_geom("EPSG:4326", source.crs, geometry)
        data, transform = mask(
            source,
            [polygon],
            crop=True,
            filled=False,
            indexes=[mapping[x] for x in ("red", "nir", "scl")],
        )
        data = data.astype("float64").filled(np.nan)
        red = band_math.to_reflectance(
            data[0], source.scales[mapping["red"] - 1], source.offsets[mapping["red"] - 1], np
        )
        nir = band_math.to_reflectance(
            data[1], source.scales[mapping["nir"] - 1], source.offsets[mapping["nir"] - 1], np
        )
        valid = (
            np.isfinite(red)
            & np.isfinite(nir)
            & ~np.isin(data[2], [3, 8, 9, 10, 11])
            & (red >= -0.05)
            & (red <= 1.2)
            & (nir >= -0.05)
            & (nir <= 1.2)
            & ((nir + red) != 0)
        )
        values = np.full(red.shape, np.nan)
        values[valid] = band_math.ndvi(red[valid], nir[valid], np)
        return values, transform, data.nbytes + values.nbytes

    timings = {"per_field_vrt": [], "shared_scene_vrt": []}
    logical_bytes = {}
    first = {}
    with tempfile.TemporaryDirectory() as directory:
        for sample in range(repeats + 1):
            order = list(timings) if sample % 2 == 0 else list(reversed(timings))
            outputs = {}
            for strategy in order:
                start = time.perf_counter()
                results, materialized = [], 0
                with tempfile.TemporaryDirectory(dir=directory) as bundle:
                    if strategy == "shared_scene_vrt":
                        # Construct one bounded grid for all fields in this scene.
                        from rasterio.features import bounds

                        boxes = [bounds(g) for g in geometries]
                        west, south = min(b[0] for b in boxes), min(b[1] for b in boxes)
                        east, north = max(b[2] for b in boxes), max(b[3] for b in boxes)
                        envelope = {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [west, south],
                                    [east, south],
                                    [east, north],
                                    [west, north],
                                    [west, south],
                                ]
                            ],
                        }
                        vrt, mapping = build_band_vrt(
                            paths, bundle, clip_geometry=envelope, max_pixels=1_000_000
                        )
                        with rasterio.open(vrt) as src:
                            for geometry in geometries:
                                values, transform, size = read_field(src, mapping, geometry)
                                results.append((values, transform))
                                materialized += size
                    else:
                        for geometry in geometries:
                            with tempfile.TemporaryDirectory(dir=bundle) as field_bundle:
                                vrt, mapping = build_band_vrt(
                                    paths,
                                    field_bundle,
                                    clip_geometry=geometry,
                                    max_pixels=1_000_000,
                                )
                                with rasterio.open(vrt) as src:
                                    values, transform, size = read_field(src, mapping, geometry)
                                    results.append((values, transform))
                                    materialized += size
                elapsed = time.perf_counter() - start
                if sample == 0:
                    first[strategy] = elapsed
                else:
                    timings[strategy].append(elapsed)
                logical_bytes[strategy] = materialized
                outputs[strategy] = results
            for (a, at), (b, bt) in zip(
                outputs["per_field_vrt"], outputs["shared_scene_vrt"], strict=True
            ):
                if not at.almost_equals(bt) or a.shape != b.shape:
                    raise AssertionError("candidate output grid differs")
                if not np.array_equal(np.isfinite(a), np.isfinite(b)):
                    raise AssertionError("candidate mask differs")
                if not np.isfinite(a).any() or not np.allclose(
                    a, b, atol=1e-5, rtol=0, equal_nan=True
                ):
                    raise AssertionError("candidate NDVI differs or is empty")
    summaries = {
        k: {"p50": percentile(v, 0.5), "p95": percentile(v, 0.95), "n": len(v)}
        for k, v in timings.items()
    }
    gain = 1 - summaries["shared_scene_vrt"]["p95"] / summaries["per_field_vrt"]["p95"]
    return {
        "timings": summaries,
        "first_open_seconds": first,
        "cache": "uncontrolled",
        "p95_gain": gain,
        "adoption_pass": gain >= 0.2,
        "correctness_pass": True,
        "materialized_array_bytes": logical_bytes,
        "network_bytes_status": "NOT_MEASURED",
        "peak_process_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "scope": "VRT helpers; excludes discovery, HTTP API, upload and persistence",
    }
