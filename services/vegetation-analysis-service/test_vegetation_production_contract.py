from vegetation_contracts import build_snapshot, derive_lai_from_ndvi, quality_gate

PROV = {
    "scene_id": "S2_X",
    "acquisition_datetime": "2026-07-01T00:00:00Z",
    "algorithm_version": "bandmath-v3",
    "data_available_at": "2026-07-01T01:00:00Z",
}


def test_estimated_ndvi_is_never_executable():
    assert quality_gate({"ndvi": {"estimated": True, "value": 0.7}})["executable"] is False


def test_authoritative_ndvi_requires_full_provenance():
    ndvi = {
        "source": "raster-service",
        "estimated": False,
        "value": 0.7,
        "quality_score": 0.9,
        "provenance": PROV,
    }
    assert quality_gate({"ndvi": ndvi})["executable"] is True


def test_missing_scene_blocks_execution():
    p = dict(PROV)
    p.pop("scene_id")
    ndvi = {
        "source": "raster-service",
        "estimated": False,
        "value": 0.7,
        "quality_score": 0.9,
        "provenance": p,
    }
    assert "ndvi_provenance_scene_id_missing" in quality_gate({"ndvi": ndvi})["reasons"]


def test_lai_is_explicitly_derived():
    out = derive_lai_from_ndvi(0.7)
    assert out["estimated"] is True and out["algorithm_version"] == "1.0.0"


def test_snapshot_hash_is_deterministic_for_body(monkeypatch):
    s = build_snapshot(
        field_id="f",
        tenant_id="t",
        season_id="s",
        acquisition_date="2026-07-01",
        indices={},
        source="raster-service",
        quality={"executable": False},
        data_available_at="2026-07-01T01:00:00Z",
    )
    assert len(s["snapshot_hash"]) == 64 and s["contract_version"] == "vegetation-snapshot.v2"
