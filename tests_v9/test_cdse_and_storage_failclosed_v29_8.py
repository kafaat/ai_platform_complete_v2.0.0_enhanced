"""حارس: بلاطات CDSE ومخزن الكائنات يفشلان مُغلَقَين ولا يخدمان سياقاً خاطئاً.

من تدقيق الأقمار (v3):
- Finding-6: مفتاح كاش CDSE يجب أن يعزل المستأجرين ويتبدّل مع هندسة الحقل.
- Finding-7: لا bbox احتياطيّ ثابت (كان يمن) — fail-closed حين لا bbox.
- Finding-8: روابط بلاطات cdse-tilejson تحمل tid (وإلّا تُرفَض <img> بلا مستأجِر) + urlencode.
- Finding-9: رفع S3 المُهيّأ الفاشل يرفع استثناءً (لا file:// صامت غير قابل للخدمة).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
RASTER = REPO / "services" / "raster-service"
CDSE_TILES = RASTER / "routers" / "cdse_tiles.py"
# CDSE tile logic (cache-key, fail-closed bbox) was extracted from the thin router
# into raster_cdse_tile_runtime.py (phase16); source guards read both.
CDSE_RUNTIME = RASTER / "raster_cdse_tile_runtime.py"
FIELDS = RASTER / "routers" / "fields.py"
OBJECT_STORE = RASTER / "object_store.py"


def _cdse_src() -> str:
    """Combined router + extracted-runtime source for CDSE tile guards."""
    return CDSE_TILES.read_text(encoding="utf-8") + "\n" + CDSE_RUNTIME.read_text(encoding="utf-8")


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
    # مفتاح الكاش قد يمتدّ عبر أسطر (سلسلة scene-bound مقابل request-bound)، فالمطابقة
    # تُجرى على كتلة الإسناد كاملة لا سطراً واحداً هشّاً.
    src = _cdse_src()
    blocks = []
    idx = 0
    while True:
        pos = src.find("cache_key = ", idx)
        if pos == -1:
            break
        end = src.index("\n\n", pos) if "\n\n" in src[pos:] else pos + 400
        blocks.append(src[pos : min(end, pos + 400)])
        idx = pos + 1
    assert blocks, "لا يوجد إسناد cache_key في المصدر"
    for block in blocks:
        assert "{tenant}" in block, "مفتاح الكاش لا يعزل المستأجر — تصادم عبر المستأجرين"
        assert "{geom_sig}" in block, "مفتاح الكاش لا يتبدّل مع هندسة الحقل — تسريب COG قديم"


def test_cdse_has_no_hardcoded_yemen_bbox_fallback() -> None:
    src = _cdse_src()
    assert "[44.9, 16.0, 45.1, 16.1]" not in src, "bbox يمن ثابت عاد — يجب fail-closed"
    # fail-closed صريح حين لا bbox.
    assert "if not field_bbox:" in src, "يجب fail-closed حين غياب bbox الحقل"


# ─── v3-Finding-8: cdse-tilejson tiles carry tid + urlencode ──────────────────


def test_cdse_tilejson_propagates_tid_and_urlencodes() -> None:
    src = CDSE_TILES.read_text(encoding="utf-8")
    idx = src.find("async def field_cdse_tilejson")
    # نقصّ حتّى مطلع الدالّة التالية (لا نافذة ثابتة هشّة تنكسر عند إضافة توثيق/منطق).
    nxt = src.find("\n@router", idx + 1)
    body = src[idx : nxt if nxt != -1 else idx + 3000]
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


def test_upload_cog_fails_closed_when_s3_configured_and_upload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load(OBJECT_STORE, "raster_object_store")
    # بلا S3 (افتراضيّ): file:// مشروع.
    assert mod.upload_cog("/tmp/x.tif", "k").startswith("file://")

    # لا تكفِي محاكاة enabled() فقط: عنوانٌ فارغٌ ليس تكوين S3 صالحاً.
    # جهّز عنوان HTTPS ومفاتيح اصطناعيّة، واحقن فشل نقل دون شبكة أو boto3 حقيقيّ.
    for name, value in {
        "S3_BUCKET": "rasters",
        "S3_ENDPOINT": "https://objects.example.test",
        "S3_USE_SSL": "true",
        "S3_ACCESS_KEY": "synthetic-access-key",
        "S3_SECRET_KEY": "synthetic-secret-key",
    }.items():
        monkeypatch.setattr(mod, name, value)

    class BrokenClient:
        def head_bucket(self, **kwargs):
            return None

        def upload_file(self, *args, **kwargs):
            raise OSError("synthetic_s3_write_failure")

    boto3 = ModuleType("boto3")
    boto3.client = lambda *args, **kwargs: BrokenClient()  # type: ignore[attr-defined]
    botocore = ModuleType("botocore")
    botocore_client = ModuleType("botocore.client")

    class FakeConfig:
        def __init__(self, **kwargs):
            self.options = kwargs

    botocore_client.Config = FakeConfig  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    monkeypatch.setitem(sys.modules, "botocore", botocore)
    monkeypatch.setitem(sys.modules, "botocore.client", botocore_client)

    # S3 مُهيّأة ورفض الوسيط للرفع + fallback مُطفأ ⇒ فشل ظاهر دون file://.
    monkeypatch.setattr(mod, "S3_ALLOW_FILE_FALLBACK", "false")
    with pytest.raises(mod.ObjectStoreUploadError, match="synthetic_s3_write_failure"):
        mod.upload_cog("/tmp/x.tif", "k")

    # وضع التطوير الصريح وحده يُجيز الرجوع لـfile:// عند فشل الرفع، لا عند فساد الإعداد.
    monkeypatch.setattr(mod, "S3_ALLOW_FILE_FALLBACK", "true")
    assert mod.upload_cog("/tmp/x.tif", "k").startswith("file://")
