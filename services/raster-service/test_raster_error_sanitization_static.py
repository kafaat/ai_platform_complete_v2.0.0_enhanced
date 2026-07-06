#!/usr/bin/env python3
"""حارس ساكن: لا تسريب نصّ الاستثناء (`str(e)`) في حقول الخطأ المكشوفة للعميل.

raster-service يُرجِع حالة الوظائف عبر `/jobs/{id}/result` و`batch_failed` — فلا يجوز
كتابة `str(e)` الخام (مسارات ملفّات/S3/SQL) في `error_message` أو عناصر `failed[...]`.
يجب أن تكون رموزاً عامّة (processing_failed/scene_processing_failed) مع تسجيل
`type(e).__name__` في log فقط.

ساكن بحت (يقرأ النصّ) — يعمل بلا rasterio/قاعدة، ويمنع الانحدار.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

_MAIN_PATH = Path(__file__).resolve().parent / "main.py"


# وحدات التفكيك (phase2–5): مُعالِجات/تنسيق استُخرِجت من main.py إلى وحدات شقيقة
# (لا تحت routers/). يجب أن يبقى فحص تعقيم الأخطاء + رموز الفشل شاملاً لها أيضاً،
# وإلّا تسلّل str(e) أو اختفى رمز فشل عامّ عبر النقل خارج main.py دون رصد.
_DECOMP_MODULES = (
    "raster_job_orchestration.py",
    "scene_policy.py",
    "stac_search.py",
    "raster_asset_persistence.py",
    "raster_date_geo.py",
    "cdse_singleflight.py",
    "layer_lookup.py",
    "tile_cache_io.py",
)


class _CombinedSource:
    """توحيد main↔cert: المسارات فُكِّكت من main.py إلى routers/ ووحدات شقيقة. ``read_text()``
    يُرجِع المصدرَ المُجمَّع (main.py + routers/*.py + وحدات التفكيك) كي يبقى فحص تعقيم
    الأخطاء ورموز الفشل شاملاً المعالِجات أينما انتقلت."""

    def read_text(self, *a, **k) -> str:
        base = _MAIN_PATH.parent
        rdir = base / "routers"
        parts = [_MAIN_PATH.read_text(encoding="utf-8")]
        parts += [
            Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(rdir / "*.py")))
        ]
        parts += [
            (base / m).read_text(encoding="utf-8") for m in _DECOMP_MODULES if (base / m).exists()
        ]
        return "\n".join(parts)


_MAIN = _CombinedSource()


def test_no_str_exception_in_client_error_fields():
    """لا يجوز إسناد str(e)/str(_e) إلى حقل خطأ مكشوف للعميل."""
    src = _MAIN.read_text(encoding="utf-8")
    forbidden = [
        r'"error_message"\s*:\s*str\(\s*_?e\w*\s*\)',  # "error_message": str(e)
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


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
