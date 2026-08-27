"""READINESS-PROBES-THE-UPSTREAM-ON-EVERY-CALL-01 — جهوزيّةٌ بلا نداءٍ زائد.

**العطلُ:** `readyz` كان يستدعي `readiness_probe` — ومنه `fetch_current` — في كلّ
نداء. والمُنسِّقُ يطرق `/readyz` كلَّ ثوانٍ، فصار فحصُ «أأنا حيّ؟» يستهلك حصّةَ
المزوّد ويُقيَّد بزمنه، والخدمةُ لها مخبّأٌ يعمل بلا مزوّدٍ أصلاً.

**والعلاجُ الأوّلُ كان خاطئاً، والاختبارُ القائمُ هو ما أسقطه:** خبّأتُ نتيجةَ
المِسبار ثلاثين ثانية، فأحمرَّ `test_readyz_reports_degraded_when_open_meteo_probe_fails`
— وهو على حقّ. نجاحٌ مخبّأٌ يُخفي عطلاً منبعيّاً حتّى ينقضي أجلُه، وذلك نقضُ
الغرض الذي وُجِدت النقطةُ له. **تخفيفُ الحِمل لا يُشترى بإخفاء الأعطال.**

فالجهوزيّةُ صارت تُبنى على ما قاسته حركةُ المرور فعلاً، ولا تُنادي المزوّدَ إلّا
حين لا يكون الجوابُ معروفاً. وهذه الاختباراتُ تُثبِت الشقّين معاً: لا نداءَ حين
يكون الجوابُ معروفاً، **ولا إخفاءَ عطلٍ مقابل ذلك**.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import open_meteo  # noqa: E402
import weather_runtime as wr  # noqa: E402


def _clear_breaker_state() -> None:
    open_meteo._BREAKER_FAILURES = 0
    open_meteo._BREAKER_OPEN_UNTIL = 0.0
    open_meteo._LAST_ERROR = None
    open_meteo._LAST_SUCCESS_S = None


@pytest.fixture(autouse=True)
def _reset_breaker():
    """حالةُ القاطع عالميّةٌ في الوحدة — تُصفَّر قبل كلّ حالةٍ **وبعدها**.

    والتنظيفُ بعد الحالة ليس نظافةً زائدة: أوّلُ صياغةٍ لهذا الملفّ نظّفت قبلَ كلّ
    حالةٍ ولم تنظّف بعدها، فتسرّب `_LAST_SUCCESS_S` إلى
    `test_weather_readyz_and_cache_backend.py` وأحمرَّ اختبارٌ **قائمٌ سليم**.
    اختبارٌ يُلوّث حالةً عالميّةً يُفسِد جارَه ويبدو الجارُ هو الكاذب.
    """
    importlib.reload(open_meteo)
    _clear_breaker_state()
    yield
    _clear_breaker_state()


def _count_probes(monkeypatch) -> list[int]:
    calls = [0]

    async def counting_probe():
        calls[0] += 1
        return {"ok": True, "provider": "open-meteo"}

    monkeypatch.setattr(wr, "readiness_probe", counting_probe)
    monkeypatch.setitem(sys.modules, "main", None)
    return calls


async def _readyz():
    return await wr.readyz()


def test_a_recent_real_success_is_not_re_measured(monkeypatch):
    """نجاحٌ قاسته حركةُ المرور توّاً لا يُعاد قياسُه بنداءٍ إلى المزوّد."""
    import asyncio

    calls = _count_probes(monkeypatch)
    open_meteo._record_success()  # كأنّ طلباً حقيقيّاً نجح للتوّ
    monkeypatch.setattr(wr, "circuit_breaker_state", open_meteo.circuit_breaker_state)
    payload = asyncio.run(_readyz())
    assert payload["status"] == "ready"
    assert payload["upstream_open_meteo"]["readiness_source"] == "observed-traffic"
    assert calls[0] == 0, "نُودِيَ المزوّدُ رغم أنّ الجوابَ كان معروفاً"


def test_a_cold_service_still_measures(monkeypatch):
    """بلا مشاهدةٍ حديثة لا يُدَّعى شيء — يُقاس."""
    import asyncio

    calls = _count_probes(monkeypatch)
    monkeypatch.setattr(wr, "circuit_breaker_state", open_meteo.circuit_breaker_state)
    payload = asyncio.run(_readyz())
    assert payload["upstream_open_meteo"]["readiness_source"] == "probe"
    assert calls[0] == 1


def test_a_recorded_failure_forces_a_fresh_measurement(monkeypatch):
    """إخفاقٌ واحدٌ مُسجَّل ⇒ يُقاس الآن، ولا يُؤجَّل خلف نجاحٍ سابق.

    هذا هو الشقُّ الذي يمنع العلاجَ من أن يصير إخفاءً: نجاحٌ قديمٌ لا يُغطّي على
    تداعٍ بدأ.
    """
    import asyncio

    calls = _count_probes(monkeypatch)
    open_meteo._record_success()
    open_meteo._record_failure(RuntimeError("upstream hiccup"))
    monkeypatch.setattr(wr, "circuit_breaker_state", open_meteo.circuit_breaker_state)
    asyncio.run(_readyz())
    assert calls[0] == 1, "نجاحٌ سابقٌ غطّى على إخفاقٍ مُسجَّل"


def test_an_open_breaker_reports_degraded_without_touching_the_provider(monkeypatch):
    """القاطعُ المفتوح جوابٌ معروف: `degraded` بلا نداءٍ يُثقِل مزوّداً متداعياً."""
    import asyncio

    calls = _count_probes(monkeypatch)
    for _ in range(open_meteo.BREAKER_FAILURE_THRESHOLD):
        open_meteo._record_failure(RuntimeError("upstream down"))
    monkeypatch.setattr(wr, "circuit_breaker_state", open_meteo.circuit_breaker_state)
    payload = asyncio.run(_readyz())
    assert payload["status"] == "degraded"
    assert payload["upstream_open_meteo"]["readiness_source"] == "circuit-breaker-open"
    assert calls[0] == 0


def test_the_breaker_stamps_real_successes_only():
    """`last_success_age_s` مُشتقٌّ من نجاحٍ حقيقيّ — وبلا نجاحٍ يبقى `None`."""
    assert open_meteo.circuit_breaker_state()["last_success_age_s"] is None
    open_meteo._record_success()
    age = open_meteo.circuit_breaker_state()["last_success_age_s"]
    assert age is not None and age >= 0.0
