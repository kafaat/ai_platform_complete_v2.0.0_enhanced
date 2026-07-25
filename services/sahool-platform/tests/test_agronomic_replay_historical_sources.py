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
