"""Historical backfill asks CDSE for the field, not the whole Sentinel-2 tile."""

import cdse_client

TILE = [44.0, 14.9, 45.0, 15.9]
FIELD = {
    "type": "Polygon",
    "coordinates": [
        [[44.40, 15.30], [44.41, 15.30], [44.41, 15.31], [44.40, 15.31], [44.40, 15.30]]
    ],
}


def test_field_bbox_wins_over_the_scene_tile():
    bbox = cdse_client.backfill_request_bbox({"bbox": TILE}, FIELD)
    assert bbox[0] >= 44.39 and bbox[2] <= 44.42
    assert (bbox[2] - bbox[0]) < 0.02 and (bbox[3] - bbox[1]) < 0.02


def test_scene_bbox_only_without_field_geometry():
    assert cdse_client.backfill_request_bbox({"bbox": TILE}, None) == TILE


def test_request_identity_is_computed_on_the_field_bbox():
    scene = {"bbox": TILE, "datetime": "2026-07-15T08:00:00Z"}
    digest_with_tile_scene, _ = cdse_client.backfill_request_identity(scene, "ndvi", FIELD)
    digest_without_tile, _ = cdse_client.backfill_request_identity(
        {"datetime": scene["datetime"]}, "ndvi", FIELD
    )
    # The tile no longer influences what is requested, so the identity is the same.
    assert digest_with_tile_scene == digest_without_tile
