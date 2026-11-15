from datetime import date
from types import SimpleNamespace

import db_persist
import pytest
from layer_lookup import find_field_layer, resolve_field_layer


def asset(acquired, **metadata):
    return {
        "field_id": "F",
        "index": "ndvi",
        "cog_url": "test.tif",
        "acquisition_date": acquired,
        **metadata,
    }


def pick(rows, day="latest"):
    return find_field_layer(rows, {"F": list(rows)}, "F", "ndvi", day)


@pytest.mark.parametrize("day", ["latest", "2026-10-01"])
def test_rank_acquisitions_by_instant_before_creation(day):
    early = asset("2026-10-01T23:20:00+08:00", created_at="2026-10-05T23:00:00Z")
    late = asset("2026-10-01T18:10:00Z")
    assert pick({"early": early, "late": late}, day) is late


def test_latest_excludes_invalid_and_missing_dates():
    good = asset("2026-09-30")
    invalid = {"bad": asset("nonsense"), "missing": asset(None)}
    assert pick({**invalid, "good": good}) is good
    assert pick(invalid) is None


@pytest.mark.parametrize(
    "metadata_a,metadata_b",
    [
        ({"quality_score": 0.3, "cloud_pct": 1}, {"quality_score": 0.8, "cloud_pct": 50}),
        ({"quality_score": None}, {"quality_score": 0}),
        ({"cloud_pct": 35}, {"cloud_pct": 0}),
        ({"created_at": "2026-10-03T01:00:00+08:00"}, {"created_at": "2026-10-02T22:30:00Z"}),
    ],
)
def test_day_only_uses_database_quality_cloud_creation_order(metadata_a, metadata_b):
    first = asset("2026-10-01T23:00:00Z", **metadata_a)
    second = asset(date(2026, 10, 1), **metadata_b)
    for rows in [{"a": first, "b": second}, {"b": second, "a": first}]:
        assert pick(rows) is second


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mem_date,db_date,expected",
    [
        ("2026-10-02T00:30:00+03:00", "2026-10-02", "db"),
        ("2026-10-01T23:30:00-03:00", "2026-10-01", "mem"),
        ("not-a-date", "2026-10-01", "db"),
        ("not-a-date", None, None),
        ("2026-10-01T12:00:00Z", "2026-10-01", "db"),
    ],
)
async def test_resolve_latest_across_cache_and_database(monkeypatch, mem_date, db_date, expected):
    row = asset(db_date, quality_score=0.9, cog_url="db")

    async def fetch(*args, **kwargs):
        return row

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fetch)
    mem = asset(mem_date, quality_score=0.5, cog_url="mem")
    layers = {"mem": mem}
    by_field = {"F": ["mem"]}
    for _ in range(2):
        result = await resolve_field_layer(
            "F",
            "ndvi",
            "latest",
            layers=layers,
            field_layers=by_field,
            tenant_getter=lambda: None,
            object_store_module=SimpleNamespace(exists_locally=lambda _: True),
            logger=None,
        )
        assert (result["cog_url"] if result else None) == expected


@pytest.mark.asyncio
async def test_date_only_row_compares_against_entire_newest_day(monkeypatch):
    # Selecting a single memory winner first discards the morning asset, which
    # has the highest quality when one candidate has no recorded capture time.
    morning = asset("2026-10-01T08:00:00Z", quality_score=0.95)
    evening = asset("2026-10-01T18:00:00Z", quality_score=0.5)

    async def fetch(*args, **kwargs):
        return asset("2026-10-01", quality_score=0.8)

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fetch)
    layers = {"morning": morning, "evening": evening}
    result = await resolve_field_layer(
        "F",
        "ndvi",
        "latest",
        layers=layers,
        field_layers={"F": list(layers)},
        tenant_getter=lambda: None,
        object_store_module=SimpleNamespace(exists_locally=lambda _: True),
        logger=None,
    )
    assert result is morning


@pytest.mark.parametrize(
    "metadata",
    [
        {"asset_status": "stale"},
        {"asset_status": "failed"},
        {"asset_status": "pending"},
        {"valid_pixel_ratio": 0.0},
        {"valid_pixel_ratio": -0.1},
        {"valid_pixel_ratio": "NaN"},
    ],
)
def test_unavailable_cache_asset_cannot_hide_prior_valid_day_or_fill_exact_date(metadata):
    prior = asset("2026-10-01", asset_status="ready", valid_pixel_ratio=0.25)
    rows = {"prior": prior, "bad": asset("2026-10-02", **metadata)}
    assert pick(rows) is prior
    assert pick(rows, "2026-10-02") is None


@pytest.mark.parametrize("metadata", [{}, {"asset_status": None, "valid_pixel_ratio": None}])
def test_legacy_unknown_status_and_validity_remain_readable(metadata):
    row = asset("2026-10-02", **metadata)
    assert pick({"legacy": row}, "2026-10-02") is row


@pytest.mark.asyncio
async def test_exact_date_skips_stale_memory_and_rehydrates_ready_asset(monkeypatch):
    stale = asset("2026-10-02T06:00:00Z", asset_status="stale", cog_url="stale")
    calls = []

    async def fetch(field, index, day, tenant_id):
        calls.append((field, index, day, tenant_id))
        return asset(day, asset_status="ready", valid_pixel_ratio=0.6, cog_url="ready")

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fetch)
    selected = await resolve_field_layer(
        "F",
        "ndvi",
        "2026-10-02",
        layers={"stale": stale},
        field_layers={"F": ["stale"]},
        tenant_getter=lambda: "tenant",
        object_store_module=SimpleNamespace(exists_locally=lambda _: True),
        logger=None,
    )
    assert selected["cog_url"] == "ready"
    assert calls == [("F", "ndvi", "2026-10-02", "tenant")]
