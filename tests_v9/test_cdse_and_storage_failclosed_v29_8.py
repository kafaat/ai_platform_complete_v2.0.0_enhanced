"""حارس: بلاطات CDSE ومخزن الكائنات يفشلان مُغلَقَين ولا يخدمان سياقاً خاطئاً.

من تدقيق الأقمار (v3):
- Finding-6: مفتاح كاش CDSE يجب أن يعزل المستأجرين ويتبدّل مع هندسة الحقل.
- Finding-7: لا bbox احتياطيّ ثابت (كان يمن) — fail-closed حين لا bbox.
- Finding-8: روابط بلاطات cdse-tilejson تحمل tid (وإلّا تُرفَض <img> بلا مستأجِر) + urlencode.
- Finding-9: رفع S3 المُهيّأ الفاشل يرفع استثناءً (لا file:// صامت غير قابل للخدمة).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
RASTER = REPO / "services" / "raster-service"
CDSE_TILES = RASTER / "routers" / "cdse_tiles.py"
FIELDS = RASTER / "routers" / "fields.py"
OBJECT_STORE = RASTER / "object_store.py"


def _load(path: Path, name: str):
    # object_store لا يستورد boto3 عند التحميل (الاستيراد كسول داخل upload_cog)، فلا
    # نلوّث sys.modules بكعب boto3 (كان يكسر اختبارات لاحقة تعتمد boto3 الحقيقيّ).
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# ─── v3-Finding-6/7: CDSE cache key + fail-closed bbox (source scan) ───────────


def test_cdse_cache_key_isolates_tenant_and_geometry() -> None:
    src = CDSE_TILES.read_text(encoding="utf-8")
    key_line = next(ln for ln in src.splitlines() if 'cache_key = f"' in ln)
    assert "{tenant}" in key_line, "مفتاح الكاش لا يعزل المستأجر — تصادم عبر المستأجرين"
    assert "{geom_sig}" in key_line, "مفتاح الكاش لا يتبدّل مع هندسة الحقل — تسريب COG قديم"


def test_cdse_has_no_hardcoded_yemen_bbox_fallback() -> None:
    src = CDSE_TILES.read_text(encoding="utf-8")
    assert "[44.9, 16.0, 45.1, 16.1]" not in src, "bbox يمن ثابت عاد — يجب fail-closed"
    # fail-closed صريح حين لا bbox.
    assert "if not field_bbox:" in src, "يجب fail-closed حين غياب bbox الحقل"


# ─── v3-Finding-8: cdse-tilejson tiles carry tid + urlencode ──────────────────


def test_cdse_tilejson_propagates_tid_and_urlencodes() -> None:
    src = CDSE_TILES.read_text(encoding="utf-8")
    idx = src.find("async def field_cdse_tilejson")
    body = src[idx : idx + 1600]
    assert "urlencode(" in body, "روابط البلاطة يجب أن تُرمَّز بـurlencode لا تسلسل يدويّ"
    assert 'tile_params["tid"]' in body, "رابط البلاطة يجب أن يحمل tid وإلّا تُرفَض <img>"
    assert 'f"index={index}"' not in body, "بقي التسلسل اليدويّ للسلسلة — استبدله urlencode"


def test_field_tilejson_urlencodes_version_token() -> None:
    src = FIELDS.read_text(encoding="utf-8")
    idx = src.find("self_tiles = f")
    body = src[max(0, idx - 700) : idx]
    assert "urlencode(" in body, "field_tilejson يجب أن يُرمِّز qs (v قد يُشتقّ من cog_url)"
    assert "qs_parts = [" not in body, "بقي بناء qs اليدويّ — استبدله urlencode"


# ─── v3-Finding-9: object_store fail-closed on configured-S3 upload failure ────


def test_upload_cog_fails_closed_when_s3_configured_and_upload_fails() -> None:
    mod = _load(OBJECT_STORE, "raster_object_store")
    # بلا S3 (افتراضيّ): file:// مشروع.
    assert mod.upload_cog("/tmp/x.tif", "k").startswith("file://")

    # S3 مُهيّأة والرفع يفشل + fallback مُطفأ ⇒ يرفع ObjectStoreUploadError (لا file://).
    mod.enabled = lambda: True  # type: ignore[assignment]
    mod._allow_file_fallback = lambda: False  # type: ignore[assignment]
    with pytest.raises(mod.ObjectStoreUploadError):
        mod.upload_cog("/tmp/x.tif", "k")

    # S3_ALLOW_FILE_FALLBACK=1 (تطوير) ⇒ يتدهور إلى file:// بتحذير.
    mod._allow_file_fallback = lambda: True  # type: ignore[assignment]
    assert mod.upload_cog("/tmp/x.tif", "k").startswith("file://")
