#!/usr/bin/env python3
"""عقد ``UNBOUNDED-RASTER-READ-ON-ARBITRARY-URL-01`` — الحجم يُفحَص قبل التخصيص.

``src.read()`` يخصّص ``width × height × count`` بايتاً دفعةً واحدة، و
``safe_raster_source`` يقبل **أيّ** رابط ``http(s)`` غير محجوب — فحجم المصدر ليس تحت
سيطرة الخدمة. و``rasterio.open`` يعطي الأبعاد بلا قراءة بكسل، فالفحص مجّانيّ.

**وهذا تصحيحٌ لتصنيف تقرير الشهادة، لا تأكيدٌ له.** التقرير نسب العطل إلى «قراءة مشهد
Sentinel-2 كامل» عبر مسار CDSE؛ والقياس يُكذّب ذلك:
``raster_backfill_scene_processing.process_backfill_scene_cdse`` يستدعي
``process_index(bbox=…, geometry=clip)`` — فالراستر **مقصوص على حدود الحقل قبل أن يصل
الخدمة**. المسار الإنتاجيّ محدود. غير المحدود هو ``/process`` برابطٍ حرّ، وهو ما يُغلَق هنا.

**والرفض المُعلَن أصدق من OOM صامت:** حاويةٌ تُقتَل بـSIGKILL لا تترك سبباً في أيّ سجلّ
ولا في أيّ صفّ — وهي بالضبط الحالة التي عجز تقرير الشهادة عن إثباتها لغياب الدليل.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services/raster-service"
PIXEL = RASTER / "raster_pixel_processing.py"
TILE = RASTER / "tile_render.py"


def _load(name: str):
    for path in (str(ROOT), str(RASTER)):
        if path not in sys.path:
            sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location(f"_probe_{name}", RASTER / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Src:
    """أصغر ما يحتاجه الفحص من مجموعة بيانات — الأبعاد بلا أيّ بكسل."""

    def __init__(self, width: int, height: int, count: int) -> None:
        self.width, self.height, self.count = width, height, count


@pytest.fixture(scope="module")
def security():
    return _load("raster_security_context")


def test_a_full_sentinel2_scene_is_refused_not_allocated(security):
    """٤٨٢ م.بكسل-نطاق مقابل ``mem_limit`` قدره 1536m — والقناع والكتابة يخصّصان أيضاً."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        security.assert_readable_size(_Src(10980, 10980, 4), what="probe", ceiling=64_000_000)
    assert exc.value.status_code == 413
    # رسالة الحارس جزءٌ منه: تُسمّي الأبعاد والسقف وما يفعله المُستدعي.
    detail = str(exc.value.detail)
    assert "10980" in detail and "64,000,000" in detail
    assert "RASTER_MAX_READ_BAND_PIXELS" in detail


def test_a_field_sized_raster_passes(security):
    """حارسٌ يرفض الجميع لا يقيس شيئاً — والحقل النموذجيّ أصغر بمراتب."""
    assert security.assert_readable_size(_Src(2000, 2000, 4), what="probe", ceiling=64_000_000) == (
        2000 * 2000 * 4
    )


def test_the_ceiling_counts_bands_not_just_area(security):
    """‏RGBA يخصّص أربعة أضعاف نطاقٍ واحد؛ حسابُ المساحة وحدها يُخطئ بأربع مرّات."""
    from fastapi import HTTPException

    area_only = 5000 * 5000  # = 25 م.بكسل — تحت السقف لو أُهمِلت النطاقات
    assert area_only < 64_000_000
    with pytest.raises(HTTPException):
        security.assert_readable_size(_Src(5000, 5000, 4), what="probe", ceiling=64_000_000)


def _calls_guard_before_read(path: Path, func_name: str) -> bool:
    """هل يسبق ``assert_readable_size`` أوّلَ ``src.read()`` داخل الدالّة؟

    مُشتقّ بشجرة AST: مطابقةُ نصٍّ تقول إنّ الاسمَين موجودان، لا إنّ الترتيب صحيح —
    وحارسٌ يُستدعى **بعد** التخصيص لا يمنع شيئاً.
    """
    fn = next(
        node
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name == func_name
    )
    guard_line = read_line = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            rendered = ast.unparse(node.func)
            if rendered.endswith("assert_readable_size") and guard_line is None:
                guard_line = node.lineno
            if rendered.endswith(".read") and read_line is None:
                read_line = node.lineno
    return guard_line is not None and read_line is not None and guard_line < read_line


def test_the_truecolor_path_checks_before_it_allocates():
    assert _calls_guard_before_read(PIXEL, "process_precomputed_truecolor"), (
        "الفحص لا يسبق القراءة — حارسٌ بعد التخصيص لا يمنع شيئاً"
    )


def test_the_uint8_polygon_mask_checks_before_it_allocates():
    name = next(
        node.name
        for node in ast.walk(ast.parse(TILE.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and "assert_readable_size" in ast.unparse(node)
    )
    assert _calls_guard_before_read(TILE, name)


def test_the_ceiling_is_declared_data_not_a_literal_at_the_call_site():
    """رقمٌ مبعثر في موضعَين ينحرف؛ ومصدرٌ واحد يُغيَّر ببيئة عند الحاجة."""
    settings = _load("raster_settings")
    assert settings.RASTER_MAX_READ_BAND_PIXELS > 0
    for path in (PIXEL, TILE):
        source = path.read_text(encoding="utf-8")
        assert "RASTER_MAX_READ_BAND_PIXELS" in source, f"{path.name} لا يقرأ السقف المُعلَن"


def test_the_cdse_production_path_is_clipped_upstream():
    """التصحيح مُثبَّت لا مكتوب: المسار الذي اتُّهم في التقرير محدودٌ أصلاً.

    لو سقط هذا الاختبار يوماً — أي زال القصّ أعلى المجرى — فالتصنيف يعود صحيحاً كما
    كُتِب، ويجب أن يُعاد فتحه لا أن يُقرأ التوثيق على أنّه ما يزال صادقاً.
    """
    source = (RASTER / "raster_backfill_scene_processing.py").read_text(encoding="utf-8")
    call = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("process_index")
    )
    keywords = {kw.arg for kw in call.keywords}
    assert {"bbox", "geometry"} <= keywords, (
        f"القصّ أعلى المجرى زال ({keywords}) — أُعِد فتح تصنيف «قراءة مشهد كامل»"
    )
