"""اختبار: رصد جودة البيانات في estimate_lai_from_ndvi إضافيّ فقط (لا يغيّر السلوك).

نتحقّق من:
  • السلوك القديم (فلتر «< 0» والمخرجات) يبقى مطابقاً تماماً.
  • تُسجَّل مخالفة جودة عند NDVI خارج المدى الفيزيائيّ [-1, 1].
  • لا يرمي المسار استثناءً حتى لو تعذّر استيراد api.data_quality (حارس الاستيراد).
"""

from __future__ import annotations

import logging

from core.spatial.pipeline import estimate_lai_from_ndvi


def test_legacy_negative_ndvi_behavior_unchanged():
    """فلتر «NDVI < 0» القديم يبقى كما هو — نفس المخرَج تماماً."""
    assert estimate_lai_from_ndvi(-0.5) == {
        "lai": None,
        "confidence": "none",
        "note_ar": "NDVI غير صالح",
    }
    assert estimate_lai_from_ndvi(None) == {
        "lai": None,
        "confidence": "none",
        "note_ar": "NDVI غير صالح",
    }


def test_valid_ndvi_output_unchanged():
    """قيمة NDVI صالحة → نفس مخرَج LAI كالسابق (لا تأثير للرصد على القيمة)."""
    out = estimate_lai_from_ndvi(0.6)
    assert out["lai"] == 1.67
    assert out["confidence"] == "estimate"
    assert out["density_ar"] == "غطاء معتدل"


def test_dq_violation_logged_without_changing_result(caplog):
    """NDVI خارج [-1, 1] يُسجَّل كمخالفة جودة، لكنّ المخرَج يبقى مخرَج «< 0» القديم."""
    with caplog.at_level(logging.WARNING, logger="core.spatial.pipeline"):
        out = estimate_lai_from_ndvi(-2.0)
    # المخرَج لم يتغيّر — لا يزال يتبع فرع «غير صالح».
    assert out == {"lai": None, "confidence": "none", "note_ar": "NDVI غير صالح"}
    # سُجِّلت المخالفة (رصد فقط).
    assert any("ndvi_physical_range" in rec.message for rec in caplog.records)


def test_no_violation_for_in_range_ndvi(caplog):
    """قيمة ضمن المدى الفيزيائيّ لا تُنتج تحذير جودة."""
    with caplog.at_level(logging.WARNING, logger="core.spatial.pipeline"):
        estimate_lai_from_ndvi(0.5)
    assert not any("ndvi_physical_range" in rec.message for rec in caplog.records)


def test_does_not_raise_when_dq_import_unavailable(monkeypatch):
    """حارس الاستيراد: حتى لو فشل استيراد api.data_quality لا يُسقِط المسار."""
    import builtins

    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "api.data_quality" or name.startswith("api.data_quality"):
            raise ImportError("api غير قابل للاستيراد في هذا السياق")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_import)
    # لا استثناء، ونفس السلوك القديم.
    assert estimate_lai_from_ndvi(-2.0) == {
        "lai": None,
        "confidence": "none",
        "note_ar": "NDVI غير صالح",
    }
