"""حارس عقد التاريخ في طلب TileJSON بالواجهة (FieldIndicatorMap.tsx).

السبب (متابعة D من مراجعة النسخة): باني رابط البلاطة كان يحذف `date` حين تكون فارغة أو
`latest`، لكنّ طلب TileJSON كان يبني `params: { index, date }` بلا شرط ⇒ قد يخرج
`date=latest`/`date=` في طلب TileJSON. الخادم يتحمّلها، لكنّ نظافة العقد تقتضي عدم تمرير
`date` إلّا حين يكون تاريخاً صريحاً (`YYYY-MM-DD`). backend يعامل الغياب كأحدث مشهد.

هذا الحارس يُثبّت الإصلاح في CI (مسح نصّيّ ساكن — لا تشغيل Node/Vite):
  • طلب TileJSON لا يمرّر `params: { index, date }` غير مشروط.
  • يُمرّر الصيغة المشروطة (`date && date !== 'latest'`).
  • باني رابط البلاطة (indicatorTileUrl) يبقى محميّاً بنفس الشرط.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_FIELD_MAP = os.path.join(_ROOT, "frontend", "src", "components", "FieldIndicatorMap.tsx")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_field_indicator_map_exists():
    assert os.path.exists(_FIELD_MAP), "FieldIndicatorMap.tsx مفقود"


def test_tilejson_request_does_not_pass_date_unconditionally():
    """طلب TileJSON يجب ألّا يبني `params: { index, date }` بلا شرط (تسريب date=latest)."""
    src = _read(_FIELD_MAP)
    # نتجاهل أسطر التعليقات (// ...) — قد تذكر العقد القديم شرحاً.
    code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("//"))
    # الصيغة الحرفيّة غير المشروطة المرفوضة (تتجاهل المسافات الداخليّة).
    bad = re.search(r"params:\s*\{\s*index\s*,\s*date\s*\}", code)
    assert bad is None, (
        "طلب TileJSON يمرّر `params: { index, date }` غير مشروط — "
        "استخدم `date && date !== 'latest' ? { index, date } : { index }`"
    )


def test_tilejson_request_uses_conditional_date():
    """يجب تمرير الصيغة المشروطة التي تحذف date عند الغياب/`latest`."""
    src = _read(_FIELD_MAP)
    assert re.search(
        r"date\s*&&\s*date\s*!==\s*'latest'\s*\?\s*\{\s*index\s*,\s*date\s*\}\s*:\s*\{\s*index\s*\}",
        src,
    ), "طلب TileJSON لا يستخدم params المشروطة (date && date !== 'latest' ? {index,date} : {index})"


def test_tile_url_builder_still_guards_date():
    """انحدار: باني رابط البلاطة (indicatorTileUrl) يبقى يحذف date عند الغياب/`latest`."""
    src = _read(_FIELD_MAP)
    assert "date && date !== 'latest'" in src, "حارس date في باني رابط البلاطة مفقود"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
