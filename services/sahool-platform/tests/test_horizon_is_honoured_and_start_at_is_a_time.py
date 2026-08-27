"""AN-ACCEPTED-HORIZON-IS-QUANTISED-TO-TWO-BUCKETS-01 — عقدان يكذبان بلا خطأ.

عطلان في مسارٍ واحد، وكلاهما **يَعِد بشيءٍ ويُسلّم غيرَه** بلا رفع استثناء:

**① الأفقُ المُكمَّم.** `horizon_hours` يُقبَل ويُتحقَّق منه (`ge=1, le=168`) ثمّ
يُستعمَل قيمةً منطقيّةً وحدها (`> 48`). فـ`49` و`168` يُنتِجان الطلبَ نفسَه
حرفيّاً: ١٦٨ قيمةً مقبولةً تُكرِم **سلوكين**.

**② `start_at` رمزيّ.** `best` يحمل `time` رمزيّاً (`"now"` / `"+72h"`) و
`weather_time` طابعاً زمنيّاً حقيقيّاً، وكانت الأولويّةُ للرمزيّ. فحقلٌ اسمُه
`start_at` يحمل `"+72h"` **ويُصيَّر كما هو للمزارع** في
`FieldWorkspaceWeatherPanel.tsx:53` («`+72h` → —»). وأحدُهم لاحظ التناقضَ فعالج
**تسميةَ العَرَض** («وقتُ البدء — أفقٌ ساعيّ») بدل المصدر — فالعطلُ عاش تحت لافتةٍ
تصفه.

ويُقاسان بلا تطبيقٍ ولا شبكة: دالّتان نقيّتان في وحدة الراوتر.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[1] / "api" / "routers" / "field_workspace_weather.py"


def _fns():
    """يُستخرَج المنطقُ النقيُّ بـAST — الوحدةُ تستورد `api.main` وقتَ التحميل."""
    import ast

    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    wanted = {"_series_for_horizon", "_window_from_operation", "_score_to_suitability"}
    keep = [
        n
        for n in tree.body
        if (isinstance(n, ast.FunctionDef) and n.name in wanted)
        or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "_HORIZON_LADDER")
    ]
    mod = ast.Module(body=keep, type_ignores=[])
    ns: dict = {"Any": object}
    exec(compile(ast.fix_missing_locations(mod), str(_SRC), "exec"), ns)  # noqa: S102
    return ns


ns = _fns()
series = ns["_series_for_horizon"]
window = ns["_window_from_operation"]


# ── ① الأفق ──────────────────────────────────────────────────────────────────


def test_the_two_historical_behaviours_are_preserved_exactly():
    """التعميمُ ليس تغييراً في القيمتين اللتين كان النظامُ يخدمهما فعلاً."""
    assert series(48) == "0,1,3,6,12,24,48"
    assert series(168) == "0,1,3,6,12,24,48,72,96,120,144,168"


@pytest.mark.parametrize(("a", "b"), [(49, 168), (50, 72), (1, 24), (100, 120)])
def test_distinct_horizons_no_longer_collapse_to_one_request(a: int, b: int):
    """كلُّ أفقٍ مقبولٍ يُنتِج طلبَه — لا دلوَين."""
    assert series(a) != series(b)


@pytest.mark.parametrize("horizon", [1, 5, 47, 49, 73, 167, 168])
def test_the_requested_horizon_is_always_the_last_frame(horizon: int):
    """من طلب ٤٩ ساعةً يحصل على إطارٍ عندها — لا عند ٤٨."""
    points = [int(x) for x in series(horizon).split(",")]
    assert points[-1] == horizon
    assert points == sorted(set(points)), "سلسلةٌ غيرُ مرتّبةٍ أو بتكرار"
    assert all(p <= horizon for p in points), "إطارٌ خارجَ الأفق المطلوب"


# ── ② الوقت ──────────────────────────────────────────────────────────────────

_SYMBOLIC = {"time": "+72h", "weather_time": "2026-08-27T02:00", "hour_offset": 72}


def test_start_at_carries_the_real_timestamp_not_the_symbolic_key():
    out = window({"operation": "spraying", "best": _SYMBOLIC})
    assert out["start_at"] == "2026-08-27T02:00"
    assert out["start_offset_hours"] == 72, "الإزاحةُ فُقِدت بدل أن تُسمّى"


def test_a_missing_timestamp_is_none_not_a_symbol():
    """بلا طابعٍ حقيقيّ لا يُختلَق شيء — و**لا يُستعمَل الرمزُ بديلاً**."""
    out = window({"operation": "spraying", "best": {"time": "now", "hour_offset": 0}})
    assert out["start_at"] is None
    assert out["start_offset_hours"] == 0


def test_no_symbolic_offset_can_reach_start_at():
    """راتشِتٌ على الشكل: `start_at` إمّا طابعٌ زمنيّ وإمّا `None`."""
    for symbol in ("now", "+1h", "+168h"):
        out = window({"best": {"time": symbol, "hour_offset": 1}})
        assert out["start_at"] is None, f"الرمز {symbol!r} بلغ start_at"
