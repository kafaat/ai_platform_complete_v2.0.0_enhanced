from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from indicator_batch_claim import BatchClaimStore, batch_claim_key


class Bands:
    def model_dump(self, mode=None):
        return {"red": 1, "nir": 2, "blue": 3, "scl": 4}


def req(indicators=("ndvi", "ndmi")):
    return SimpleNamespace(
        tenant_id="tenant-a",
        field_id="field-a",
        scene_id="scene-a",
        capture_datetime="2026-07-12T00:00:00Z",
        raster_url="/tmp/scene.tif",
        source_format="sentinel2_l2a",
        indicators=list(indicators),
        bands=Bands(),
        clip_polygon_geojson={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        geometry_revision=2,
        apply_cloud_mask=True,
        raw_qa_required=True,
        min_raw_quality_score=0.5,
    )


def test_key_is_order_insensitive_and_deduplicates_indicators():
    assert batch_claim_key(req(("ndvi", "ndmi", "ndvi"))) == batch_claim_key(req(("ndmi", "ndvi")))


def test_key_changes_for_geometry_revision():
    a = req()
    b = req()
    b.geometry_revision = 3
    assert batch_claim_key(a) != batch_claim_key(b)


def test_parallel_claim_has_single_winner_and_same_job_id():
    store = BatchClaimStore(None)
    key = "k"

    def run(i):
        return store.claim(key, f"job-{i}")

    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(run, range(64)))
    assert sum(r.acquired for r in results) == 1
    assert len({r.job_id for r in results}) == 1


def test_compare_and_release_does_not_remove_other_claim():
    store = BatchClaimStore(None)
    assert store.claim("k", "job-a").acquired
    assert not store.release("k", "job-b")
    assert not store.claim("k", "job-c").acquired
    assert store.release("k", "job-a")
    assert store.claim("k", "job-c").acquired
