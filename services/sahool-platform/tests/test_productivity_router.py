from api.main import app, get_current_user
from core.canonical_schemas import UserRole, UserSchema
from fastapi.testclient import TestClient


def _user():
    return UserSchema(
        user_id="u1",
        tenant_id="00000000-0000-0000-0000-000000000001",
        role=UserRole.MANAGER,
        name_ar="مدير",
    )


def test_productivity_endpoints_are_exposed_and_grounded():
    app.dependency_overrides[get_current_user] = _user
    client = TestClient(app)
    try:
        r = client.post(
            "/api/v1/fields/field-a/productivity-zones",
            json={"field_id": "field-a", "observations": []},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["zones"] == []
        assert body["data_sufficiency"] == "limited"
        assert body["source_policy"] == "caller_supplied_observations_only"

        r = client.post(
            "/api/v1/fields/field-a/zone-sampling-plan",
            json={
                "field_id": "field-a",
                "observations": [
                    {"id": "low", "area_ha": 2, "ndvi_mean": 0.25, "lat": 15.0, "lng": 44.0},
                    {"id": "no-gps", "area_ha": 1, "ndvi_mean": 0.75},
                ],
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 3
        assert body["unplaceable_observation_ids"] == ["no-gps"]
        assert body["source_policy"] == "no_fake_coordinates"

        r = client.post(
            "/api/v1/fields/field-a/daily-ai-brief",
            json={"signals": {"ndvi_drop_pct": 12, "wind_speed_kmh": 28}, "tasks": []},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["field_id"] == "field-a"
        assert body["tenant_id"].endswith("0001")
        assert body["is_grounded"] is True
    finally:
        app.dependency_overrides.clear()
