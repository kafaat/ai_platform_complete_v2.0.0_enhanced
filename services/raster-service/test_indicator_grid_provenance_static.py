"""وحدة (ساكن): indicator-grid يُسطّح النَّسَب المفرد للواجهة بصدق (لا اختلاق).

تدقيق عميق: عقد الإرسال/الاستهلاك بين raster-service وsceneFreshness غير مُوحَّد —
الواجهة تنتظر scene_id/field_revision/processing_version لكن الراستر لم يُسطّحها.
هذا الحارس يثبّت أنّ field_indicator_grid يكشفها **مفردةً عند عدم الالتباس فقط**.

وحدة صرفة — ``pytest -m unit`` (نصّ، لا خدمة).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = (Path(__file__).resolve().parent / "routers" / "fields.py").read_text(encoding="utf-8")


def test_grid_surfaces_singular_provenance_keys():
    for key in ('"scene_id"', '"field_revision"', '"processing_version"'):
        assert key in _SRC, key


def test_singular_only_when_unambiguous_no_fabrication():
    # _single يُرجِع القيمة فقط عند وجود قيمة واحدة (وإلّا None) — لا يخترع نَسَباً.
    assert "def _single(" in _SRC
    assert "if len(values) == 1 else None" in _SRC
    # field_revision يُقرأ من النَّسَب أو من الطبقة (geometry_revision) لا يُلفَّق.
    assert 'provenance.get("geometry_revision")' in _SRC
    assert 'layer.get("geometry_revision")' in _SRC
    assert 'provenance.get("processing_version")' in _SRC
