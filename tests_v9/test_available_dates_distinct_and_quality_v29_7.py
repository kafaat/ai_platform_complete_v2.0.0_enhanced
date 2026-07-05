"""حارس انحدار: available-dates تحدّ بالتواريخ المميَّزة، والاختيار واعٍ بالجودة.

ثلاثة عيوب من تدقيق الأقمار (v3 + v4) تُغطّى هنا:

- **v3-Finding-1:** ``list_available_asset_dates`` كان ``GROUP BY acquisition_date,
  index_name … LIMIT`` — فالحدّ يقع على صفوف (تاريخ×مؤشّر). مع N مؤشّرات تعود فقط
  ~limit/N تاريخاً مميَّزاً ⇒ بتر خطّ السنتين. الإصلاح: CTE يحدّ التواريخ المميَّزة أوّلاً.
- **v3-Finding-4:** ``MIN(cloud_pct)`` و``MIN(scene_id)`` كتجميعتَين مستقلّتَين تخلطان
  بيانات وصفيّة من صفَّين مختلفَين. الإصلاح: ``DISTINCT ON`` ينتقي صفّاً واحداً متماسكاً.
- **v3-Finding-3:** ``fetch_latest_asset`` تجاهل أعمدة الجودة. الإصلاح: ترتيب بالجودة
  بعد التاريخ (أحدث تاريخ يفوز، ثمّ الأفضل جودةً لذلك اليوم).
- **v4-audit:** ``insert_raster_asset`` لم يكتب أعمدة v105 (quality_score/aoi_cloud_pct/
  cloud_mask_sources) فكان ترتيب الجودة بلا أثر (NULL). الإصلاح: تُكتب من stats الآن.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
DB_PERSIST = REPO / "services" / "raster-service" / "db_persist.py"
RASTER_MAIN = REPO / "services" / "raster-service" / "main.py"


def _fn_body(src: str, marker: str, span: int = 1800) -> str:
    idx = src.find(marker)
    assert idx != -1, f"لم يُعثَر على {marker!r}"
    return src[idx : idx + span]


# ─── v3-Finding-1 + v3-Finding-4: available-dates ─────────────────────────────


def test_available_dates_limits_distinct_dates_not_rows() -> None:
    """الحدّ يُطبَّق على التواريخ المميَّزة عبر CTE، لا على صفوف (تاريخ×مؤشّر)."""
    body = _fn_body(DB_PERSIST.read_text(encoding="utf-8"), "def list_available_asset_dates")
    assert "WITH recent_dates AS" in body, "يجب CTE يختار التواريخ المميَّزة أوّلاً"
    assert "SELECT DISTINCT acquisition_date" in body, "التواريخ المميَّزة تُحدّ قبل الربط"
    # الحدّ ($4) يقع داخل الـCTE على التواريخ لا على GROUP BY للصفوف.
    cte = body[body.find("WITH recent_dates") : body.find(")", body.find("LIMIT $4")) + 1]
    assert "LIMIT $4" in cte, "الحدّ يجب أن يكون داخل CTE التواريخ المميَّزة"


def test_available_dates_picks_coherent_row_not_mixed_aggregates() -> None:
    """DISTINCT ON ينتقي صفّاً واحداً؛ لا خلط MIN(scene_id) مع MIN(cloud_pct)."""
    body = _fn_body(
        DB_PERSIST.read_text(encoding="utf-8"), "def list_available_asset_dates", span=2800
    )
    assert "DISTINCT ON (a.acquisition_date, a.index_name)" in body, (
        "يجب DISTINCT ON لصفّ متماسك لكلّ (تاريخ، مؤشّر)"
    )
    # نفحص نصّ SQL فقط (لا التعليقات التوضيحيّة التي قد تذكر النمط القديم).
    sql = body[body.find('sql = """') : body.find('"""', body.find('sql = """') + 9)]
    assert "MIN(scene_id)" not in sql, "MIN(scene_id) يخلط بيانات من صفوف مختلفة"
    assert "MIN(cloud_pct)" not in sql, "MIN(cloud_pct) يخلط بيانات من صفوف مختلفة"
    # has_cog محفوظ: نفضّل صفّاً يملك COG ثمّ الأفضل جودةً.
    assert "cog_uri IS NOT NULL AND a.cog_uri <> '') DESC" in body, (
        "يجب تفضيل صفّ يملك COG كي يبقى has_cog صحيحاً"
    )


# ─── v3-Finding-3: fetch_latest_asset quality-aware ordering ──────────────────


def test_fetch_latest_asset_is_quality_aware() -> None:
    """أحدث تاريخ يفوز أوّلاً، ثمّ quality_score DESC ثمّ cloud_pct ASC."""
    body = _fn_body(DB_PERSIST.read_text(encoding="utf-8"), "def fetch_latest_asset", span=2400)
    order = body[body.find("ORDER BY") : body.find("LIMIT 1")]
    assert "acquisition_date DESC" in order, "دلالة latest: أحدث تاريخ أوّلاً"
    assert "quality_score DESC" in order, "بعد التاريخ: الأفضل جودةً"
    assert "cloud_pct ASC" in order, "ثمّ الأقلّ غيوماً"
    # التاريخ يسبق الجودة (لا نكسر دلالة latest).
    assert order.find("acquisition_date DESC") < order.find("quality_score DESC")


# ─── v4-audit: insert populates v105 quality columns ──────────────────────────


def test_insert_writes_v105_quality_columns() -> None:
    """INSERT يكتب quality_score/aoi_cloud_pct/cloud_mask_sources (كانت تُهمَل)."""
    body = _fn_body(DB_PERSIST.read_text(encoding="utf-8"), "def insert_raster_asset", span=3200)
    for col in ("quality_score", "aoi_cloud_pct", "cloud_mask_sources"):
        assert col in body, f"عمود v105 {col} غائب عن INSERT — ترتيب الجودة يصبح بلا أثر"
    # التوقيع يقبل القيم الجديدة.
    import importlib.util
    import sys
    import types

    if "asyncpg" not in sys.modules:
        sys.modules["asyncpg"] = types.ModuleType("asyncpg")
    spec = importlib.util.spec_from_file_location("raster_db_persist_q", DB_PERSIST)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    params = inspect.signature(mod.insert_raster_asset).parameters
    for p in ("quality_score", "aoi_cloud_pct", "cloud_mask_sources"):
        assert p in params, f"insert_raster_asset يفتقد المعامل {p}"


def test_caller_passes_quality_values_from_stats() -> None:
    """المُستدعي في main.py يمرّر confidence/cloud_pct/cloud_mask_sources فعلاً."""
    src = " ".join(RASTER_MAIN.read_text(encoding="utf-8").split())
    assert 'quality_score=stats.get("confidence")' in src, "quality_score لا يُمرَّر من stats"
    assert 'aoi_cloud_pct=stats.get("cloud_pct")' in src, "aoi_cloud_pct لا يُمرَّر من stats"
    assert 'cloud_mask_sources=stats.get("cloud_mask_sources")' in src, (
        "cloud_mask_sources لا يُمرَّر من stats"
    )
    # النَّسَب (provenance) يحفظ cloud_mask_sources أيضاً (كان يُنتَج ويُسقَط).
    assert '"cloud_mask_sources",' in src, "provenance لا يحفظ cloud_mask_sources"
