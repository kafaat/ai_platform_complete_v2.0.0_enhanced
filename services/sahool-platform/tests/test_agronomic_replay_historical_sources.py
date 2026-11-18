from api.agronomic_replay import build_agronomic_replay


def test_replay_merges_persisted_weather_manual_irrigation_and_harvest():
    out = build_agronomic_replay(
        "field-a",
        weather=[{"date": "2025-01-01", "t_max": 28, "rain_mm": 3}],
        irrigation=[
            {
                "date": "2025-01-02",
                "name": "ريّ من دفتر موسم معتمد",
                "water_target_mm": 15,
                "schedule_id": "event-a",
            }
        ],
        outcomes=[
            {
                "date": "2025-05-01",
                "label_ar": "حصاد من دفتر موسم معتمد",
                "value": 4200,
                "ref_id": "record-a",
            }
        ],
    )
    assert [event["track"] for event in out["events"]] == [
        "weather",
        "irrigation",
        "outcome",
    ]
    assert out["events"][-1]["value"] == 4200
    assert out["counts_by_track"]["weather"] == 1


def test_replay_historical_weather_carries_persisted_measurements():
    import json

    from api.agronomic_replay import historical_weather_replay_row

    measurements = {"tmax_c": 31, "tmin_c": -2, "precipitation_mm": 0, "et0_mm": None}
    for payload in (measurements, json.dumps(measurements)):
        row = historical_weather_replay_row({"date": "2025-01-01", "payload": payload})
        event = build_agronomic_replay("field-a", weather=[row])["events"][0]
        assert event["value"] == {"t_max": 31, "t_min": -2, "rain_mm": 0}
        assert event["date"] == "2025-01-01"


def test_replay_historical_weather_keeps_legacy_shape_and_observation_date():
    from api.agronomic_replay import historical_weather_replay_row

    payload = {"date": "2000-01-01", "rain_mm": 0, "precipitation_mm": 2, "summary_ar": "جاف"}
    day = historical_weather_replay_row({"date": "2025-01-01", "payload": payload})
    event = build_agronomic_replay("field-a", weather=[day])["events"][0]
    assert (event["date"], event["label_ar"], event["value"]) == (
        "2025-01-01",
        "جاف",
        {"rain_mm": 0},
    )


def test_replay_historical_weather_does_not_invent_missing_values():
    from api.agronomic_replay import historical_weather_replay_row

    for payload in ({"precipitation_mm": None, "humidity_pct": 71}, "invalid", "[]", None):
        day = historical_weather_replay_row({"date": "2025-01-01", "payload": payload})
        assert build_agronomic_replay("field-a", weather=[day])["events"][0]["value"] is None
