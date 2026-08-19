"""«latest» في الخريطة الحيّة تُربَط بيوم المشهد الحقيقيّ — لا بمزيج أقلّ غيوماً في سنة.

**العلّة المقيسة.** ``raster_cdse_tile_runtime`` يبني لـ«latest» نافذةً بعرض
``LATEST_WINDOW_DAYS`` (٣٦٥ افتراضاً) ويُسلّمها إلى ``process_index``، و``process_index``
يُرسِل ``mosaickingOrder=leastCC``. فالناتج **أقلّ المشاهد غيوماً في سنة** لا الأحدث —
ويُخزَّن ساعةً تحت مفتاح كاش مبنيّ على ``today`` (تاريخ الطلب)، بلا أيّ شاهد على تاريخ
البكسلات المعروضة.

**ولمَ هو عطل لا خيار.** مسار الإدامة ``raster_cdse_processing`` يحمل الإصلاح وتعليله
بلفظ كاتبه: *"Process API may return a least-cloud mosaic from the lookback window while
we persist acquisition_date=time_to (today), making available-dates and selected tile
dates point at the wrong COG."* فيبحث الكتالوج ثمّ يُرتّب ثمّ يضيّق إلى يوم المشهد.
والشريط الزمنيّ في الواجهة يُغذّى من هذا المسار المُصلَح. فالخريطة الحيّة والشريط
الزمنيّ كانا قد يعرضان **بكسلات يومَين مختلفين** تحت الاسم نفسه — تناقضٌ بين مسارين في
الخدمة الواحدة، لا نقصُ ميزة.

**حدّ صدق مقيس:** هذه الشريحة تربط النافذة وتُسجّل التاريخ المربوط؛ ولا تُخرِجه بعدُ في
جسم استجابة البلاطة (النقطة تُعيد بايتات صورة). فالشاهد اليوم في السجلّ لا في العقد.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services" / "raster-service"
if str(RASTER) not in sys.path:
    sys.path.insert(0, str(RASTER))

import raster_cdse_tile_runtime as runtime  # noqa: E402

pytestmark = pytest.mark.unit

_LOGGER = logging.getLogger(__name__)
_BBOX = [44.10, 15.30, 44.12, 15.32]

# مشهدان **قديمان كلاهما** عمداً: ``rank_scenes`` تقيس الحداثة مقابل «الآن» الحقيقيّ
# بنافذة تفضيل ٤٥ يوماً، فأيّ تاريخ قريب يجعل الترتيب دالّةً في يوم تشغيل الاختبار —
# أي قنبلةً زمنيّة تخضرّ اليوم وتحمرّ بعد أشهر. بتجاوز الاثنين للنافذة تتشبّع درجة
# الحداثة عند الصفر لكليهما، فتحسم الغيوم وحدها والنتيجة ثابتة أبداً.
_CLOUDY = {
    "id": "cloudy",
    "datetime": "2020-03-04T07:30:00Z",
    "properties": {"eo:cloud_cover": 38.0},
}
_CLEAN = {"id": "clean", "datetime": "2020-11-21T07:30:00Z", "properties": {"eo:cloud_cover": 2.0}}

_WIDE_FROM = "2019-01-01T00:00:00Z"
_WIDE_TO = "2021-01-01T23:59:59Z"


class _StubClient:
    """عميل يُسجّل ما سُئل عنه ثمّ يقطع المسار قبل أيّ عمل راستريّ.

    ``process_index`` يرفع عمداً: المقيس هنا هو **النافذة المُسلَّمة إليه**، وبلوغُها
    يكفي. وبهذا لا يحتاج الاختبار ``rasterio`` — وهي غير مثبَّتة في وظيفة *Unit Tests*،
    فاشتراطها كان سيُحوّل هذا الملفّ إلى تخطٍّ صامت في البوّابة (``UNIT-TEST-DORMANCY-01``).
    """

    def __init__(self, scenes=None, search_raises: Exception | None = None):
        self._scenes = scenes if scenes is not None else []
        self._search_raises = search_raises
        self.search_calls: list[dict] = []
        self.process_calls: list[dict] = []

    def search_scenes(self, **kwargs):
        self.search_calls.append(kwargs)
        if self._search_raises is not None:
            raise self._search_raises
        return self._scenes

    def process_index(self, **kwargs) -> bytes:
        self.process_calls.append(kwargs)
        raise RuntimeError("قطعٌ مقصود بعد تسجيل النافذة")


async def _drive(monkeypatch, client, date_from: str, date_to: str, today: str = "2026-08-16"):
    monkeypatch.setattr(runtime._cdse, "get_client", lambda: client)
    monkeypatch.setattr(runtime._cdse, "is_truecolor", lambda _index: False)
    result = await runtime.ensure_field_cog(
        "fld_bind",
        "ndvi",
        today,
        date_from,
        date_to,
        _BBOX,
        None,  # بلا هندسة ⇒ لا مسار قناع
        False,
        logger=_LOGGER,
    )
    return result


# ── الدوالّ النقيّة ──────────────────────────────────────────────────────────────


def test_a_single_day_window_does_not_span_multiple_days() -> None:
    assert not runtime.window_spans_multiple_days("2026-06-18T00:00:00Z", "2026-06-18T23:59:59Z"), (
        "نافذة تاريخ صريح يومٌ واحد — لو قُرِئت ممتدّةً لأضفنا بحثاً شبكيّاً بلا سبب"
    )


def test_the_latest_window_spans_multiple_days() -> None:
    assert runtime.window_spans_multiple_days(_WIDE_FROM, _WIDE_TO)


def test_binding_narrows_a_wide_window_to_the_selected_scene_day() -> None:
    """الضمانة المركزيّة: نافذة السنتين تنكمش إلى يوم المشهد المختار."""
    date_from, date_to, selected = runtime.bind_scene_day_window(
        [_CLOUDY, _CLEAN], _WIDE_FROM, _WIDE_TO
    )
    assert (date_from, date_to) == ("2020-11-21T00:00:00Z", "2020-11-21T23:59:59Z")
    assert selected is not None
    assert selected.acquisition_datetime == "2020-11-21T07:30:00Z"
    assert selected.acquisition_day == "2020-11-21"


def test_binding_obeys_the_policy_not_the_list_order() -> None:
    """المشهد الخاسر أوّلاً في القائمة — ومع ذلك لا يفوز بموضعه.

    لو قرأ الربط ``scenes[0]`` لمرّ كلّ اختبارٍ آخر هنا، لأنّ الترتيب مصادفةً يضع
    الفائز أوّلاً في بقيّتها.

    **حدّ مقيس:** هذه الحالة لا تُميّز بين «الأحدث» و«أفضل جودة» — فـ``_CLEAN`` هنا
    هو الأحدث **والأنظف** معاً، فتتّفق السياستان عليه. التمييز بينهما يقع في
    ``test_cdse_latest_selection_semantics.py`` على مُدخَل يفترقان عليه فعلاً.
    """
    _from, _to, selected = runtime.bind_scene_day_window([_CLOUDY, _CLEAN], _WIDE_FROM, _WIDE_TO)
    assert selected is not None and selected.acquisition_day == "2020-11-21"


def test_binding_fails_open_when_no_scene_is_returned() -> None:
    """بلا مشاهد ⇒ النافذة كما جاءت. الربط تحسينُ صدقٍ لا شرطُ صلاحيّة."""
    assert runtime.bind_scene_day_window([], _WIDE_FROM, _WIDE_TO) == (_WIDE_FROM, _WIDE_TO, None)
    assert runtime.bind_scene_day_window(None, _WIDE_FROM, _WIDE_TO) == (_WIDE_FROM, _WIDE_TO, None)


def test_binding_fails_open_on_an_unusable_acquisition_datetime() -> None:
    scene = {"id": "x", "datetime": None, "properties": {"datetime": "لا-تاريخ"}}
    assert runtime.bind_scene_day_window([scene], _WIDE_FROM, _WIDE_TO) == (
        _WIDE_FROM,
        _WIDE_TO,
        None,
    )


def test_binding_reads_the_acquisition_datetime_from_properties_when_absent_at_top_level() -> None:
    """المشهد بلا ``datetime`` عُلويّ — والتاريخ في ``properties`` كما تُعيده بعض ردود STAC."""
    scene = {"id": "x", "properties": {"datetime": "2020-11-21T07:30:00Z"}}
    _from, _to, selected = runtime.bind_scene_day_window([scene], _WIDE_FROM, _WIDE_TO)
    assert selected is not None
    assert selected.acquisition_datetime == "2020-11-21T07:30:00Z"


def test_binding_survives_properties_present_but_null() -> None:
    """``properties: None`` حاضرةٌ بقيمة عدميّة — و``get("properties", {})`` وحدها تنفجر.

    الافتراضيّ لا يُستعمَل حين يكون المفتاح **موجوداً**، فتُمرَّر ``None`` إلى ``.get``
    التالية. و``rank_scenes`` **لا تُطبّع** هذا الحقل (مقيس)، فالقيمة تصل كما جاءت.

    **ولا بدّ من غياب ``datetime`` العُلويّ هنا:** ``or`` تقصر الدارة، فلو حضر التاريخ
    عُلويّاً لما قُرِئت ``properties`` أصلاً ولمرّ الاختبار على عطبٍ قائم — وهو ما وقع
    في صياغتي الأولى وكشفه التكذيب لا القراءة.
    """
    scene = {"id": "x", "properties": None}
    assert runtime.bind_scene_day_window([scene], _WIDE_FROM, _WIDE_TO) == (
        _WIDE_FROM,
        _WIDE_TO,
        None,
    )


# ── المسار الموصول ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_live_path_processes_the_scene_day_not_the_lookback_window(monkeypatch) -> None:
    """برهان الوصل: ``process_index`` يتلقّى يوم المشهد، لا نافذة الاسترجاع.

    الدالّة النقيّة وحدها لا تكفي — دالّة صحيحة غير مستدعاة تُبقي العطل قائماً.
    """
    client = _StubClient(scenes=[_CLOUDY, _CLEAN])
    await _drive(monkeypatch, client, _WIDE_FROM, _WIDE_TO)

    assert len(client.search_calls) == 1, "النافذة الممتدّة يجب أن تُسأل عن مشهدها"
    assert client.process_calls, "لم يبلغ المسار المعالجة أصلاً"
    sent = client.process_calls[0]
    assert sent["time_from"] == "2020-11-21T00:00:00Z"
    assert sent["time_to"] == "2020-11-21T23:59:59Z"


@pytest.mark.asyncio
async def test_the_search_and_the_processing_ask_for_the_same_cloud_ceiling(monkeypatch) -> None:
    """سقفان مختلفان ⇒ نربط بيوم مشهدٍ سترفضه المعالجة، فنعود بفراغ حيث كانت صورة."""
    client = _StubClient(scenes=[_CLEAN])
    await _drive(monkeypatch, client, _WIDE_FROM, _WIDE_TO)

    assert client.search_calls[0]["max_cloud_pct"] == client.process_calls[0]["max_cloud_pct"]


@pytest.mark.asyncio
async def test_an_explicit_historical_date_is_not_searched_again(monkeypatch) -> None:
    """تاريخ صريح نافذتُه يومٌ سلفاً — فالبحث عليه نداء شبكيّ زائد على كلّ بطاقة.

    وهو أيضاً الاتّجاه الذي يمنع الإفراط: لو رُبِط كلّ طلب، لصار التاريخ المختار
    يُعاد تفسيره — وهو التلويث الذي تتجنّبه هذه الشريحة عمداً.
    """
    client = _StubClient(scenes=[_CLEAN])
    await _drive(monkeypatch, client, "2026-06-18T00:00:00Z", "2026-06-18T23:59:59Z")

    assert client.search_calls == [], "لا بحث لتاريخ صريح"
    assert client.process_calls[0]["time_from"] == "2026-06-18T00:00:00Z"
    assert client.process_calls[0]["time_to"] == "2026-06-18T23:59:59Z"


@pytest.mark.asyncio
async def test_a_failing_catalog_search_fails_closed(monkeypatch) -> None:
    """C7 (IMAGERY-LATEST-CANONICAL-SCENE-BINDING-01) يُغلِق الدَّين المُعلَن أعلاه:
    انقطاع الكتالوج لم يعد يُعيدنا إلى «سلوك ما قبل الشريحة» (معالجة النافذة الواسعة
    تحت اسم latest) — بل يفشل مُغلَقاً بلا معالجة، تفضيلاً لبلاطة مفقودة على بلاطة
    مُسمّاة «الأحدث» وهي ليست كذلك.
    """
    client = _StubClient(search_raises=RuntimeError("الكتالوج منقطع"))
    result = await _drive(monkeypatch, client, _WIDE_FROM, _WIDE_TO)

    assert result is None
    assert len(client.search_calls) == 1
    assert client.process_calls == [], (
        "فشل البحث يجب ألّا يُفضي إلى معالجة نافذة واسعة تحت اسم latest"
    )
