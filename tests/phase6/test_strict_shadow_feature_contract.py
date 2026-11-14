"""Opt-in strict shadow contract tests; no production services required."""

from shared.feature_store.strict_shadow import strict_shadow_snapshot

BASE = {
    "tenant_id": "A",
    "season_id": "S1",
    "feature_set_id": "FS1",
    "entity_type": "field",
    "entity_id": "F1",
    "source_version": "v1",
    "event_time": "2026-11-01T00:00:00Z",
    "available_at": "2026-11-02T00:00:00Z",
    "ingested_at": "2026-11-03T00:00:00Z",
    "features": {"ndvi": 0.4},
}


def run(records, **kwargs):
    return strict_shadow_snapshot(
        records,
        tenant_id=kwargs.get("tenant_id", "A"),
        season_id=kwargs.get("season_id", "S1"),
        feature_set_id=kwargs.get("feature_set_id", "FS1"),
        as_of="2026-11-04T00:00:00Z",
        max_age_hours=100,
    )


def test_valid_shadow_only():
    result = run([BASE])
    assert result["row_count"] == 1
    assert result["mode"] == "shadow"


def test_tenant_isolation():
    result = run([{**BASE, "tenant_id": "B"}])
    assert result["row_count"] == 0
    assert result["excluded_by_reason"]["other_tenant"] == 1


def test_season_isolation():
    assert run([{**BASE, "season_id": "S2"}])["row_count"] == 0


def test_feature_set_isolation():
    assert run([{**BASE, "feature_set_id": "FS2"}])["row_count"] == 0


def test_future_publication_rejected():
    assert run([{**BASE, "available_at": "2026-12-01T00:00:00Z"}])["row_count"] == 0


def test_future_ingestion_rejected():
    assert run([{**BASE, "ingested_at": "2026-12-01T00:00:00Z"}])["row_count"] == 0


def test_nonfinite_features_rejected():
    assert run([{**BASE, "features": {"ndvi": float("nan")}}])["row_count"] == 0
    assert run([{**BASE, "features": {"ndvi": float("inf")}}])["row_count"] == 0


def test_wrong_entity_rejected():
    assert run([{**BASE, "entity_type": "farm"}])["row_count"] == 0


def test_missing_provenance_rejected():
    assert run([{**BASE, "source_version": ""}])["row_count"] == 0


def test_snapshot_digest_stable():
    assert run([BASE])["snapshot_id"] == run([BASE])["snapshot_id"]


def test_snapshot_digest_tenant_scoped():
    b = {**BASE, "tenant_id": "B"}
    assert run([BASE])["snapshot_id"] != run([b], tenant_id="B")["snapshot_id"]


def test_snapshot_digest_season_scoped():
    b = {**BASE, "season_id": "S2"}
    assert run([BASE])["snapshot_id"] != run([b], season_id="S2")["snapshot_id"]


def test_invalid_timezone_rejected():
    assert run([{**BASE, "event_time": "2026-11-01T00:00:00"}])["row_count"] == 0
