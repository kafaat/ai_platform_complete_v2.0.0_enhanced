"""نبضةُ عمّال الطقس تفشل مغلقةً — ``WEATHER-HEARTBEAT-01``.

الفحصُ الذي يشهد بصحّةٍ لم يقسها أسوأ من غياب فحص: غيابُه يُقرأ «لا نعرف»، وخُضرتُه
الكاذبة تُقرأ «نعرف أنّه سليم». وثلاثةُ أسئلةٍ كانت مخلوطةً هنا، وكلٌّ منها كان
يشهد للآخر:

* **هل العمليّة أقلعت؟** — يجيب عنه ملفّ الجاهزيّة، ويُكتَب مرّةً ولا يُحدَّث.
* **هل الحلقة تتحرّك الآن؟** — تجيب عنه النبضة وحدها.
* **هل البيانات طازجة؟** — لا يجيب عنه أيٌّ منهما، ولا يدّعيه هذا الملفّ.

والتمييز مقيس لا نظريّ: ``.env.example`` يشحن ``WEATHER_SIGNAL_INTERVAL_SEC=3600``
بينما كان السقف ثابتاً عند ١٨٠ ثانية — فالنبضة تبيت **٩٥٪ من كلّ ساعة** على عاملٍ
سليمٍ تماماً. سقفٌ لا يُشتقّ من كادنس المنتِج يقيس دقّة الجدولة لا الحياة.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PROBES = (
    "services/weather-signal-engine/worker_health_probe.py",
    "services/weather-polygon-worker/worker_health_probe.py",
)


def _probe(monkeypatch, tmp_path: Path, **env: str):
    """يُحمَّل بعد ضبط البيئة: الثوابت تُقرأ وقتَ الاستيراد كما في الحاوية."""
    monkeypatch.setenv("WORKER_READY_FILE", str(tmp_path / "ready"))
    monkeypatch.setenv("WORKER_HEARTBEAT_FILE", str(tmp_path / "beat"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("weather_probe_under_test", ROOT / PROBES[0])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ready(tmp_path: Path) -> None:
    (tmp_path / "ready").write_text("1", encoding="utf-8")


def _beat(tmp_path: Path, age_seconds: float = 0.0) -> None:
    import os
    import time

    path = tmp_path / "beat"
    path.write_text("1", encoding="utf-8")
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


# ── الحالة السعيدة تبقى سعيدة ────────────────────────────────────────────────


def test_a_fresh_heartbeat_on_a_started_worker_is_ready(monkeypatch, tmp_path):
    module = _probe(monkeypatch, tmp_path)
    _ready(tmp_path)
    _beat(tmp_path, age_seconds=5)
    ok, reason = module.check()
    assert ok is True, reason


# ── ① غيابُ النبضة: الفشلُ مغلقاً ─────────────────────────────────────────────


def test_a_missing_heartbeat_is_not_ready(monkeypatch, tmp_path):
    """الصيغةُ السابقة كانت تمرّ هنا: `exists() and <بائتة>` تقصر دائرتها.

    فيبقى المطلوبُ الوحيد ملفَّ الجاهزيّة — وهو يُكتَب مرّةً عند الإقلاع ولا
    يُحدَّث. أي أنّ الفحص كان يقيس «أقلعت مرّةً» ويُعلِنها «تعمل الآن».
    """
    module = _probe(monkeypatch, tmp_path)
    _ready(tmp_path)
    ok, reason = module.check()
    assert ok is False
    assert "heartbeat file missing" in reason


def test_the_ready_file_alone_never_certifies_liveness(monkeypatch, tmp_path):
    """ملفّ الجاهزيّة شاهدُ إقلاعٍ لا شاهدَ حياة — فلا يُقبَل بديلاً عن النبضة."""
    module = _probe(monkeypatch, tmp_path)
    _ready(tmp_path)
    assert module.check()[0] is False
    _beat(tmp_path, age_seconds=1)
    assert module.check()[0] is True


def test_a_missing_ready_file_is_not_ready(monkeypatch, tmp_path):
    module = _probe(monkeypatch, tmp_path)
    _beat(tmp_path, age_seconds=1)
    ok, reason = module.check()
    assert ok is False
    assert "ready file missing" in reason


# ── ② ختمٌ في المستقبل: اختلافُ الساعات غيابُ دليلٍ لا دليلُ صحّة ──────────────


def test_a_future_dated_heartbeat_is_not_ready(monkeypatch, tmp_path):
    """`now - mtime > MAX_AGE` تصير سالبةً فلا تتجاوز أيّ سقف — ويبقى الفحص
    أخضرَ حتّى يلحق الزمنُ الحقيقيّ بالختم."""
    module = _probe(monkeypatch, tmp_path)
    _ready(tmp_path)
    _beat(tmp_path, age_seconds=-3600)
    ok, reason = module.check()
    assert ok is False
    assert "future" in reason


def test_a_few_seconds_of_clock_skew_is_tolerated(monkeypatch, tmp_path):
    """انحرافُ ثوانٍ بين الكتابة والقراءة ليس عطلاً — وإلّا صار الحارس هشّاً."""
    module = _probe(monkeypatch, tmp_path)
    _ready(tmp_path)
    _beat(tmp_path, age_seconds=-2)
    assert module.check()[0] is True


# ── ③ البياتُ الحقيقيّ ما يزال يُرصَد ─────────────────────────────────────────


def test_a_genuinely_stale_heartbeat_is_not_ready(monkeypatch, tmp_path):
    """«يعمل لكنّه بائت» — العمليّةُ حيّة والحلقة متوقّفة. لا يجوز أن يمرّ."""
    module = _probe(monkeypatch, tmp_path, WORKER_HEALTH_MAX_AGE_SEC="180")
    _ready(tmp_path)
    _beat(tmp_path, age_seconds=10_000)
    ok, reason = module.check()
    assert ok is False
    assert "stale" in reason


# ── ④ السقفُ يُشتقّ من كادنس المنتِج ──────────────────────────────────────────


def test_the_bound_is_derived_from_the_declared_cadence(monkeypatch, tmp_path):
    """سقفٌ أقصر من الدورة يجعل النبضة بائتةً في وضعها **الطبيعيّ**.

    مقيس على المشحون: `.env.example` يضبط الدورة على ٣٦٠٠ ثانية والسقف الثابت
    ١٨٠ — أي عاملٌ سليمٌ يُعلَن مريضاً ٩٥٪ من كلّ ساعة.
    """
    module = _probe(monkeypatch, tmp_path, WORKER_HEARTBEAT_CADENCE_SEC="3600")
    assert module.effective_max_age() == 2 * 3600 + 60
    _ready(tmp_path)
    _beat(tmp_path, age_seconds=3500)
    assert module.check()[0] is True, "دورةٌ واحدة لم تكتمل بعد — ليس بياتاً"


def test_a_cadence_shorter_than_the_floor_never_lowers_the_bound(monkeypatch, tmp_path):
    """الاشتقاق يرفع السقف ولا يخفضه: كادنسٌ صغير لا يجعل الفحص أشدّ من أساسه."""
    module = _probe(
        monkeypatch, tmp_path, WORKER_HEARTBEAT_CADENCE_SEC="10", WORKER_HEALTH_MAX_AGE_SEC="180"
    )
    assert module.effective_max_age() == 180


def test_an_undeclared_cadence_falls_back_to_the_explicit_bound(monkeypatch, tmp_path):
    module = _probe(
        monkeypatch, tmp_path, WORKER_HEARTBEAT_CADENCE_SEC="0", WORKER_HEALTH_MAX_AGE_SEC="180"
    )
    assert module.effective_max_age() == 180


def test_two_cadences_are_allowed_because_one_stall_is_not_a_death(monkeypatch, tmp_path):
    """دورةٌ واحدة تجعل كلّ تأخّرٍ عابر يُقرَأ عطلاً — فيقيس الفحصُ الجدولة لا الحياة.

    ودورتان كاملتان فائتتان **تُرصَد**: هذا هو الحدّ الذي يفصل التأخّر عن التوقّف.
    """
    module = _probe(monkeypatch, tmp_path, WORKER_HEARTBEAT_CADENCE_SEC="300")
    _ready(tmp_path)
    _beat(tmp_path, age_seconds=400)
    assert module.check()[0] is True, "دورةٌ واحدة فائتة تأخّرٌ لا موت"
    _beat(tmp_path, age_seconds=900)
    assert module.check()[0] is False, "دورتان فائتتان توقّفٌ يجب أن يُرصَد"


# ── ⑤ العقدُ مع مُستهلِكيه في compose ────────────────────────────────────────


def test_every_probe_consumer_declares_its_producer_cadence():
    """السقفُ بلا كادنسٍ مُعلَن رقمٌ يصادف أن يوافق — وهو ما انكسر فعلاً.

    فكلّ خدمةٍ يقرأ فحصُها هذا المِسبار يجب أن تُعلِن كادنسها في نفس الملفّ الذي
    يُعلِن الفحص، وإلّا عاد الرقمان ينحرفان بلا من يرى الانحراف.
    """
    import yaml

    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    consumers = [
        name
        for name, svc in compose["services"].items()
        if "worker_health_probe.py" in " ".join((svc.get("healthcheck") or {}).get("test") or [])
    ]
    assert consumers, "لا مستهلك للمِسبار — الاختبار يقيس شجرةً تغيّرت تحته"
    for name in consumers:
        env = compose["services"][name].get("environment") or {}
        assert "WORKER_HEARTBEAT_CADENCE_SEC" in env, (
            f"{name} يقرأ المِسبار ولا يُعلِن كادنسه ⇒ السقف يعود رقماً مستقلّاً "
            "عن المنتِج، وهو العطل الذي أبات النبضة ٩٥٪ من الساعة على الإعداد المشحون"
        )


def test_both_probe_copies_stay_byte_identical():
    """نسختان تنحرفان: يُصلَح عاملٌ ويبقى الآخر يفشل مفتوحاً بلا من يلاحظ."""
    texts = {p: (ROOT / p).read_text(encoding="utf-8") for p in PROBES}
    assert len(set(texts.values())) == 1, "نسختا المِسبار انحرفتا"


def test_the_probe_stays_stdlib_only():
    """يعمل داخل حاوية مُقوّاة: أيّ تبعيّة هنا تكسر الفحص وقت الحاجة إليه."""
    text = (ROOT / PROBES[0]).read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")) and "__future__" not in stripped:
            module = stripped.split()[1].split(".")[0]
            assert module in {"os", "sys", "time", "pathlib"}, stripped
