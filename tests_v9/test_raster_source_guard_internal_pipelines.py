"""حارس مصدر الراستر ↔ خطوط الأنابيب الداخليّة (backfill / process-from-stac / CDSE).

السبب (بلاغ تشغيل 2026-07-04): كلّ مهامّ الاستكمال التاريخيّ فشلت بـ
«job backfill_x failed: HTTPException» مباشرةً بعد «بُني VRT من 13 نطاق». الجذر:
``_safe_raster_source`` كان يقبل ``file://`` وhttp(s) فقط، بينما الأنابيب الداخليّة
تمرّر مخرجاتها كمسار محلّيّ **خام**:
  • backfill/process-from-stac: VRT كان يُكتب في /tmp (خارج UPLOAD_DIR أصلاً)؛
  • CDSE: GeoTIFF تحت UPLOAD_DIR لكن بلا بادئة file://.
فتُرمى 400 «مخطّط URL غير مدعوم» وتُبتلع في معالج فشل المهمّة.

العقد المُثبَّت هنا (لا اتّساع أمنيّاً):
  ١) المسار المحلّيّ المطلق يُقبَل **فقط** تحت UPLOAD_DIR — نفس احتواء file://
     (traversal وملفّات النظام تُرفَض كما كانت، وسياسة http(s)/SSRF لم تتغيّر).
  ٢) بوّابتا بناء الـVRT في routers/fields.py تكتبان بـ``out_dir=main.UPLOAD_DIR``
     (وإلّا عاد الفشل حتى مع قبول المسار الخام).
  ٣) CDSE يكتب GeoTIFF المؤشّر تحت UPLOAD_DIR (يبقى داخل المجلّد المسموح).
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]  # CI يشغّل -m unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
RASTER = os.path.join(ROOT, "services/raster-service")

# يتطلّب fastapi — في بيئة CI الخفيفة قد يغيب؛ نتخطّى بصدق إن غاب (نمط authz).
_fastapi = importlib.util.find_spec("fastapi") is not None


@pytest.fixture
def rm():
    """يستورد raster-service/main.py باسم فريد (عزل تصادم أسماء عبر الخدمات)."""
    if not _fastapi:
        pytest.skip("fastapi غير متاح في هذه البيئة — يُنفَّذ في وظيفة الوحدات الكاملة")
    if RASTER not in sys.path:
        sys.path.insert(0, RASTER)
    spec = importlib.util.spec_from_file_location(
        "sahool_raster_main_for_source_guard_tests",
        os.path.join(RASTER, "main.py"),
    )
    assert spec is not None and spec.loader is not None
    raster_main = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = raster_main
    spec.loader.exec_module(raster_main)
    assert hasattr(raster_main, "_safe_raster_source"), "استُورد main خاطئ — ليس raster-service"
    try:
        yield raster_main
    finally:
        sys.modules.pop(spec.name, None)


def test_bare_local_path_under_upload_dir_is_accepted(rm):
    """جوهر انحدار backfill: مسار خام تحت UPLOAD_DIR (VRT/CDSE tif) يُقبَل."""
    from fastapi import HTTPException

    vrt = os.path.join(rm.UPLOAD_DIR, "stac_stack_guard.vrt")
    tif = os.path.join(rm.UPLOAD_DIR, "cdse_ndvi_guard.tif")
    assert rm._safe_raster_source(vrt) == os.path.realpath(vrt)
    assert rm._safe_raster_source(tif) == os.path.realpath(tif)
    # file:// يبقى مقبولاً كما كان (نفس الاحتواء).
    assert rm._safe_raster_source(f"file://{vrt}") == os.path.realpath(vrt)
    # خارج UPLOAD_DIR — مرفوض للمسارَين الخام وfile:// (لا اتّساع أمنيّاً).
    for bad in ("/etc/passwd", "file:///etc/passwd", os.path.join(rm.UPLOAD_DIR, "..", "evil.tif")):
        with pytest.raises(HTTPException) as ei:
            rm._safe_raster_source(bad)
        assert ei.value.status_code == 400


def test_remote_source_policy_unchanged(rm):
    """سياسة المصادر البعيدة لم تتغيّر: http(s) مقبول، metadata محجوب، غيره 400."""
    from fastapi import HTTPException

    url = "https://example.com/scene/red.tif"
    assert rm._safe_raster_source(url) == url
    with pytest.raises(HTTPException):
        rm._safe_raster_source("http://169.254.169.254/latest/meta-data")
    with pytest.raises(HTTPException):
        rm._safe_raster_source("s3://bucket/key.tif")
    with pytest.raises(HTTPException):
        rm._safe_raster_source("")


def test_vrt_builders_write_under_upload_dir():
    """ساكن: كلّ استدعاء build_band_vrt في routers/fields.py يمرّر out_dir=main.UPLOAD_DIR
    (بوّابتا process-from-stac وbackfill) — الكتابة في /tmp تعيد إسقاط المهامّ."""
    src = open(os.path.join(RASTER, "routers", "fields.py"), encoding="utf-8").read()
    calls = re.findall(r"build_band_vrt\(([^)]*)\)", src)
    assert len(calls) >= 2, f"توقّعنا بوّابتَي بناء VRT على الأقلّ، وجدنا {len(calls)}"
    offenders = [c.strip() for c in calls if "out_dir=main.UPLOAD_DIR" not in c]
    assert not offenders, f"build_band_vrt بلا out_dir=main.UPLOAD_DIR: {offenders}"


def test_stac_total_failure_maps_to_503_not_raw_500(rm):
    """متابعة نفس البلاغ الحيّ: حين يفشل الأساس + الاحتياطيّات ولا cache (مثل تعطّل
    DNS الحاوية — Errno -5)، كان RuntimeError يخرج للعميل 500 خاماً بtraceback.
    العقد: 503 برسالة ثابتة قابلة للتصرّف (لا str(e) للعميل — يبقى في السجلّ)."""
    import asyncio

    from fastapi import HTTPException

    async def total_failure(payload):
        raise RuntimeError(
            "STAC غير متاح بعد 3 محاولات ولا cache: [Errno -5] No address associated with hostname"
        )

    # التحويل إلى CDSE جعل _stac_search يوجّه افتراضاً لكتالوج Copernicus؛ هذا الحارس
    # يخصّ مسار Element84 (فشل العميل المرن → 503) فنُثبّت المزوّد صراحةً لاختباره.
    # بعد التفكيك صار منطق التوجيه في وحدة stac_search؛ لذا نضبط المزوّد على الوحدة
    # المفكَّكة (لا على main فقط) وإلّا سقط المسار على حارس «اعتمادات CDSE غائبة».
    _helpers = rm.stac_search_helpers
    _prev_provider = rm.HISTORICAL_SEARCH_PROVIDER
    _prev_helpers_provider = _helpers.HISTORICAL_SEARCH_PROVIDER
    rm.HISTORICAL_SEARCH_PROVIDER = "element84"
    _helpers.HISTORICAL_SEARCH_PROVIDER = "element84"
    rm._stac.search = total_failure
    try:
        with pytest.raises(HTTPException) as ei:
            asyncio.run(
                rm._stac_search(
                    [44.0, 15.0, 44.01, 15.01],
                    "2026-01-01T00:00:00Z",
                    "2026-01-31T23:59:59Z",
                    30,
                    5,
                )
            )
        assert ei.value.status_code == 503
        assert "Errno" not in str(ei.value.detail), "تفصيل الاستثناء الخام تسرّب للعميل"
        assert "STAC" in str(ei.value.detail)
    finally:
        rm.HISTORICAL_SEARCH_PROVIDER = _prev_provider
        _helpers.HISTORICAL_SEARCH_PROVIDER = _prev_helpers_provider


def test_cdse_index_tif_written_under_upload_dir():
    """ساكن: GeoTIFF مؤشّر CDSE يُكتب تحت UPLOAD_DIR (يجتاز حارس المصدر)."""
    src = open(os.path.join(RASTER, "main.py"), encoding="utf-8").read()
    assert re.search(r"os\.path\.join\(UPLOAD_DIR,\s*f\"cdse_", src), (
        "كتابة CDSE tif يجب أن تبقى تحت UPLOAD_DIR — نقلها خارجه يُفشل المعالجة 400"
    )
