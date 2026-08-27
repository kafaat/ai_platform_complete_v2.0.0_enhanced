"""ما تُرسِله المنصّةُ من إزاحاتٍ يصل الخدمةَ كاملاً — وإلّا فالأفقُ وعدٌ لا يُنفَّذ.

**العطلُ المقيس على `main` بعد #948:** أغلقت تلك الشريحةُ شقَّ الأفق في
**طرف المنصّة** — ``_series_for_horizon`` يشتقّ السلّمَ من ``horizon_hours``
بدل ثابتين. وهو إصلاحٌ صحيح، **لكنّ أثرَه مُبطَلٌ حيث يهمّ**: قائمةُ السماح
في ``services/weather-service/tiles.py`` كانت مغلقةً على ``{0,1,3,6,12,24,48}``
وترمي كلَّ ما فوقها صامتةً.

المقيس على رأس ``main`` قبل هذه الشريحة::

    أفق 168 ⇒ تُرسِل 12 إزاحة · يصل 7 · ضاع [72, 96, 120, 144, 168]
    وparse_series_hours(_series_for_horizon(48)) == parse_series_hours(_series_for_horizon(168))

أي أنّ ``horizon_hours=168`` و``=48`` ظلّا يُنتِجان النتيجةَ نفسَها **حرفيّاً**
بعد الإصلاح كما قبله.

**ولمَ لم يكشفه اختبارُ #948:** يعيش في ``services/sahool-platform/tests/``
ويقرأ الراوترَ وحدَه — لا يستورد ``tiles`` ولا ``parse_series_hours``. فهو
يُثبِت أنّ **المنصّة تُرسِل** الصحيح، لا أنّ **الخدمة تستقبله**. وكلا الطرفين
سليمٌ بمعزل: المنصّةُ تُرسِل قائمةً معقولة، والخدمةُ تُصفّي مُدخَلاً غيرَ
موثوق. **العطلُ في القفزة**، ولا يظهر إلّا بقياس الطرفين معاً — وهو ما يفعله
هذا الملفّ وحدَه.

وهو الصنفُ نفسُه الذي أسقط ``WEATHER-CLIENT-ASKS-A-PATH-THE-SERVICE-NEVER-
DECLARED-01``: عقدٌ طرفاه في خدمتين، وكلٌّ مختبَرٌ وحدَه، والقفزةُ بلا شاهد.

**والخاصّيّةُ المحروسة ليست «١٦٨ تعمل»** بل **الوصولُ الكامل**: لا إزاحةَ
تُرسَل وتُرمى. فذلك يبقى صادقاً لو تغيّر السلّمُ أو المدى.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_ROUTER = _ROOT / "services" / "sahool-platform" / "api" / "routers" / "field_workspace_weather.py"


@pytest.fixture(scope="module")
def series_for_horizon():
    """يُستخرَج مُشتقُّ السلّم من الراوتر بلا استيراد `fastapi` — الدالّةُ نقيّة."""
    tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
    wanted = ("_HORIZON_LADDER", "_series_for_horizon")
    body = [
        n
        for n in tree.body
        if (isinstance(n, ast.FunctionDef) and n.name in wanted)
        or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in wanted)
    ]
    assert len(body) == len(wanted), (
        "لم يُعثَر على سلّم الأفق أو مُشتقّه في الراوتر — تغيّر شكلُه والفحصُ صار أعمى"
    )
    ns: dict = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), "<router>", "exec"), ns)  # noqa: S102
    return ns["_series_for_horizon"]


@pytest.fixture(scope="module")
def parse_series_hours():
    sys.path.insert(0, str(_ROOT / "services" / "weather-service"))
    from tiles import parse_series_hours as fn

    return fn


_HORIZONS = [1, 6, 24, 48, 72, 96, 120, 168]


@pytest.mark.parametrize("horizon", _HORIZONS)
def test_no_offset_the_platform_sends_is_dropped_by_the_service(
    horizon, series_for_horizon, parse_series_hours
) -> None:
    """القفزةُ بين الخدمتين — الطرفُ الذي لا يفحصه اختبارُ أيٍّ منهما."""
    sent_raw = series_for_horizon(horizon)
    sent = [int(part) for part in sent_raw.split(",") if part.strip()]
    got = parse_series_hours(sent_raw)

    dropped = [h for h in sent if h not in got]
    assert not dropped, (
        f"أفق {horizon}: أُرسِلت {len(sent)} إزاحة ووصلت {len(got)} — "
        f"رُمِيت صامتةً: {dropped}. فالأفقُ وعدٌ لا يُنفَّذ."
    )


def test_a_longer_horizon_actually_reaches_further(series_for_horizon, parse_series_hours) -> None:
    """جوهرُ العطل: 48 و168 كانا يصلان بالنتيجة نفسها حرفيّاً."""
    at_48 = parse_series_hours(series_for_horizon(48))
    at_168 = parse_series_hours(series_for_horizon(168))

    assert at_168 != at_48, "الأفقُ الأطولُ يصل بالنتيجة نفسها — الإسقاطُ الصامت ما يزال قائماً"
    assert max(at_168) > max(at_48)


@pytest.mark.parametrize("pair", [(6, 24), (24, 48), (48, 72), (72, 168)])
def test_what_reaches_the_service_is_monotone_in_the_horizon(
    pair, series_for_horizon, parse_series_hours
) -> None:
    """اطّرادٌ يقيس العلاقة لا أرقاماً — يبقى صادقاً لو تغيّر السلّم."""
    small, large = pair
    a = set(parse_series_hours(series_for_horizon(small)))
    b = set(parse_series_hours(series_for_horizon(large)))

    assert a <= b, f"ما يصل عند {large} لا يشمل ما يصل عند {small}"


def test_the_service_still_refuses_what_lies_outside_its_range(parse_series_hours) -> None:
    """توسيعُ المدى ليس فتحَه: ما فوق السقف وما دون الصفر يبقيان مرفوضين."""
    assert parse_series_hours("0,24,999,-5") == [0, 24]


def test_the_service_bounds_the_frame_count(parse_series_hours) -> None:
    """كلُّ إطارٍ عيّنةُ مزوّدٍ تُضرَب في عدد العمليّات — فالسقفُ يحدّ الكلفة."""
    from tiles import MAX_SERIES_FRAMES

    assert len(parse_series_hours(",".join(str(h) for h in range(100)))) == MAX_SERIES_FRAMES


def test_an_unparseable_request_falls_back_to_the_declared_default(parse_series_hours) -> None:
    """الافتراضيُّ مُعلَنٌ ثابتاً، فلا يُخمَّن من شكل المُدخَل."""
    from tiles import DEFAULT_SERIES_HOURS

    assert parse_series_hours("") == list(DEFAULT_SERIES_HOURS)
    assert parse_series_hours("abc,,xyz") == list(DEFAULT_SERIES_HOURS)
