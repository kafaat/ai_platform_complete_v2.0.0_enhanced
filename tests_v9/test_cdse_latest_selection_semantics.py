"""فصل سلطتَي الاختيار: «أحدث اكتساب مقبول» ليست «أعلى جودة».

**الجذر المقيس (IMAGERY-LATEST-SELECTION-SEMANTICS-02).** كانت المنصّة تنفّذ دلالة
«الأحدث» بـ``rank_scenes`` — وأوزانُها ٠٫٥٠ سحاب مقابل ٠٫٢٠ حداثة، فيهزم **الأقدمُ
الأنظفُ الأحدثَ**. ذلك جوابٌ صحيح لسؤال «أفضل جودة» وخاطئ لسؤال «الأحدث». وفوقه
عطبان في اكتشاف المشاهد نفسه:

  * ``search_scenes`` كان يحمل **تعليقين** يدّعيان ترتيباً زمنيّاً «يُطبَّق أدناه»
    ولا وجود لأيّ ``sort`` في الدالّة — ادّعاءٌ بلا شاهد بُنِي عليه مستهلكون.
  * ولا ترقيم صفحات (``context.next``) رغم أنّ الكتالوج مُرقَّم؛ فمع ``limit=10`` على
    نافذة استرجاع واسعة يصير الجواب «أفضل مشهد من صفحةٍ جزئيّة صادف أن أعادها
    المزوّد» — لا الأحدث ولا الأفضل في النافذة.

هذه الحالات هي بوّابة الخروج: كلٌّ منها يفشل على الشجرة قبل هذه الشريحة.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services" / "raster-service"
if str(RASTER) not in sys.path:
    sys.path.insert(0, str(RASTER))

import cdse_client  # noqa: E402
import raster_cdse_tile_runtime as runtime  # noqa: E402
import scene_policy as sp  # noqa: E402

pytestmark = pytest.mark.unit

POLICY = sp.SceneSelectionPolicy

# تواريخ بعيدة عمداً: ``rank_scenes`` تقيس الحداثة مقابل «الآن» الحقيقيّ، فتاريخٌ
# قريب يجعل المقارنة دالّةً في يوم التشغيل — قنبلةٌ زمنيّة. بتجاوز نافذة التفضيل
# تتشبّع درجة الحداثة لكليهما وتحسم بقيّةُ الأوزان، فالنتيجة ثابتة أبداً.
NEWER_DIRTIER = {
    "id": "newer-dirtier",
    "datetime": "2020-11-21T07:30:00Z",
    "properties": {"eo:cloud_cover": 35.0},
}
OLDER_CLEANER = {
    "id": "older-cleaner",
    "datetime": "2020-03-04T07:30:00Z",
    "properties": {"eo:cloud_cover": 1.0},
}
NEWEST_OVER_CEILING = {
    "id": "newest-over-ceiling",
    "datetime": "2020-12-01T07:30:00Z",
    "properties": {"eo:cloud_cover": 90.0},
}


# ── ١) السلطتان تفترقان على المُدخل نفسه ────────────────────────────────────────


def test_latest_prefers_the_newest_even_when_an_older_scene_is_cleaner() -> None:
    """الحالة المركزيّة. لو نُفِّذت هذه السياسة بـ``rank_scenes`` لفاز الأقدم الأنظف."""
    selected = sp.select_scene(
        [OLDER_CLEANER, NEWER_DIRTIER], policy=POLICY.LATEST_ACCEPTABLE, max_cloud_pct=40.0
    )
    assert selected is not None
    assert selected.scene_id == "newer-dirtier"
    assert selected.acquisition_day == "2020-11-21"
    assert selected.policy == "latest_acceptable"


def test_best_quality_prefers_the_cleaner_scene_on_the_same_input() -> None:
    """الاتّجاه المقابل — وبدونه لا يُثبَت أنّ السياستين **مختلفتان** لا مجرّد مسمّيين."""
    selected = sp.select_scene(
        [OLDER_CLEANER, NEWER_DIRTIER], policy=POLICY.BEST_QUALITY, max_cloud_pct=40.0
    )
    assert selected is not None
    assert selected.scene_id == "older-cleaner"
    assert selected.policy == "best_quality"


def test_latest_still_honours_the_explicit_cloud_ceiling() -> None:
    """«الأحدث» مقيَّدة بـ«المقبول»: الأحدث فوق السقف يُرفَض ويفوز السابق."""
    selected = sp.select_scene(
        [NEWEST_OVER_CEILING, NEWER_DIRTIER], policy=POLICY.LATEST_ACCEPTABLE, max_cloud_pct=40.0
    )
    assert selected is not None
    assert selected.scene_id == "newer-dirtier"


def test_selection_is_independent_of_provider_order() -> None:
    """ترتيب المزوّد غير موثَّق ولا مضمون الثبات — فلا يجوز أن يقرّر."""
    forward = sp.select_scene(
        [OLDER_CLEANER, NEWER_DIRTIER, NEWEST_OVER_CEILING],
        policy=POLICY.LATEST_ACCEPTABLE,
        max_cloud_pct=40.0,
    )
    reverse = sp.select_scene(
        [NEWEST_OVER_CEILING, NEWER_DIRTIER, OLDER_CLEANER],
        policy=POLICY.LATEST_ACCEPTABLE,
        max_cloud_pct=40.0,
    )
    assert forward == reverse


def test_a_malformed_acquisition_datetime_never_wins() -> None:
    """«الأحدث» بلا زمنٍ موثوق لا معنى له — فالتاريخ الفاسد لا يُرشَّح أصلاً."""
    broken = {"id": "broken", "datetime": "لا-تاريخ", "properties": {"eo:cloud_cover": 0.0}}
    selected = sp.select_scene(
        [broken, OLDER_CLEANER], policy=POLICY.LATEST_ACCEPTABLE, max_cloud_pct=40.0
    )
    assert selected is not None and selected.scene_id == "older-cleaner"
    assert sp.select_scene([broken], policy=POLICY.LATEST_ACCEPTABLE) is None


def test_unknown_cloud_stays_eligible_and_says_so_in_the_receipt() -> None:
    """يتبع سياسة المنصّة القائمة لا سياسةً ثانية.

    ``cdse_client._apply_cloud_filter`` يقبل المشهد مجهولَ الغيوم بقرار مالك موثَّق
    («غياب ≠ صفر» مع رصد صريح). فلو رفضه المنتقي لصارت للأهليّة سلطتان تنحرفان.
    والإيصال يُعلِن الجهل بدل أن يُخفيه تحت صفر.
    """
    unknown = {"id": "unknown-cloud", "datetime": "2020-12-05T07:30:00Z", "properties": {}}
    selected = sp.select_scene([unknown], policy=POLICY.LATEST_ACCEPTABLE, max_cloud_pct=40.0)
    assert selected is not None
    assert selected.cloud_pct is None
    assert selected.cloud_source == "unknown"


def test_the_receipt_carries_identity_not_just_a_date() -> None:
    """``tuple`` من ثلاثة نصوص كانت تفقد ``scene_id`` والغيوم ومصدرها عند الحدّ."""
    receipt = sp.select_scene([NEWER_DIRTIER], policy=POLICY.LATEST_ACCEPTABLE).as_receipt()
    assert receipt["scene_id"] == "newer-dirtier"
    assert receipt["acquisition_datetime"] == "2020-11-21T07:30:00Z"
    assert receipt["acquisition_day"] == "2020-11-21"
    assert receipt["selection_policy"] == "latest_acceptable"
    assert receipt["policy_version"] == sp.SELECTION_POLICY_VERSION
    assert receipt["source"] == "cdse"


# ── ٢) ترقيم صفحات الكتالوج ─────────────────────────────────────────────────────


class _PagedResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self) -> dict:
        return self._payload


def _feature(scene_id: str, day: str, cloud: float) -> dict:
    return {
        "id": scene_id,
        "properties": {"datetime": f"{day}T07:30:00Z", "eo:cloud_cover": cloud},
    }


def test_catalog_search_follows_pagination_to_the_next_page(monkeypatch) -> None:
    """أحدث مشهد في الصفحة **الثانية** — وبلا تتبّع ``context.next`` لا يُرى إطلاقاً.

    هذا الاتّجاه هو ما يجعل ادّعاء «الأحدث» قابلاً للإثبات: بلا الترقيم يكون الجواب
    «أفضل ما في الصفحة الأولى» ويُقدَّم بوصفه أفضل ما في النافذة.
    """
    pages = [
        {
            "features": [_feature("page1-old", "2020-03-04", 5.0)],
            "context": {"next": "token-2"},
        },
        {"features": [_feature("page2-new", "2020-11-21", 5.0)], "context": {}},
    ]
    seen: list[dict] = []

    def _fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        seen.append(json or {})
        return _PagedResponse(pages[len(seen) - 1])

    import httpx

    monkeypatch.setattr(httpx, "post", _fake_post)
    client = cdse_client.CdseClient()
    monkeypatch.setattr(client, "token", lambda: "t")

    scenes = client.search_scenes(
        bbox=[44.10, 15.30, 44.12, 15.32],
        time_from="2020-01-01T00:00:00Z",
        time_to="2021-01-01T23:59:59Z",
    )
    ids = {s.get("id") for s in scenes}
    assert ids == {"page1-old", "page2-new"}, "الصفحة الثانية لم تُطلَب"
    assert seen[1].get("next") == "token-2", "رمز الصفحة التالية لم يُرسَل"

    selected = sp.select_scene(scenes, policy=POLICY.LATEST_ACCEPTABLE, max_cloud_pct=40.0)
    assert selected is not None and selected.scene_id == "page2-new"


def test_catalog_search_stops_at_the_page_ceiling(monkeypatch) -> None:
    """مزوّدٌ يُعيد ``next`` بلا نهاية يجب أن يتوقّف عندنا لا أن يستنزف الطلب."""
    calls = {"n": 0}

    def _endless_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        calls["n"] += 1
        return _PagedResponse(
            {
                "features": [_feature(f"s{calls['n']}", "2020-05-05", 5.0)],
                "context": {"next": f"tok-{calls['n']}"},
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", _endless_post)
    client = cdse_client.CdseClient()
    monkeypatch.setattr(client, "token", lambda: "t")
    client.search_scenes(
        bbox=[44.10, 15.30, 44.12, 15.32],
        time_from="2020-01-01T00:00:00Z",
        time_to="2021-01-01T23:59:59Z",
    )
    assert calls["n"] == cdse_client._CATALOG_MAX_PAGES


# ── ٣) اتّفاق آخر خطوة مع العقد ─────────────────────────────────────────────────


def test_an_unknown_mosaicking_order_is_rejected_not_passed_through() -> None:
    """قيمةٌ مجهولة قد يتجاهلها المزوّد فيعود إلى افتراضه — دلالةٌ غير مطلوبة بلا إشارة."""
    with pytest.raises(ValueError):
        cdse_client._validated_mosaicking_order("newest")
    assert cdse_client._validated_mosaicking_order(cdse_client.MOSAIC_MOST_RECENT) == "mostRecent"


class _RecordingClient:
    def __init__(self, scenes):
        self._scenes = scenes
        self.process_calls: list[dict] = []

    def search_scenes(self, **_kwargs):
        return self._scenes

    def process_index(self, **kwargs) -> bytes:
        self.process_calls.append(kwargs)
        raise RuntimeError("قطعٌ مقصود بعد تسجيل الطلب")


@pytest.mark.asyncio
async def test_the_live_path_asks_for_most_recent_once_it_bound_a_scene(monkeypatch) -> None:
    """العقد اتّفق: اخترنا «أحدث اكتساب» فيجب أن تُطلَب الفسيفساء ``mostRecent``.

    بقاء ``leastCC`` بعد التضييق كان يُبقي آخر خطوة تتكلّم دلالةً غير التي اختارت
    المشهد — وهو الخلط نفسه بمقياس أصغر.
    """
    client = _RecordingClient([OLDER_CLEANER, NEWER_DIRTIER])
    monkeypatch.setattr(runtime._cdse, "get_client", lambda: client)
    monkeypatch.setattr(runtime._cdse, "is_truecolor", lambda _index: False)
    await runtime.ensure_field_cog(
        "fld_sem",
        "ndvi",
        "2026-08-16",
        "2019-01-01T00:00:00Z",
        "2021-01-01T23:59:59Z",
        [44.10, 15.30, 44.12, 15.32],
        None,
        False,
        logger=__import__("logging").getLogger(__name__),
    )
    sent = client.process_calls[0]
    assert sent["mosaicking_order"] == cdse_client.MOSAIC_MOST_RECENT
    assert sent["time_from"] == "2020-11-21T00:00:00Z"


@pytest.mark.asyncio
async def test_an_unbound_window_does_not_claim_most_recent(monkeypatch) -> None:
    """تعذّر الاختيار ⇒ نبقى على ``leastCC`` ولا ندّعي دلالةً لم نُنفّذها.

    **حدّ صدق مقيس:** هذه الحالة تُثبِت أنّنا لا **نكذب** في وسيط الفسيفساء؛ ولا
    تُثبِت أنّ الناتج «latest». تقديمُ نافذة واسعة تحت اسم latest عند العطل دَينُ
    انتقال مُعلَن في `IMAGERY-LATEST-CANONICAL-SCENE-BINDING-01`، يُغلَق بتدهور
    توافريّة صريح لا بتلفيق دلاليّ.
    """
    client = _RecordingClient([])
    monkeypatch.setattr(runtime._cdse, "get_client", lambda: client)
    monkeypatch.setattr(runtime._cdse, "is_truecolor", lambda _index: False)
    await runtime.ensure_field_cog(
        "fld_sem2",
        "ndvi",
        "2026-08-16",
        "2019-01-01T00:00:00Z",
        "2021-01-01T23:59:59Z",
        [44.10, 15.30, 44.12, 15.32],
        None,
        False,
        logger=__import__("logging").getLogger(__name__),
    )
    sent = client.process_calls[0]
    assert sent["mosaicking_order"] == cdse_client.MOSAIC_LEAST_CLOUD
    assert sent["time_from"] == "2019-01-01T00:00:00Z"


# ── ٤) تكافؤ المسارين على الدلالة الصحيحة ───────────────────────────────────────


def test_the_live_binder_agrees_with_the_central_selector() -> None:
    """المسار الحيّ لا يحمل منتقياً ثانياً — يومُه هو يومُ المنتقي المركزيّ."""
    scenes = [OLDER_CLEANER, NEWER_DIRTIER, NEWEST_OVER_CEILING]
    _from, _to, selected = runtime.bind_scene_day_window(
        scenes, "2019-01-01T00:00:00Z", "2021-01-01T23:59:59Z"
    )
    central = sp.select_scene(
        scenes, policy=POLICY.LATEST_ACCEPTABLE, max_cloud_pct=runtime.MAX_CLOUD_PCT
    )
    assert selected == central
    assert _from == "2020-11-21T00:00:00Z"


def test_the_persisted_path_consumes_the_same_policy() -> None:
    """حارس مصدريّ مُعلَن كذلك.

    تسييرُ ``run_cdse_processing`` يحتاج تطبيق FastAPI حيّاً (``ctx``) وليس متاحاً في
    ``-m unit``؛ فبدل ادّعاء تكافؤ سلوكيّ لا أقيسه، أُثبِت الشرط الضروريّ: هذا المسار
    يستدعي المنتقي المركزيّ بالسياسة نفسها ولا يحمل ``rank_scenes(...)[0]`` بعد.
    """
    src = (RASTER / "raster_cdse_processing.py").read_text(encoding="utf-8")
    assert "SceneSelectionPolicy.LATEST_ACCEPTABLE" in src
    # التعليقات تُنزَع قبل الفحص: صياغتي الأولى طابقت **تعليقي أنا** الذي يشرح ما
    # أُزيل، فأحمرّت على نصٍّ لا على سلوك. الحارس المصدريّ يقرأ الكود لا الشرح.
    code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))
    assert "rank_scenes(" not in code, "المسار المُدام ما زال ينتقي بسياسة الجودة"


def test_the_catalog_client_no_longer_claims_a_sort_it_does_not_do() -> None:
    """التعليق الذي يصف سلوكاً غير موجود هو صنف «ادّعاء بلا شاهد» — وقد بُنِي عليه."""
    src = (RASTER / "cdse_client.py").read_text(encoding="utf-8")
    assert "Client-side date sorting is applied below" not in src, (
        "فرزٌ زبونيّ بعد الربط يعيد خلط «الأحدث» بـ«الأفضل» الذي فصلته هذه الشريحة — "
        "الاختيار سلطة select_scene وحدها، وأيّ إعادة فرزٍ لاحقة تلغي إيصالها"
    )
    assert "Client-side cloud/date sorting still" not in src, (
        "بقايا الفرز الزبونيّ القديم ممنوعة عمداً: كانت تقدّم «أفضل ما في الصفحة الأولى» "
        "بوصفه أحدث المقبول — المسار الآن على المنتقي المركزيّ بإيصاله"
    )


# ── ٥) الاستجواب من الأحدث إلى الأقدم ──────────────────────────────────────────


def test_probe_windows_run_newest_first_and_cover_the_whole_span() -> None:
    """الترتيب هو الضمانة: أوّل نافذة تُثمِر تحسم لأنّ ما بعدها أقدم بالبناء."""
    windows = runtime.backward_probe_windows(
        "2020-01-01T00:00:00Z", "2020-03-01T23:59:59Z", step_days=30
    )
    # المدى ٦٠ يوماً والخطوة ٣٠ ⇒ نافذتان على الأقلّ. بلا هذا التأكيد يمرّ الاختبار
    # على تنفيذٍ يُعيد **نافذةً واحدة** تغطّي المدى كلّه — وهو عين ما تُلغيه الشريحة.
    # كشفه زرعُ العطب، لا قراءةُ الاختبار.
    assert len(windows) > 1, "لم يُقسَّم المدى إلى نوافذ"
    assert windows[0][1].startswith("2020-03-01"), "لم تبدأ من الأحدث"
    assert windows[-1][0].startswith("2020-01-01"), "لم تبلغ الحدّ الأقدم"
    # بلا ثغرة: بداية كلّ نافذة هي نهاية التالية الأقدم. الإزاحة بمقدار واحد تجعل
    # القائمتين مختلفتَي الطول بالبناء، فـ``strict=True`` عليهما خطأ في الاختبار لا
    # في المقيس (وقد وقعتُ فيه).
    for index in range(len(windows) - 1):
        assert windows[index][0][:10] == windows[index + 1][1][:10]


def test_probe_windows_never_reach_below_the_declared_floor() -> None:
    """قسمةٌ غير متساوية يجب ألّا تُنزِل النافذة الأخيرة تحت المدى المطلوب."""
    windows = runtime.backward_probe_windows(
        "2020-01-01T00:00:00Z", "2020-02-14T23:59:59Z", step_days=30
    )
    assert min(w[0] for w in windows)[:10] == "2020-01-01"


def test_probe_windows_degrade_to_one_window_on_unusable_input() -> None:
    """خطوةٌ غير موجبة أو تاريخٌ فاسد ⇒ نافذةٌ واحدة كما جاءت، لا حلقة لانهائيّة."""
    span = ("2020-01-01T00:00:00Z", "2020-03-01T23:59:59Z")
    assert runtime.backward_probe_windows(*span, step_days=0) == [span]
    assert runtime.backward_probe_windows("لا-تاريخ", span[1]) == [("لا-تاريخ", span[1])]


class _WindowRecordingClient:
    """يُعيد المشهد في نافذةٍ **قديمة** فقط، ويُسجّل كلّ نافذة سُئل عنها."""

    def __init__(self, answer_day: str | None):
        self._answer_day = answer_day
        self.windows: list[tuple[str, str]] = []
        self.process_calls: list[dict] = []

    def search_scenes(self, *, time_from, time_to, **_kw):
        self.windows.append((time_from, time_to))
        if self._answer_day and time_from[:10] <= self._answer_day <= time_to[:10]:
            return [_feature("hit", self._answer_day, 5.0)]
        return []

    def process_index(self, **kwargs) -> bytes:
        self.process_calls.append(kwargs)
        raise RuntimeError("قطعٌ مقصود بعد تسجيل الطلب")


@pytest.mark.asyncio
async def test_the_live_path_stops_at_the_first_window_that_yields(monkeypatch) -> None:
    """لا ينزل إلى الأقدم بعد أن وجد — وهو ما يجعل «الأحدث» مُثبَتاً لا مُرجَّحاً."""
    import datetime as _dt
    import logging

    today = _dt.datetime.now(_dt.UTC)
    recent_day = (today - _dt.timedelta(days=3)).strftime("%Y-%m-%d")
    client = _WindowRecordingClient(recent_day)
    monkeypatch.setattr(runtime._cdse, "get_client", lambda: client)
    monkeypatch.setattr(runtime._cdse, "is_truecolor", lambda _index: False)

    wide_from = (today - _dt.timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z")
    wide_to = today.strftime("%Y-%m-%dT23:59:59Z")
    await runtime.ensure_field_cog(
        "fld_probe",
        "ndvi",
        today.strftime("%Y-%m-%d"),
        wide_from,
        wide_to,
        [44.10, 15.30, 44.12, 15.32],
        None,
        False,
        logger=logging.getLogger(__name__),
    )
    assert len(client.windows) == 1, f"نزل إلى نوافذ أقدم بلا داعٍ: {client.windows}"
    assert client.process_calls[0]["time_from"].startswith(recent_day)
    assert client.process_calls[0]["mosaicking_order"] == cdse_client.MOSAIC_MOST_RECENT


@pytest.mark.asyncio
async def test_the_live_path_walks_back_when_recent_windows_are_empty(monkeypatch) -> None:
    """نافذةٌ فارغة لا تُنهي البحث — تُستجوَب الأقدم منها حتّى حدّ الاسترجاع."""
    import datetime as _dt
    import logging

    today = _dt.datetime.now(_dt.UTC)
    old_day = (today - _dt.timedelta(days=100)).strftime("%Y-%m-%d")
    client = _WindowRecordingClient(old_day)
    monkeypatch.setattr(runtime._cdse, "get_client", lambda: client)
    monkeypatch.setattr(runtime._cdse, "is_truecolor", lambda _index: False)

    await runtime.ensure_field_cog(
        "fld_probe2",
        "ndvi",
        today.strftime("%Y-%m-%d"),
        (today - _dt.timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z"),
        today.strftime("%Y-%m-%dT23:59:59Z"),
        [44.10, 15.30, 44.12, 15.32],
        None,
        False,
        logger=logging.getLogger(__name__),
    )
    assert len(client.windows) > 1, "لم ينزل إلى نافذة أقدم"
    assert client.process_calls[0]["time_from"].startswith(old_day)


def test_pagination_after_fallback_uses_the_accepted_payload(monkeypatch) -> None:
    """مراجعة #859 أصابت: إن رُفض الـpayload الكامل ونجح ``_minimal_fallback``،
    فطلبُ الصفحة التالية يجب أن يُبنى من الـpayload **المقبول** — لا من الأصليّ
    المرفوض الذي سيُرفَض ثانيةً فيتوقّف الجمع عند الصفحة الأولى بنقصٍ مُعلَنٍ
    كان يمكن تفاديه."""
    pages = {
        2: {"features": [_feature("fb-page1", "2020-03-04", 5.0)], "context": {"next": "tok-2"}},
        3: {"features": [_feature("fb-page2", "2020-11-21", 5.0)], "context": {}},
    }
    seen: list[dict] = []

    def _post(url, json=None, headers=None, timeout=None):  # noqa: A002
        seen.append(dict(json or {}))
        if len(seen) == 1:
            return _PagedResponse({}, status_code=400)
        return _PagedResponse(pages[len(seen)])

    import httpx

    monkeypatch.setattr(httpx, "post", _post)
    client = cdse_client.CdseClient()
    monkeypatch.setattr(client, "token", lambda: "t")

    scenes = client.search_scenes(
        bbox=[44.10, 15.30, 44.12, 15.32],
        time_from="2020-01-01T00:00:00Z",
        time_to="2021-01-01T23:59:59Z",
    )
    assert {s.get("id") for s in scenes} == {"fb-page1", "fb-page2"}
    fallback_payload = seen[1]
    expected_page2 = dict(fallback_payload)
    expected_page2["next"] = "tok-2"
    assert seen[2] == expected_page2, "الصفحة التالية لم تُبْنَ من الـpayload المقبول"
