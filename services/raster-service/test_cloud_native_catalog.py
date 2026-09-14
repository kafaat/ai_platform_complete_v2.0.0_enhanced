import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SERVICE = Path(__file__).resolve().parent
if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))

import cloud_native_catalog as cnc  # noqa: E402


def test_stac_landing_links_search_and_collections():
    landing = cnc.stac_landing_page("https://tiles.sahool.test")
    rels = {link["rel"] for link in landing["links"]}
    assert {"self", "search", "data"}.issubset(rels)
    assert landing["stac_version"] == "1.0.0"


def test_stac_collections_include_source_and_derived_products():
    cols = cnc.stac_collections()["collections"]
    ids = {c["id"] for c in cols}
    assert "sentinel-2-l2a" in ids
    assert "field-cog-products" in ids


def test_cog_registry_preview_scores_quality_without_advertising_a_tile_path():
    """تغييرُ عقدٍ مقصود: المعاينةُ لا تُصدِر قالبَ بلاطاتٍ لا يُخدَم.

    كان التأكيدُ السابق يشترط البادئة `/tiles/WebMercatorQuad/` — أي **شكلَ TiTiler
    المباشر حاملاً `cog_url` في الاستعلام**. وذلك المسارُ غيرُ موجَّهٍ في البوّابة،
    والسجلُّ المُعايَن بلا هويّةٍ بعد، فلا مسارَ بلاطاتٍ مُصادَقاً عليه له.
    """
    rec = cnc.cog_registry_record(
        tenant_id="tenant",
        field_id="field",
        date="2026-06-26",
        index_type="ndvi",
        cog_url="https://example.com/ndvi.tif",
        cloud_pct=6,
    )
    assert rec["quality"]["accepted"] is True
    assert rec["index_type"] == "ndvi"
    assert rec["tilejson_url"] is None
    assert rec["tilejson_unavailable_reason"] == "preview_record_has_no_registry_identity"
    # ولا يُعاد شكلُ TiTiler المباشر في أيّ حقلٍ من المعاينة.
    assert "WebMercatorQuad" not in json.dumps(rec)
