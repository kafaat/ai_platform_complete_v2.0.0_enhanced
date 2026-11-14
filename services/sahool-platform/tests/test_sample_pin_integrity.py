from copy import deepcopy

import pytest
from api.routers.soil_sampling import LabSampleIn
from pydantic import ValidationError


def collection():
    source = {"scene_id": "S2-1", "acquisition_date": "2026-05-01"}
    return {
        "field_id": "pivot",
        "kind": "soil",
        "latitude": 16.01,
        "longitude": 44.02,
        "depth_cm_from": 0,
        "depth_cm_to": 30,
        "sampling_plan_id": "plan-1",
        "sampling_origin": {
            "point_id": "point-1",
            "zone_id": "zone-1",
            "latitude": 16,
            "longitude": 44,
            "indicators": ["ndvi", "ndmi"],
            "indicator_sources": {"ndvi": source, "ndmi": deepcopy(source)},
        },
    }


@pytest.mark.parametrize(
    "attribute,value", [("scene_id", "S2-2"), ("scene_id", " "), ("acquisition_date", "2026-05-11")]
)
def test_sample_pin_rejects_incompatible_spectral_sources(attribute, value):
    request = collection()
    request["sampling_origin"]["indicator_sources"]["ndmi"][attribute] = value
    with pytest.raises(ValidationError):
        LabSampleIn.model_validate(request)


@pytest.mark.parametrize(
    "field,value",
    [
        ("latitude", True),
        ("longitude", False),
        ("gps_accuracy_m", True),
        ("gps_accuracy_m", "Infinity"),
    ],
)
def test_sample_actual_coordinates_and_accuracy_require_measurements(field, value):
    request = collection()
    request[field] = value
    with pytest.raises(ValidationError):
        LabSampleIn.model_validate(request)


def test_sample_planned_coordinates_require_measurements_and_remain_separate():
    request = collection()
    valid = LabSampleIn.model_validate(request)
    assert (valid.latitude, valid.longitude) != (
        valid.sampling_origin.latitude,
        valid.sampling_origin.longitude,
    )
    request["sampling_origin"]["longitude"] = False
    with pytest.raises(ValidationError):
        LabSampleIn.model_validate(request)


def test_legacy_sample_with_no_indicator_sources_still_validates():
    request = collection()
    del request["sampling_origin"]["indicator_sources"]
    assert LabSampleIn.model_validate(request).sampling_origin.indicator_sources == {}
