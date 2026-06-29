"""حارس عقد التاريخ في طلب البلاطات/TileJSON بالواجهة (متابعة D، توحيد main↔cert).

السبب: الواجهة كانت تمرّر ``date`` بلا شرط في طلب TileJSON وفي باني رابط البلاطة
(``fieldIndicatorTileUrl``) ⇒ قد يخرج ``date=latest``/``date=`` في الطلب. الخادم
يتحمّلها (يعامل الغياب كأحدث مشهد)، لكنّ نظافة العقد تقتضي عدم تمرير ``date`` إلّا حين
يكون تاريخاً صريحاً (``YYYY-MM-DD``).

بعد توحيد main↔cert صارت بنية الواجهة لـcert (الأحدث): طلب TileJSON في
``FieldIndicatorMap.tsx`` + باني الرابط ``fieldIndicatorTileUrl`` في ``services/api.ts``.
هذا الحارس يُثبّت إصلاح D في الموضعَين (مسح نصّيّ ساكن — لا تشغيل Node/Vite).
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_FIELD_MAP = os.path.join(_ROOT, "frontend", "src", "components", "FieldIndicatorMap.tsx")
_API_TS = os.path.join(_ROOT, "frontend", "src", "services", "api.ts")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _strip_comments(src: str) -> str:
    return "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("//"))


def test_frontend_files_exist():
    assert os.path.exists(_FIELD_MAP), "FieldIndicatorMap.tsx مفقود"
    assert os.path.exists(_API_TS), "services/api.ts مفقود"


def test_tilejson_request_does_not_pass_date_unconditionally():
    """طلب TileJSON يجب ألّا يبني params بـ``date`` غير مشروط (تسريب date=latest)."""
    code = _strip_comments(_read(_FIELD_MAP))
    # الصيغة الحرفيّة غير المشروطة المرفوضة: { index: <x>, date, ... }
    bad = re.search(r"params:\s*\{\s*index:\s*\w+\s*,\s*date\s*[,}]", code)
    assert bad is None, (
        "طلب TileJSON يمرّر date غير مشروط — استخدم `...(date && date !== 'latest' ? { date } : {})`"
    )


def test_tilejson_request_uses_conditional_date():
    """طلب TileJSON يجب أن يحذف date عند الغياب/``latest`` (صيغة مشروطة)."""
    code = _strip_comments(_read(_FIELD_MAP))
    assert re.search(
        r"date\s*&&\s*date\s*!==\s*'latest'\s*\?\s*\{\s*date\s*\}\s*:\s*\{\s*\}",
        code,
    ), "طلب TileJSON لا يستخدم date المشروط (date && date !== 'latest' ? { date } : {})"


def test_tile_url_builder_guards_date():
    """باني رابط البلاطة ``fieldIndicatorTileUrl`` (api.ts) يحذف date عند الغياب/``latest``."""
    code = _strip_comments(_read(_API_TS))
    # يجب ألّا يُمرَّر date داخل URLSearchParams ابتدائيّاً بلا شرط لباني البلاطة.
    assert "fieldIndicatorTileUrl" in code, "fieldIndicatorTileUrl غير موجود"
    assert re.search(
        r"if\s*\(\s*date\s*&&\s*date\s*!==\s*'latest'\s*\)\s*params\.set\(\s*'date'",
        code,
    ), "fieldIndicatorTileUrl لا يحرس date (لا يحذفه عند latest/فارغ)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
