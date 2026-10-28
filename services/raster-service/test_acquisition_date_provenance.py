"""حارس نَسَب تاريخ الالتقاط (cluster acq-provenance، تدقيق 2026-10-27).

ثلاث مطالبات تحقّقنا منها على المصدر الحاليّ قبل الإصلاح:

* **T1** — مُجمِّع الأيّام كان يأخذ أوّل قيمة غير فارغة لكلّ خاصّية **مستقلّةً**، فينتج سجلّاً
  واحداً يجمع ``scene_id`` من المساهم A مع وقت الالتقاط وسحابة الحقل من المساهم B لليوم نفسه.
  العقد الآن: مساهمٌ ممثِّل واحد لكلّ يوم بقاعدة صريحة، تُؤخذ خصائص مشهده معاً، مع عدّاد
  ``contributors``.
* **T3** — تاريخ صريح غير صالح في مسار الأصل المُدَام كان يصير ``NULL`` في فلتر SQL
  (``$3::date IS NULL``) فيُختار **الأحدث** بدل الرفض. العقد الآن: 422 عند الحدّ، وفشلٌ مغلق
  (لا أصل) داخل ``fetch_latest_asset``.
* **T4** — اشتقاق اليوم بقصّ أوّل 10 محارف بلا تطبيع UTC: ``2026-10-01T00:30:00+03:00`` كان
  يُجمَّع/يُخزَّن تحت 1 أكتوبر بينما يومه بـUTC هو 30 سبتمبر.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

OFFSET_TS = "2026-10-01T00:30:00+03:00"  # يومه بـUTC: 2026-09-30


def _accumulator():
    from raster_available_dates import create_date_accumulator

    return create_date_accumulator(
        display_index=lambda x: x, high_quality_clear_pct=80, min_clear_pct=50
    )


# ─── T1: مساهم ممثِّل واحد لكلّ يوم ────────────────────────────────────────────


def test_t1_day_record_never_combines_properties_of_two_contributors():
    """شاهد التدقيق: أصلٌ مُدَام A (سحابة مشهد 70) + عنصر كتالوج B (وقت + سحابة حقل 5)."""
    by_date, add = _accumulator()
    add("2026-10-01", idx="ndvi", has_cog=True, scene_id="A", cloud_pct=70)
    add(
        "2026-10-01",
        idx="truecolor",
        has_cog=False,
        scene_id="B",
        acquisition_datetime="2026-10-01T10:00:00Z",
        aoi_cloud_pct=5,
    )
    rec = by_date["2026-10-01"]
    # الصورة المعروضة لليوم هي أصل A المُدَام ⇒ كلّ خصائص المشهد من A وحده.
    assert rec["scene_id"] == "A"
    assert rec["acquisition_datetime"] is None, "وقت B لا يُلصَق بمشهد A"
    assert rec["aoi_cloud_pct"] is None, "سحابة حقل B لا تُلصَق بمشهد A"
    assert rec["scene_cloud_pct"] == rec["cloud_pct"] == 70
    assert rec["clear_pct"] == 30 and rec["quality_label"] == "cloudy"
    # تجميعات اليوم (لا خصائص مشهد) تبقى اتّحاداً صادقاً.
    assert rec["has_cog"] is True and rec["indices"] == {"ndvi", "truecolor"}
    assert rec["contributors"] == 2


def test_t1_representative_is_lowest_valid_cloud_then_latest_time():
    by_date, add = _accumulator()
    add(
        "2026-10-02",
        has_cog=False,
        scene_id="no-cloud",
        acquisition_datetime="2026-10-02T09:00:00Z",
    )
    add(
        "2026-10-02",
        has_cog=False,
        scene_id="cloudy",
        cloud_pct=60,
        acquisition_datetime="2026-10-02T07:00:00Z",
    )
    add(
        "2026-10-02",
        has_cog=False,
        scene_id="clear-early",
        cloud_pct=10,
        acquisition_datetime="2026-10-02T07:10:00Z",
    )
    add(
        "2026-10-02",
        has_cog=False,
        scene_id="clear-late",
        cloud_pct=10,
        acquisition_datetime="2026-10-02T07:20:00Z",
    )
    rec = by_date["2026-10-02"]
    assert (rec["scene_id"], rec["acquisition_datetime"], rec["cloud_pct"]) == (
        "clear-late",
        "2026-10-02T07:20:00Z",
        10,
    )
    assert rec["contributors"] == 4


def test_t1_persisted_contributor_outranks_clearer_catalogue_item():
    """البطاقة تعرض الأصل المُدَام ⇒ مشهدُه هو الممثِّل ولو كان عنصر الكتالوج أصفى."""
    by_date, add = _accumulator()
    add(
        "2026-10-03",
        has_cog=False,
        scene_id="catalogue",
        cloud_pct=0,
        acquisition_datetime="2026-10-03T07:00:00Z",
    )
    add(
        "2026-10-03",
        has_cog=True,
        scene_id="persisted",
        cloud_pct=40,
        acquisition_datetime="2026-10-03T07:05:00Z",
    )
    rec = by_date["2026-10-03"]
    assert rec["scene_id"] == "persisted" and rec["cloud_pct"] == 40
    assert rec["acquisition_datetime"] == "2026-10-03T07:05:00Z"
    assert rec["has_cog"] is True


# ─── T4: اليوم = يوم UTC للطابع، لا أوّل 10 محارف ───────────────────────────────


def test_t4_accumulator_groups_offset_timestamp_on_its_utc_day():
    by_date, add = _accumulator()
    add(OFFSET_TS, has_cog=False, scene_id="S", acquisition_datetime=OFFSET_TS)
    assert list(by_date) == ["2026-09-30"]


def test_t4_accumulator_drops_unparseable_day_instead_of_slicing():
    by_date, add = _accumulator()
    add("2026-13-45T10:00:00Z", has_cog=False, scene_id="S")
    add("not-a-date", has_cog=False, scene_id="S")
    assert by_date == {}


@pytest.mark.parametrize(
    "value,expected",
    [
        (OFFSET_TS, date(2026, 9, 30)),
        ("2026-10-01T10:00:00Z", date(2026, 10, 1)),
        ("2026-10-01T10:00:00.123456789Z", date(2026, 10, 1)),
        ("2026-10-01", date(2026, 10, 1)),
        (date(2026, 10, 1), date(2026, 10, 1)),
        (datetime(2026, 10, 1, 0, 30, tzinfo=timezone(timedelta(hours=3))), date(2026, 9, 30)),
        ("2026-13-45", None),
        ("latest", None),
        ("", None),
        (None, None),
    ],
)
def test_t4_persisted_acquisition_date_is_the_utc_day(value, expected):
    """``insert_raster_asset`` و``fetch_latest_asset`` يشتركان في هذا التطبيع."""
    import db_persist
    from raster_available_dates import utc_day

    assert db_persist._iso_date_or_none(value) == expected
    # سلطة واحدة لمعنى «اليوم»: المُجمِّع ومسار القاعدة لا ينحرفان.
    assert utc_day(value) == (expected.isoformat() if expected else None)


def test_t4_route_groups_provider_offset_timestamp_on_utc_day(monkeypatch):
    from types import SimpleNamespace

    import db_persist
    from routers import fields

    async def authorize(field_id, *, hide_existence):
        return None

    async def stored(field_id, *, tenant_id, indices, limit):
        return []

    async def geometry(field_id, tenant_id):
        return {"type": "Polygon", "coordinates": [[[44, 15], [45, 15], [45, 16], [44, 15]]]}

    async def search(*args, **kwargs):
        return {"items": [{"datetime": OFFSET_TS, "cloud_cover_pct": 5, "item_id": "S"}]}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 16, tzinfo=UTC)

    monkeypatch.setattr(fields, "datetime", Clock)
    monkeypatch.setattr(fields, "_require_field_tenant", authorize)
    monkeypatch.setattr(fields, "_REQ_TENANT", SimpleNamespace(get=lambda: "t"))
    monkeypatch.setattr(fields, "_field_layers", {})
    monkeypatch.setattr(fields, "_stac_search", search)
    monkeypatch.setattr(fields, "_month_windows", lambda start, end: [(start, end)])
    monkeypatch.setattr(db_persist, "list_available_asset_dates", stored)
    monkeypatch.setattr(db_persist, "fetch_field_geometry", geometry)
    result = asyncio.run(
        fields.field_available_dates("F", index=None, limit=100, include_provider=True, months=1)
    )
    assert [d["date"] for d in result["dates"]] == ["2026-09-30"]
    assert result["dates"][0]["acquisition_datetime"] == OFFSET_TS


# ─── T3: تاريخ صريح غير صالح ⇒ 422 / لا أصل، لا «الأحدث» ───────────────────────


class _RecordingConn:
    def __init__(self):
        self.fetchrow_args = None

    async def execute(self, *_args):
        return None

    async def fetchrow(self, _sql, *args):
        self.fetchrow_args = args
        return {"cog_uri": "latest.tif", "acq": "2026-10-20"}

    async def close(self):
        return None


@pytest.mark.parametrize("bad", ["not-a-date", "2026-13-45", "2026-02-30"])
def test_t3_fetch_latest_asset_fails_closed_on_malformed_explicit_date(monkeypatch, bad):
    import db_persist

    conn = _RecordingConn()

    async def connect():
        return conn

    monkeypatch.setattr(db_persist, "_connect", connect)
    result = asyncio.run(db_persist.fetch_latest_asset("F", "ndvi", bad, tenant_id="t"))
    assert result is None, "تاريخ صريح غير صالح لا يصير «الأحدث»"
    assert conn.fetchrow_args is None, "لا استعلام بفلتر تاريخ NULL"


def test_t3_fetch_latest_asset_binds_utc_day_for_offset_timestamp(monkeypatch):
    import db_persist

    conn = _RecordingConn()

    async def connect():
        return conn

    monkeypatch.setattr(db_persist, "_connect", connect)
    asyncio.run(db_persist.fetch_latest_asset("F", "ndvi", OFFSET_TS, tenant_id="t"))
    assert conn.fetchrow_args[2] == date(2026, 9, 30)


@pytest.fixture
def cdse_tiles(monkeypatch):
    from routers import cdse_tiles as module

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(module, "_require_field", _noop)
    return module


@pytest.mark.parametrize("bad", ["not-a-date", "2026-13-45", "2026-02-30"])
def test_t3_persisted_thumbnail_rejects_malformed_date_with_422(monkeypatch, cdse_tiles, bad):
    calls = []

    async def fetch(*args, **kwargs):
        calls.append((args, kwargs))
        return {"cog_url": "latest.tif", "acquisition_date": "2026-10-20"}

    monkeypatch.setattr(cdse_tiles._db, "fetch_latest_asset", fetch)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            cdse_tiles.field_cdse_thumbnail(
                "F", index="ndvi", date=bad, size=160, source="persisted"
            )
        )
    assert exc.value.status_code == 422
    assert calls == [], "لا قراءة أصل لتاريخ مرفوض"


def test_t3_persisted_thumbnail_queries_the_utc_day(monkeypatch, cdse_tiles):
    seen = {}

    async def fetch(field_id, index_name, date=None, tenant_id=None):
        seen["date"] = date
        return None

    monkeypatch.setattr(cdse_tiles._db, "fetch_latest_asset", fetch)
    response = asyncio.run(
        cdse_tiles.field_cdse_thumbnail(
            "F", index="ndvi", date=OFFSET_TS, size=160, source="persisted"
        )
    )
    assert seen["date"] == "2026-09-30"
    assert response.status_code == 404


@pytest.mark.parametrize("value", ["latest", "today", ""])
def test_t3_latest_aliases_still_select_latest(monkeypatch, cdse_tiles, value):
    seen = {}

    async def fetch(field_id, index_name, date=None, tenant_id=None):
        seen["date"] = date
        return None

    monkeypatch.setattr(cdse_tiles._db, "fetch_latest_asset", fetch)
    asyncio.run(
        cdse_tiles.field_cdse_thumbnail("F", index="ndvi", date=value, size=160, source="persisted")
    )
    assert seen["date"] is None


# ─── مراجعة الإصلاح (must_fix): لا انحدار في نَسَب المشهد الواحد ولا انشقاق اليوم ─────


def test_t1_same_scene_contributors_merge_instead_of_dropping_aoi_and_time():
    """الطبقة في الذاكرة وصفّ القاعدة للأصل **نفسه** مشهدٌ واحد: يُكمِل أحدُهما الآخر.

    شاهد المراجعة: كان التعادل (أو مقارنة سحابة AOI بسحابة مشهد) يُبقي الطبقة في الذاكرة
    (بلا AOI ولا وقت) فيسقط سحابة الحقل 40 ووقت STAC ويرتفع الوسم إلى «high».
    """
    memory = dict(has_cog=True, idx="ndvi", cloud_pct=10, scene_id="S")
    stored = dict(
        has_cog=True,
        idx="ndvi",
        cloud_pct=10,
        aoi_cloud_pct=40,
        scene_id="S",
        acquisition_datetime="2026-10-15T07:30:00Z",
    )
    for contributors in ((memory, stored), (stored, memory)):
        by_date, add = _accumulator()
        for kwargs in contributors:
            add("2026-10-15", **kwargs)
        rec = by_date["2026-10-15"]
        assert (
            rec["scene_id"],
            rec["scene_cloud_pct"],
            rec["aoi_cloud_pct"],
            rec["clear_pct"],
            rec["quality_label"],
            rec["acquisition_datetime"],
        ) == ("S", 10, 40, 60, "medium", "2026-10-15T07:30:00Z")
        assert rec["contributors"] == 2


def test_t1_merged_scene_is_reranked_against_other_scenes():
    """دمج مشهد يرفع سحابة حقله ⇒ يُعاد ترتيبه؛ لا يبقى ممثِّلاً بقيمة أبطلها مشهده نفسه."""
    by_date, add = _accumulator()
    add("2026-10-16", has_cog=False, scene_id="S", cloud_pct=10)
    add("2026-10-16", has_cog=False, scene_id="T", cloud_pct=20)
    add(
        "2026-10-16",
        has_cog=False,
        scene_id="S",
        aoi_cloud_pct=40,
        acquisition_datetime="2026-10-16T07:30:00Z",
    )
    rec = by_date["2026-10-16"]
    assert (rec["scene_id"], rec["clear_pct"], rec["acquisition_datetime"]) == ("T", 80, None)
    assert rec["contributors"] == 3


def test_t1_tie_goes_to_the_contributor_with_more_provenance():
    by_date, add = _accumulator()
    add("2026-10-17", has_cog=True, cloud_pct=30)
    add("2026-10-17", has_cog=True, cloud_pct=30, aoi_cloud_pct=30, scene_id="S")
    rec = by_date["2026-10-17"]
    assert (rec["scene_id"], rec["aoi_cloud_pct"]) == ("S", 30)


def test_t1_route_merges_memory_layer_with_db_row_of_the_same_scene(monkeypatch):
    from types import SimpleNamespace

    import db_persist
    from routers import fields

    async def authorize(field_id, *, hide_existence):
        return None

    async def stored(field_id, *, tenant_id, indices, limit):
        return [
            {
                "date": "2026-10-15",
                "index_name": "ndvi",
                "cloud_pct": 10,
                "aoi_cloud_pct": 40,
                "scene_id": "S",
                "acquisition_datetime": "2026-10-15T07:30:00Z",
                "has_cog": True,
            }
        ]

    layers = {
        "mem": {
            "cog_url": "file:///mem.tif",
            "index": "ndvi",
            "acquisition_date": "2026-10-15",
            "cloud_pct": 10,
            "provenance": {"scene_id": "S"},
        }
    }
    monkeypatch.setattr(fields, "_require_field_tenant", authorize)
    monkeypatch.setattr(fields, "_REQ_TENANT", SimpleNamespace(get=lambda: "t"))
    monkeypatch.setattr(fields, "_layers", layers)
    monkeypatch.setattr(fields, "_field_layers", {"F": ["mem"]})
    monkeypatch.setattr(db_persist, "list_available_asset_dates", stored)
    result = asyncio.run(
        fields.field_available_dates("F", index="ndvi", limit=100, include_provider=False, months=1)
    )
    (day,) = result["dates"]
    assert (day["aoi_cloud_pct"], day["quality_label"], day["acquisition_datetime"]) == (
        40,
        "medium",
        "2026-10-15T07:30:00Z",
    )
    assert day["scene_id"] == "S" and day["contributors"] == 2


def test_t4_in_memory_layer_lookup_matches_the_listed_utc_day():
    """اليوم المعروض في available-dates يجب أن يجد الطبقة في الذاكرة نفسها (بلا قاعدة)."""
    from layer_lookup import find_field_layer

    layers = {"L": {"cog_url": "file:///l.tif", "index": "ndvi", "acquisition_date": OFFSET_TS}}
    field_layers = {"F": ["L"]}
    by_date, add = _accumulator()
    add(layers["L"]["acquisition_date"], idx="ndvi", has_cog=True)
    (listed,) = list(by_date)
    assert find_field_layer(layers, field_layers, "F", "ndvi", listed) is layers["L"]
    assert find_field_layer(layers, field_layers, "F", "ndvi", "2026-10-01") is None
    assert find_field_layer(layers, field_layers, "F", "ndvi", "not-a-date") is None


def test_t4_registry_product_date_is_the_same_utc_day_as_the_asset(monkeypatch):
    import db_persist

    seen = []

    class Conn:
        async def execute(self, *_args):
            return None

        async def fetchrow(self, _sql, *args):
            seen.append(args)
            return {"id": "r", "bbox": None, "bands": "{}", "metadata": "{}"}

        async def close(self):
            return None

    async def connect():
        return Conn()

    monkeypatch.setattr(db_persist, "_connect", connect)
    kwargs = dict(
        tenant_id="00000000-0000-4000-8000-000000000001",
        field_id="F",
        scene_id="S",
        index_type="ndvi",
        cog_url="https://cdn.example/x.tif",
        cloud_pct=None,
        quality_score=None,
    )
    assert asyncio.run(db_persist.insert_raster_registry_entry(product_date=OFFSET_TS, **kwargs))
    # raster_assets.acquisition_date و raster_registry.product_date يومٌ واحد للأصل نفسه.
    assert seen[-1][3] == db_persist._iso_date_or_none(OFFSET_TS).isoformat() == "2026-09-30"
    seen.clear()
    assert not asyncio.run(
        db_persist.insert_raster_registry_entry(product_date="2026-13-45", **kwargs)
    )
    assert seen == [], "تاريخ منتَج غير صالح لا يُكتب مقصوصاً"
