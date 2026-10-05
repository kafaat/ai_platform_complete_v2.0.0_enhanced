"""احتواءُ Element84→VRT: الرفضُ صريحٌ، منظَّم، وفي **كلّ** نقطة دخول.

المسار محجوب لثلاثة عيوب مقيسة (المقياس · محاذاة 10/20م · NoData — ``radiometry_containment``).
هذا الملفّ يعمل في بيئة *Unit Tests* الدنيا (بلا rasterio): يُثبت الحمولة سلوكيّاً، ويُثبت
بالمصدر المُحلَّل أنّ **لا** مستدعيَ إنتاجيّاً لـ``build_band_vrt`` بقي وأنّ نقاط الدخول الثلاث
ترفض. الشواهدُ السلوكيّة لنقاط الدخول (لا معالجة · لا COG · لا حفظ) في
``services/raster-service/test_element84_vrt_containment_runtime.py`` (وظيفة *Raster Service
Tests*، حيث rasterio مُثبَّت).
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services" / "raster-service"


def _containment():
    spec = importlib.util.spec_from_file_location(
        "_radiometry_containment", RASTER / "radiometry_containment.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_the_rejection_is_structured_permanent_and_names_its_causes():
    rc = _containment()
    detail = rc.element84_vrt_detail(["red", "nir", "swir1", "scl"], entry_point="probe")

    assert detail["code"] == "radiometry_unresolved"
    assert detail["provider"] == "element84" and detail["path"] == "stac_vrt"
    assert detail["retryable"] is False
    codes = [r["code"] for r in detail["reasons"]]
    assert codes == [
        "reflectance_scale_unresolved",
        "band_grid_misaligned",
        "nodata_not_propagated",
    ]
    misaligned = next(r for r in detail["reasons"] if r["code"] == "band_grid_misaligned")
    assert misaligned["bands"] == ["swir1", "scl"]
    assert set(detail["gap_ids"]) == set(rc.GAP_IDS)


def test_alignment_is_claimed_only_when_a_twenty_metre_band_is_requested():
    """السببُ وقائعُ الطلب: red/nir وحدهما (10م) لا يحملان سبب المحاذاة — المقياس وNoData يكفيان."""
    rc = _containment()
    detail = rc.element84_vrt_detail({"red": "r", "nir": "n"}, entry_point="probe")
    codes = [r["code"] for r in detail["reasons"]]
    assert codes == ["reflectance_scale_unresolved", "nodata_not_propagated"]


def test_the_payload_carries_band_names_never_hrefs():
    """الحمولة تصل إلى العميل وإلى عمود المهمّة؛ الروابط (قد تحمل توقيعاً) لا تُعاد."""
    rc = _containment()
    hrefs = {"red": "https://signed.example/red.tif?X-Amz-Signature=abc", "nir": "s3://b/nir.tif"}
    with pytest.raises(rc.RadiometryUnresolved) as info:
        rc.reject_element84_vrt(hrefs.keys(), entry_point="probe")
    dumped = json.dumps(info.value.detail)
    assert info.value.detail["bands"] == ["nir", "red"]
    assert "https://" not in dumped and "s3://" not in dumped and "Signature" not in dumped


def test_the_item_error_prefix_is_the_permanent_marker_the_requeue_reads():
    rc = _containment()
    assert rc.ITEM_ERROR.startswith(rc.RADIOMETRY_UNRESOLVED + ":")


# ── بالمصدر المُحلَّل: لا مستدعيَ إنتاجيّاً لبنّاء الـVRT، ونقاط الدخول الثلاث ترفض ──


def _production_sources() -> list[Path]:
    out = []
    for path in sorted((ROOT / "services").rglob("*.py")):
        name = path.name
        if name.startswith("test_") or "tests" in path.parts or name == "stac_vrt.py":
            continue
        out.append(path)
    return out


def _calls(tree: ast.AST, attr: str) -> list[ast.Call]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name == attr:
                found.append(node)
    return found


def test_no_production_code_builds_an_element84_vrt_while_contained():
    """الاحتواءُ في كلّ المسارات لا في العامل وحده: أيُّ استدعاءٍ لـ``build_band_vrt`` خارج
    الاختبارات يُعيد فتح المسار المحجوب. يُرفَع هذا الحارس مع عقد التطبيع لا قبله."""
    offenders = []
    for path in _production_sources():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for call in _calls(tree, "build_band_vrt"):
            offenders.append(f"{path.relative_to(ROOT)}:{call.lineno}")
    assert not offenders, "مسار Element84→VRT مفتوح خارج الاحتواء:\n  " + "\n  ".join(offenders)


ENTRY_POINTS = {
    ("services/raster-service/routers/fields.py", "process_from_stac"),
    ("services/raster-service/routers/fields.py", "field_historical_backfill"),
    ("services/raster-service/backfill_scan_worker.py", "_process_scene_index"),
}


@pytest.mark.parametrize("rel,func", sorted(ENTRY_POINTS))
def test_each_former_vrt_entry_point_rejects(rel, func):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == func
        ),
        None,
    )
    assert fn is not None, f"{rel}::{func} لم يعد موجوداً — حدّث قائمة نقاط الدخول"
    calls = _calls(fn, "reject_element84_vrt")
    assert calls, f"{rel}::{func} لا يرفض مسار Element84→VRT"
    entry = {kw.arg: kw.value for kw in calls[0].keywords}
    assert isinstance(entry.get("entry_point"), ast.Constant), "entry_point يجب أن يكون اسماً ثابتاً"
