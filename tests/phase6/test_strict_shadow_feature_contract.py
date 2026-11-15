"""Opt-in strict shadow contract tests; no production services required."""

import ast
from pathlib import Path

import pytest

from shared.feature_store.runtime import build_point_in_time_snapshot
from shared.feature_store.strict_shadow import strict_shadow_snapshot

pytestmark = pytest.mark.unit

MODULE = Path(__file__).resolve().parents[2] / "shared" / "feature_store" / "strict_shadow.py"
AS_OF = "2026-11-04T00:00:00Z"

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
    "prediction_at": "2026-11-03T12:00:00Z",
    "features": {"ndvi": 0.4},
}


def run(records, **kwargs):
    return strict_shadow_snapshot(
        records,
        tenant_id=kwargs.get("tenant_id", "A"),
        season_id=kwargs.get("season_id", "S1"),
        feature_set_id=kwargs.get("feature_set_id", "FS1"),
        as_of=AS_OF,
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


def test_bool_feature_rejected():
    result = run([{**BASE, "features": {"irrigated": True}}])
    assert result["row_count"] == 0
    assert result["excluded_by_reason"]["invalid_features"] == 1


def test_ingested_before_publication_rejected():
    # Ingested a day before it was published: impossible chronology. The feature
    # store authority rejects it; a parallel rule that only compares each stamp
    # with as_of admits it.
    record = {**BASE, "available_at": "2026-11-03T06:00:00Z", "ingested_at": "2026-11-02T00:00:00Z"}
    assert run([record])["row_count"] == 0


def test_missing_prediction_time_rejected():
    record = {k: v for k, v in BASE.items() if k != "prediction_at"}
    assert run([record])["row_count"] == 0


def test_admission_matches_the_feature_store_authority():
    """Within scope, the shadow admits exactly what the authority admits."""
    battery = [
        BASE,
        {**BASE, "entity_id": "F2", "event_time": "2026-10-01T00:00:00Z"},  # stale at 100 h
        {**BASE, "entity_id": "F3", "available_at": "2026-10-31T00:00:00Z"},  # before event
        {**BASE, "entity_id": "F4", "prediction_at": "2026-11-05T00:00:00Z"},  # after as_of
        {**BASE, "entity_id": "F5", "feature_available_at": {"ndvi": "2026-11-02T00:00:00Z"}},
        {**BASE, "entity_id": "F6", "available_at": "2026-11-03T06:00:00Z"},  # after ingestion
        {**BASE, "entity_id": "F7", "ingested_at": "2026-11-03T00:00:00+03:00"},
    ]
    authority = build_point_in_time_snapshot(battery, as_of=AS_OF, max_age_hours=100)
    shadow = run(battery)
    admitted = {row["entity_id"] for row in authority["rows"]}
    assert {row["entity_id"] for row in shadow["rows"]} == admitted
    assert admitted == {"F1", "F5", "F7"}


def test_module_holds_no_point_in_time_rule_of_its_own():
    """Chronology lives in shared.feature_store.runtime; this module only scopes."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "datetime" not in imported
    assert "build_point_in_time_snapshot" in imported
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {"fromisoformat", "total_seconds", "astimezone"}
