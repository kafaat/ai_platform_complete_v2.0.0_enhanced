"""`CONTRACT-WHOSE-TWO-ENDS-ARE-TESTED-APART-01` — وشهودُ نطاقه الخمسة.

عقدٌ طرفاه في خدمتين، كلٌّ مختبَرٌ وحدَه، والقفزةُ بلا شاهد. أصابنا ثلاثَ مرّاتٍ
في أسبوع. عولِجت الحوادثُ بشهودٍ **فرديّين**، وهذا يحرس الصنف: كلُّ عقدٍ عابر
يُكتشَف من الشجرة، ومسارٌ يُطلَب ولا يُعلَن يُحمِّر.

وهذا الملفّ يفرض `GUARD-SCOPE-COMPLETENESS` (دفتر القرارات 2026-08-20): لا يُقبَل
حارسٌ جديد إلّا بخمسة شهود — مصدرُ السطح، وما رآه، وما استبعده ولماذا، **وتساوي
المجموعات** لا العدّادات، وشاهدُ طفرة.

**ويحمل شاهداً سادساً يخصّ هذا الحارس بعينه: مقابلةَ قارئَين.** ثلاثةُ ثقوبٍ في
المستخرِج كُشِفت كلُّها بمقابلة `ast` بتعبيرٍ نمطيّ مستقلّ، ولا واحدٌ منها بقراءةٍ
واحدة — **قارئٌ واحدٌ لا يُكذِّب نفسَه**. فالمقابلةُ مُثبَّتةٌ هنا لئلّا تُفقَد.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / "ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_g_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"_g_{name}"] = module
    spec.loader.exec_module(module)
    return module


guard = _load("cross_service_path_contract_guard")


# ── الشهود ①②③: المصدر وما رآه وما استبعده ──────────────────────────────────
def test_the_contract_surface_is_derived_from_the_tree_not_a_written_list():
    """قائمةٌ مكتوبة تبيت: عميلٌ جديدٌ لا يدخل النطاق، والحارسُ يبقى أخضرَ عن
    سؤالٍ لم يعد يطرحه. **والاشتقاقُ قِيس أنّه يرى أكثرَ ممّا كنتُ سأكتب:**
    جردي اليدويّ عدّ أربعةَ عملاء (`*_client.py`)، والاشتقاقُ وجد ثمانية."""
    contracts = guard.discover_contracts()

    assert len(contracts) >= 8, (
        f"سطحٌ أضيقُ ممّا قِيس ({len(contracts)}) — تغيّر شكلُ عناوين الخدمات والفحصُ صار أعمى"
    )
    for client, meta in contracts.items():
        assert meta["service_dir"].is_dir(), f"خدمةٌ هدفٌ غيرُ موجودة: {client} → {meta['service']}"


def test_every_path_less_client_carries_a_written_reason():
    for client, reason in guard.PATH_LESS_BY_DESIGN.items():
        assert (ROOT / client).exists(), f"إعفاءٌ لملفٍّ غيرِ موجود: {client}"
        assert len(str(reason).strip()) > 40, f"إعفاءٌ بسببٍ صوريّ: {client}"


def test_the_exemption_list_does_not_go_stale():
    """مدخلٌ صار له مسارٌ ثابتٌ ولم يُنزَع إعفاؤه يُخفي انحداراً قادماً."""
    assert guard.audit()["stale_exemptions"] == []


# ── الشاهد ④: تساوي المجموعات، لا عدّادات ────────────────────────────────────
def test_the_guard_sees_exactly_the_modules_that_name_an_internal_service():
    """عدّادٌ متطابق يمرّ ولو كان الحارس يرى وحدةً ويغفل أخرى بالعدد نفسه."""
    host = re.compile(r"https?://sahool-([a-z0-9-]+?)-service(?::\d+)?")
    expected = set()
    api = ROOT / "services" / "sahool-platform" / "api"
    for path in api.rglob("*.py"):
        if "__pycache__" in path.as_posix():
            continue
        hosts = set(host.findall(path.read_text(encoding="utf-8", errors="ignore")))
        if len(hosts) == 1 and (ROOT / "services" / f"{next(iter(hosts))}-service").is_dir():
            expected.add(path.relative_to(ROOT).as_posix())

    assert set(guard.discover_contracts()) == expected


def test_no_requested_path_is_absent_from_the_target_service():
    report = guard.audit()
    assert report["undeclared"] == [], (
        f"مساراتٌ يطلبها عميلٌ ولا تُعلنها خدمتُه — ٤٠٤ حتميّ لا احتماليّ: {report['undeclared']}"
    )


def test_no_contract_reads_zero_and_passes():
    """قراءةٌ صفريّة تمرّ خضراء عن سؤالٍ لم تطرحه — وهي كيف يمرّ هذا الصنفُ نفسُه."""
    assert guard.audit()["blind_clients"] == []


def test_a_client_that_reads_zero_is_actually_reported_blind():
    """**شاهدٌ موجبٌ للعمى — والسطرُ الوحيد الذي نجت منه طفرةٌ مُسجَّلة.**

    كان الفحصُ أعلاه وحدَه: «القائمةُ فارغةٌ على شجرةٍ سليمة». وهي تبقى فارغةً
    **أيضاً لو عُطِّل الكشفُ رأساً** — فطفرةٌ تُطفئه مرّت خضراء. تأكيدُ غيابٍ بلا
    شاهدِ حضورٍ يقيس صمتَ الشجرة لا عملَ الآليّة، وهو الصنفُ الذي يحرسه هذا
    الملفّ واقعاً في طبقةِ اختباره هو.

    فيُقاس هنا بالإيجاب على مُدخَلٍ مُصطنَع: عميلٌ بلا مسارٍ **يُعلَن أعمى**،
    وخدمةٌ بلا إعلانٍ كذلك، والسليمُ يمرّ.
    """
    blind = guard.classify("api/some_new_client.py", set(), {"/v1/x"})
    assert blind["blind"] == ["api/some_new_client.py"]
    assert blind["path_less"] is True

    unreadable_service = guard.classify("api/c.py", {"/v1/x"}, set())
    assert unreadable_service["blind"], "خدمةٌ بصفر إعلانٍ تمرّ — القارئُ أعمى عن الطرف الآخر"

    healthy = guard.classify("api/c.py", {"/v1/x"}, {"/v1/x", "/v1/y"})
    assert healthy["blind"] == [] and healthy["undeclared"] == []

    drifted = guard.classify("api/c.py", {"/v1/typo"}, {"/v1/x"})
    assert drifted["undeclared"] == ["/v1/typo"]

    # والمُعفى بسببٍ مكتوب لا يُعدّ أعمى — وإلّا صار الإعفاءُ بلا أثر.
    exempt = next(iter(guard.PATH_LESS_BY_DESIGN))
    assert guard.classify(exempt, set(), {"/v1/x"})["blind"] == []


# ── الشاهد ⑥ (خاصٌّ بهذا الحارس): قارئان يتقابلان ───────────────────────────
_INDEPENDENT = re.compile(r'(?:get|post|put|delete)_json\w*\(\s*(?:f?)["\'](/[^"\']*)')


@pytest.mark.parametrize(
    "client",
    [
        "services/sahool-platform/api/weather_service_client.py",
        "services/sahool-platform/api/decision_service_client.py",
        "services/sahool-platform/api/raster_service_client.py",
    ],
)
def test_the_structural_reader_sees_everything_a_textual_one_sees(client):
    """**الآليّةُ التي كشفت ثلاثةَ ثقوبٍ في المستخرِج، مُثبَّتةً لئلّا تُفقَد.**

    كلُّ ثقبٍ ظهر بفارقِ عدَدٍ بين قارئين، لا بقراءةٍ واحدة:
      · `soil_hydraulic_client` ⇒ صفرٌ بالنمطيّ (ينادي `httpx` بسلسلةٍ مُنسَّقة)
      · `irrigation_activation_gate` ⇒ صفرٌ بـ`ast` (المسارُ في ثابتِ وحدة)
      · `raster_get_json_sync` ⇒ ١٦ مقابل ١٤ (`endswith` أفلت لاحقةَ `_sync`)

    والاتّجاهُ المفروض هنا **أحاديّ بالقصد**: البنيويُّ يرى كلَّ ما يراه النصّيّ
    وزيادة. فالعكسُ (تساوٍ صارم) كان سيمنع توسيعَ البنيويّ إلى أشكالٍ لا يعرفها
    النصّيّ أصلاً — وهو ما فعلناه مرّتين.
    """
    source = (ROOT / client).read_text(encoding="utf-8")
    textual = {guard.normalise(m) for m in _INDEPENDENT.findall(source)}
    structural = guard.requested_paths(source)

    assert textual, f"القارئُ المستقلُّ لم يجد شيئاً في {client} — المقابلةُ صارت بلا معنى"
    missed = sorted(textual - structural)
    assert not missed, f"المستخرِجُ البنيويُّ يفوته ما يراه قارئٌ نصّيٌّ بسيط في {client}: {missed}"


# ── الشاهد ⑤: شاهدُ الطفرة ──────────────────────────────────────────────────
def test_a_path_the_service_never_declares_is_caught():
    """المرساةُ المسمّاة: الحادثةُ الأصليّةُ بحرفها تُحمِّر الحارس."""
    source = 'BASE = "http://sahool-weather-service:8000"\nx = weather_get_json("/v1/weather/tile-cache/stats")\n'
    requested = guard.requested_paths(source)

    assert "/v1/weather/tile-cache/stats" in requested
    declared = guard.declared_paths(ROOT / "services" / "weather-service")
    assert "/v1/weather/tile-cache/stats" not in declared, "عاد المسارُ الخاطئ إلى سطح الخدمة"
    assert "/v1/weather/cache-stats" in declared


def test_both_call_shapes_and_the_module_constant_are_read():
    """الأشكالُ الثلاثةُ المقيسةُ في الشجرة — كلُّها تُقرأ، ولا واحدٌ منها يُفلِت."""
    assert guard.requested_paths('x = weather_get_json("/v1/weather/current")') == {
        "/v1/weather/current"
    }
    assert guard.requested_paths(
        'y = await client.get(f"{base}/v1/fields/{fid}/soil/hydraulic-profile")'
    ) == {"/v1/fields/{}/soil/hydraulic-profile"}
    assert guard.requested_paths('GATE = "/v1/activation/irr_f01_reservation/enforce"') == {
        "/v1/activation/irr_f01_reservation/enforce"
    }
    assert guard.requested_paths('z = raster_get_json_sync("/v1/indices")') == {"/v1/indices"}


def test_prose_and_error_messages_are_not_mistaken_for_requests():
    """سلسلةٌ في رسالةٍ أو تعليقٍ ليست طلباً — وإلّا امتلأ الجردُ بما لا يُطلَب."""
    assert guard.requested_paths('raise ValueError("تعذّر /v1/weather/current")') == set()
    assert guard.requested_paths("# ينادي /v1/weather/forecast سابقاً\nx = 1") == set()


def test_the_guard_exits_nonzero_when_a_path_is_undeclared(monkeypatch):
    """الحارسُ الذي يطبع الشكوى ويُنهي بصفرٍ لا يحجب شيئاً."""
    monkeypatch.setattr(
        guard,
        "audit",
        lambda: {
            "contracts": {
                "c.py": {"service": "s", "requested": 1, "declared": 2, "undeclared": ["/x"]}
            },
            "blind_clients": [],
            "undeclared": ["c.py → s: /x"],
            "path_less": [],
            "stale_exemptions": [],
        },
    )
    assert guard.main() == 1


def test_the_guard_exits_nonzero_when_nothing_is_discovered(monkeypatch):
    """صفرُ عقدٍ مكتشَفٍ يمرّ أخضرَ لو لم يُغلَق — وهو أخطرُ من عقدٍ منحرف."""
    monkeypatch.setattr(guard, "audit", lambda: {"contracts": {}})
    assert guard.main() == 1
