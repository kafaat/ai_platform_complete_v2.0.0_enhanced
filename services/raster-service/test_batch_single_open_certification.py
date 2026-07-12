from __future__ import annotations

from collections import Counter

import numpy as np
import raster_api_models as models
import raster_job_orchestration
import raster_processing_runtime
import rasterio
from rasterio.transform import from_origin


class _DatasetProxy:
    def __init__(self, inner, reads: Counter[int]):
        self._inner = inner
        self._reads = reads

    def read(self, indexes=None, *args, **kwargs):
        if isinstance(indexes, int):
            self._reads[indexes] += 1
        return self._inner.read(indexes, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def close(self):
        return self._inner.close()


def test_batch_opens_source_once_and_reads_each_shared_band_once(tmp_path, monkeypatch):
    source = tmp_path / "scene.tif"
    profile = {
        "driver": "GTiff",
        "width": 8,
        "height": 8,
        "count": 6,
        "dtype": "float32",
        "crs": "EPSG:32638",
        "transform": from_origin(500000, 1700000, 10, 10),
        "nodata": -9999.0,
    }
    with rasterio.open(source, "w", **profile) as dst:
        for band in range(1, 7):
            dst.write(np.full((8, 8), band / 10.0, dtype="float32"), band)

    real_open = rasterio.open
    source_opens = 0
    reads: Counter[int] = Counter()

    def counted_open(path, *args, **kwargs):
        nonlocal source_opens
        ds = real_open(path, *args, **kwargs)
        if str(path) == str(source) and (not args or args[0] == "r") and "mode" not in kwargs:
            source_opens += 1
            return _DatasetProxy(ds, reads)
        return ds

    monkeypatch.setattr(rasterio, "open", counted_open)
    ctx = raster_processing_runtime.make_processing_context(upload_dir=str(tmp_path))
    ctx._persist_raster_asset = lambda *a, **k: False
    req = models.BatchProcessRequest(
        tenant_id="tenant-1",
        field_id="field-1",
        raster_url=str(source),
        indicators=[models.IndicatorKind.ndvi, models.IndicatorKind.ndmi, models.IndicatorKind.evi],
        source_format=models.SourceFormat.custom,
        bands=models.BandMapping(red=1, green=2, blue=3, nir=4, swir1=5, swir2=6),
        apply_cloud_mask=False,
        raw_qa_required=False,
    )
    job_id = "batch_single_open_test"
    ctx._jobs.set(job_id, {"job_id": job_id, "status": models.JobStatus.pending})

    raster_job_orchestration.run_batch_processing(ctx, job_id, req)
    job = ctx._jobs.get(job_id)

    assert job["status"] == models.JobStatus.completed
    assert job["single_open_certified"] is True
    assert job["batch_io_strategy"] == "single_dataset_open_shared_band_cache"
    assert source_opens == 1
    # red, green, blue, nir, swir1, swir2 are shared across all three indicators.
    assert all(count == 1 for count in reads.values())
    assert set(reads) == {1, 2, 3, 4, 5, 6}
