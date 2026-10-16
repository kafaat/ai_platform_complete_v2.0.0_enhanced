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

import ast
import inspect
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
DB_PERSIST = REPO / "services" / "raster-service" / "db_persist.py"
RASTER_MAIN = REPO / "services" / "raster-service" / "main.py"
# التفكيك (phase-4): مسار الحفظ ومُستدعي insert_raster_asset انتقلا من main.py
# إلى raster_asset_persistence.py (main يعيد تصديرها فقط). نقرأ الوحدتَين معاً.
RASTER_PERSIST = REPO / "services" / "raster-service" / "raster_asset_persistence.py"


@pytest.fixture
def isolated_raster_imports():
    """Restore service import scope after running the actual persistence adapter."""
    previous = dict(sys.modules)
    yield
    raster_root = str(RASTER_PERSIST.parent) + "/"
    for name, module in tuple(sys.modules.items()):
        if name not in previous and str(getattr(module, "__file__", "")).startswith(raster_root):
            sys.modules.pop(name, None)


def _fn_body(src: str, marker: str) -> str:
    name = marker.removeprefix("def ")
    node = next(
        (
            node
            for node in ast.walk(ast.parse(src))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ),
        None,
    )
    assert node is not None, f"لم يُعثَر على {marker!r}"
    body = ast.get_source_segment(src, node)
    assert body is not None
    return body


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
    body = _fn_body(DB_PERSIST.read_text(encoding="utf-8"), "def list_available_asset_dates")
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
    body = _fn_body(DB_PERSIST.read_text(encoding="utf-8"), "def fetch_latest_asset")
    order = body[body.find("ORDER BY") : body.find("LIMIT 1")]
    assert "acquisition_date DESC" in order, "دلالة latest: أحدث تاريخ أوّلاً"
    assert "quality_score DESC" in order, "بعد التاريخ: الأفضل جودةً"
    assert "cloud_pct ASC" in order, "ثمّ الأقلّ غيوماً"
    # التاريخ يسبق الجودة (لا نكسر دلالة latest).
    assert order.find("acquisition_date DESC") < order.find("quality_score DESC")


# ─── v4-audit: insert populates v105 quality columns ──────────────────────────


def test_insert_writes_v105_quality_columns() -> None:
    """INSERT يكتب quality_score/aoi_cloud_pct/cloud_mask_sources (كانت تُهمَل)."""
    body = _fn_body(DB_PERSIST.read_text(encoding="utf-8"), "def insert_raster_asset")
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


@pytest.mark.parametrize("quality", [None, 0.0, 0.87])
def test_caller_passes_quality_values_from_stats(
    monkeypatch, isolated_raster_imports, quality
) -> None:
    """Actual persistence prefers measured QA, retaining legacy confidence fallback."""
    from types import SimpleNamespace

    monkeypatch.syspath_prepend(str(RASTER_PERSIST.parent))
    import db_persist
    from raster_asset_persistence import persist_raster_asset

    captured = {}

    async def insert(**kwargs):
        captured["asset"] = kwargs
        return True

    async def registry(**kwargs):
        captured["registry"] = kwargs
        return True

    monkeypatch.setattr(db_persist, "insert_raster_asset", insert)
    monkeypatch.setattr(db_persist, "insert_raster_registry_entry", registry)
    req = SimpleNamespace(
        field_id="fld_quality",
        tenant_id="00000000-0000-4000-8000-000000000001",
        scene_id="scene-quality",
        capture_datetime="2026-10-01T07:30:00Z",
        source_format=SimpleNamespace(value="sentinel2_l2a"),
        indicator=SimpleNamespace(value="ndvi"),
        bands=None,
    )
    stats = {
        "confidence": 0.25,
        "cloud_pct": 7.0,
        "cloud_mask_sources": ["scl"],
        "valid_pixels": 93,
        "nodata_pixels": 7,
    }
    if quality is not None:
        stats["quality_score"] = quality
    assert persist_raster_asset(
        req, "https://example.invalid/quality.tif", {}, [44, 15, 44.1, 15.1], stats
    )
    expected = quality if quality is not None else stats["confidence"]
    assert captured["asset"]["quality_score"] == expected
    assert captured["registry"]["quality_score"] == expected
    assert captured["asset"]["aoi_cloud_pct"] == stats["cloud_pct"]
    assert captured["asset"]["cloud_mask_sources"] == stats["cloud_mask_sources"]
    assert captured["asset"]["provenance"]["stats"]["cloud_mask_sources"] == ["scl"]
