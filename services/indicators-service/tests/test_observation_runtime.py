from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import UUID

MODULE = Path(__file__).resolve().parents[1] / "observation_runtime.py"
spec = importlib.util.spec_from_file_location("observation_runtime_tested", MODULE)
assert spec and spec.loader
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def test_bundle_is_converted_without_pixel_recomputation():
    bundle = {
        "field_id": "fld_abc123",
        "real_data": True,
        "bundle_consistency": True,
        "mixed_scene": False,
        "observations": {
            "ndvi": {
                "real_data": True,
                "date": "2026-07-15T07:35:29Z",
                "stats": {"mean": 0.61, "min": 0.2, "max": 0.8, "std": 0.1},
                "coverage_ratio": 0.94,
                "valid_pixel_ratio": 0.91,
                "cloud_cover": 0.04,
                "confidence": 0.89,
                "indicator_product": {
                    "provenance": {
                        "scene_id": "S2A_TEST_SCENE",
                        "algorithm_version": "2.1.0",
                        "acquisition_datetime": "2026-07-15T07:35:29Z",
                    }
                },
            }
        },
    }
    items = runtime.canonicalize_bundle(
        bundle=bundle,
        tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
        season_id="sea_2026",
    )
    assert len(items) == 1
    obs = items[0]
    assert obs.field_id == "fld_abc123"
    assert obs.summary.mean == runtime.Decimal("0.61")
    assert obs.observation_quality.gate_status.value == "passed"
    assert "pixel_array" not in type(obs).model_fields


def test_latest_and_timeline_only_label_verified_lst_as_kelvin():
    from observation_timeline import canonicalize_timeseries

    from shared.contracts.remote_sensing.thermal import LANDSAT_ST_KELVIN

    scope = dict(field_id="fld_a", tenant_id=UUID(int=1), season_id="season")
    for algorithm, expected in ((LANDSAT_ST_KELVIN, "K"), ("sahool.band_math/2", None)):
        point = {
            "datetime": "2026-11-13T07:00:00Z",
            "mean": 302.62973,
            "algorithm_version": algorithm,
        }
        (timeline,) = canonicalize_timeseries(**scope, indicator_code="lst", points=[point])
        item = {
            "date": point["datetime"],
            "stats": {"mean": point["mean"], "std": 0.0},
            "indicator_product": {
                "provenance": {"scene_id": "fixture", "algorithm_version": algorithm}
            },
        }
        (latest,) = runtime.canonicalize_bundle(
            bundle={"field_id": scope["field_id"], "observations": {"lst": item}},
            tenant_id=scope["tenant_id"],
            season_id=scope["season_id"],
        )
        assert latest.indicator.unit == timeline.indicator.unit == expected
        assert latest.summary.mean == timeline.summary.mean
        assert latest.summary.stddev == 0
