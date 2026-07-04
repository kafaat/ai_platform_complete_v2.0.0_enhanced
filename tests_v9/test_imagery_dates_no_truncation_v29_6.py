"""حارس انحدار: سلسلة تواريخ الصور لا تُبتَر عند سنتين+ وتُبقي الأحدث.

الخلل (قبل v29.6): ``list_asset_dates`` كان يستخدم ``LIMIT 100`` مع ``ORDER BY
acquisition_date ASC`` — فسلسلة Sentinel-2 لسنتين (≈146 مروراً، وغالباً >100 بعد
رفض الغيوم) تُبتَر، والأسوأ أنّها تُبقي **أقدم** 100 وتُسقط الأحدث. النتيجة: شريط
الصور الزمنيّ (DateScrubber) يعرض 2024 ويفقد 2026.

الإصلاح: السقف الافتراضيّ 800 (يسع 5 سنوات لعدّة مؤشّرات)، والاستعلام يأخذ الأحدث
(DESC+LIMIT) ثمّ يُرجِعها تصاعديّاً. هذا الاختبار يحاكي دلالة الاستعلام على >100
تاريخ ويؤكّد: (أ) لا بتر دون السقف، (ب) عند البتر تبقى الأحدث لا الأقدم، (ج) الترتيب
النهائيّ تصاعديّ.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DB_PERSIST = REPO / "services" / "raster-service" / "db_persist.py"


def _load_db_persist():
    """حمّل db_persist مع كبت تبعيّاته الخارجيّة (asyncpg) إن غابت."""
    if "asyncpg" not in sys.modules:
        stub = types.ModuleType("asyncpg")
        sys.modules["asyncpg"] = stub
    spec = importlib.util.spec_from_file_location("raster_db_persist", DB_PERSIST)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class _FakeConn:
    """اتّصال asyncpg مُزيّف يحاكي دلالة SQL (DESC+LIMIT داخليّ ثمّ ASC خارجيّ)."""

    def __init__(self, all_dates: list[str]) -> None:
        self._all = all_dates

    async def execute(self, *_a, **_k):  # set_config
        return "SET"

    async def fetch(self, _sql, field_id, index_name, tenant_id, limit):
        # حاكِ الاستعلام: distinct + DESC + LIMIT ثمّ ORDER BY ASC خارجيّ.
        distinct = sorted(set(self._all), reverse=True)  # DESC
        newest = distinct[: int(limit)]  # LIMIT (الأحدث)
        ascending = sorted(newest)  # ORDER BY ad ASC خارجيّ
        return [{"acq": d} for d in ascending]

    async def close(self):
        return None


def _two_years_of_dates(n: int) -> list[str]:
    """n تاريخ اكتساب كلّ 5 أيّام تنازليّاً من اليوم (يحاكي إعادة زيارة Sentinel-2)."""
    base = _dt.date(2026, 6, 1)
    return [(base - _dt.timedelta(days=5 * i)).isoformat() for i in range(n)]


@pytest.mark.unit
def test_default_limit_covers_two_years() -> None:
    """السقف الافتراضيّ يتّسع لسلسلة سنتين (>140 تاريخاً) بلا بتر."""
    import asyncio

    mod = _load_db_persist()
    dates = _two_years_of_dates(150)  # > سقف 100 القديم

    async def _connect(ds=dates):
        return _FakeConn(ds)

    mod._connect = _connect  # type: ignore[assignment]
    out = asyncio.run(mod.list_asset_dates("f1", "ndvi", tenant_id="t1"))
    assert len(out) == 150, f"سلسلة سنتين بُترت: أُرجِع {len(out)} من 150"
    assert out == sorted(out), "الترتيب النهائيّ يجب أن يكون تصاعديّاً"


@pytest.mark.unit
def test_when_capped_keeps_newest_not_oldest() -> None:
    """عند تجاوز السقف، تبقى الأحدث لا الأقدم (إصلاح ASC→DESC)."""
    import asyncio

    mod = _load_db_persist()
    dates = _two_years_of_dates(1000)  # يتجاوز السقف الافتراضيّ 800

    async def _connect(ds=dates):
        return _FakeConn(ds)

    mod._connect = _connect  # type: ignore[assignment]

    out = asyncio.run(mod.list_asset_dates("f1", "ndvi", tenant_id="t1"))
    assert len(out) == 800, f"توقّع 800 (السقف)، حصل {len(out)}"
    newest_expected = max(dates)
    oldest_all = min(dates)
    assert out[-1] == newest_expected, "يجب الاحتفاظ بأحدث تاريخ"
    assert oldest_all not in out, "أقدم تاريخ يجب أن يُسقَط عند البتر (لا العكس)"


@pytest.mark.unit
def test_signature_default_raised_above_100() -> None:
    """توقيع الدالة: السقف الافتراضيّ رُفِع فوق 100 (حارس ضدّ العودة للخلل)."""
    import inspect

    mod = _load_db_persist()
    sig = inspect.signature(mod.list_asset_dates)
    default = sig.parameters["limit"].default
    assert default >= 600, f"السقف الافتراضيّ {default} < 600 — سيبتر سلسلة سنتين+"
