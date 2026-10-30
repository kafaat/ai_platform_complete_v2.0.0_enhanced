import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# توحيد main↔cert: المسارات فُكِّكت من main.py إلى routers/؛ نمسح المصدر المُجمَّع
# (main.py + كلّ routers/*.py) كي تبقى تأكيدات كود المعالِجات صحيحة بعد التفكيك — لا إضعاف.
MAIN = (
    (ROOT / "main.py").read_text(encoding="utf-8")
    + "\n"
    + "\n".join(
        Path(p).read_text(encoding="utf-8")
        for p in sorted(glob.glob(str(ROOT / "routers" / "*.py")))
    )
    + "\n"
    + "\n".join(
        Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "raster_*.py")))
    )
)
CDSE = (ROOT / "cdse_client.py").read_text(encoding="utf-8")
TILE = (ROOT / "tile_render.py").read_text(encoding="utf-8")


def test_cdse_explicit_bare_date_is_full_day_not_zero_length():
    assert 'time_to = f"{to_day}T23:59:59Z"' in MAIN
    assert 'capture_datetime = f"{to_day}T12:00:00Z"' in MAIN
    assert "00:00→00:00 interval" in MAIN


def test_cdse_bbox_and_geometry_are_validated_before_provider_calls():
    assert "def _validate_bbox_4326" in CDSE
    assert "bbox = _validate_bbox_4326(bbox)" in CDSE
    assert "def _geometry_object" in CDSE
    assert 'payload["intersects"] = geom' in CDSE


def test_raster_callers_declare_shared_nodata():
    # Writer pixel/mask semantics are exercised by test_cog_finite_nodata_runtime.py.
    assert "nodata=RASTER_NODATA" in MAIN
    assert '"nodata": RASTER_NODATA' in MAIN


def test_tilejson_returns_resolved_date_and_cache_version():
    assert "resolved_date =" in MAIN
    assert "resolved_version =" in MAIN
    assert '"resolved_date": resolved_date' in MAIN
    assert '"cache_version": resolved_version' in MAIN


def test_transparent_tiles_are_not_browser_cached_as_valid_data():
    assert '"Cache-Control": "no-store, max-age=0"' in MAIN
    assert '"X-Sahool-Tile-Cache": "transparent"' in MAIN
