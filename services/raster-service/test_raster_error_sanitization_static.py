#!/usr/bin/env python3
"""حارس ساكن: لا تسريب نصّ الاستثناء (`str(e)`) في حقول الخطأ المكشوفة للعميل.

raster-service يُرجِع حالة الوظائف عبر `/jobs/{id}/result` و`batch_failed` — فلا يجوز
كتابة `str(e)` الخام (مسارات ملفّات/S3/SQL) في `error_message` أو عناصر `failed[...]`.
يجب أن تكون رموزاً عامّة (processing_failed/...) مع تسجيل `type(e).__name__` في log فقط.
ساكن بحت (يقرأ النصّ) — يعمل بلا rasterio/قاعدة، ويمنع الانحدار.
"""

from __future__ import annotations

import re
from pathlib import Path

_MAIN = Path(__file__).resolve().parent / "main.py"


def test_no_str_exception_in_client_error_fields():
    src = _MAIN.read_text(encoding="utf-8")
    # أنماط محظورة: تسريب str(e)/str(_e) في error_message أو إسناد failed[...].
    forbidden = [
        r'"error_message"\s*:\s*str\(\s*_?e\w*\s*\)',  # error_message": str(e)
        r"failed\[[^\]]+\]\s*=\s*str\(\s*_?e\w*\s*\)",  # failed[...] = str(e)
        r"error_message\s*=\s*str\(\s*_?e\w*\s*\)",  # error_message = str(e)
    ]
    offenders: list[str] = []
    for pat in forbidden:
        for m in re.finditer(pat, src):
            line = src[: m.start()].count("\n") + 1
            offenders.append(f"main.py:{line}: {m.group(0)}")
    assert not offenders, "تسريب نصّ استثناء في حقل خطأ مكشوف للعميل:\n  " + "\n  ".join(offenders)


def test_generic_failure_codes_present():
    """تأكيد بقاء الرموز العامّة (لم يُعَد str(e) خلسةً)."""
    src = _MAIN.read_text(encoding="utf-8")
    assert '"processing_failed"' in src
    assert '"scene_processing_failed"' in src
    assert '"raster_processing_failed"' in src


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
