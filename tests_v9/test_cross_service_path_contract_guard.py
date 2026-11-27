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
    جردي اليدويّ عدّ أربعةَ عملاء (`*_client.py`)، والاشتقاقُ وجد ثمانية — ومنذ W1-02
    (``core/`` وكلُّ مضيفٍ مبنيٍّ في compose) صار أكثر."""
    contracts = guard.discover_contracts()

    assert len(contracts) >= 11, (
        f"سطحٌ أضيقُ ممّا قِيس ({len(contracts)}) — تغيّر شكلُ عناوين الخدمات والفحصُ صار أعمى"
    )
    for client, meta in contracts.items():
        assert meta["services"], f"عميلٌ بلا مضيفٍ في النطاق: {client}"
        for host, service_dir in meta["services"].items():
            assert service_dir.is_dir(), f"خدمةٌ هدفٌ غيرُ موجودة: {client} → {host}"


def test_every_path_less_client_carries_a_written_reason():
    for client, reason in guard.PATH_LESS_BY_DESIGN.items():
        assert (ROOT / client).exists(), f"إعفاءٌ لملفٍّ غيرِ موجود: {client}"
        assert len(str(reason).strip()) > 40, f"إعفاءٌ بسببٍ صوريّ: {client}"


def test_the_exemption_list_does_not_go_stale():
    """مدخلٌ صار له مسارٌ ثابتٌ ولم يُنزَع إعفاؤه يُخفي انحداراً قادماً."""
    assert guard.audit()["stale_exemptions"] == []


# ── الشاهد ④: تساوي المجموعات، لا عدّادات ────────────────────────────────────
def test_the_guard_sees_exactly_the_modules_that_name_an_internal_service():
    """عدّادٌ متطابق يمرّ ولو كان الحارس يرى وحدةً ويغفل أخرى بالعدد نفسه.

    المرجعُ هنا مشتقٌّ **مستقلّاً**: نصُّ compose يُقرأ بتعبيرٍ نمطيّ (مفتاحُ خدمةٍ
    تحته ``build:``)، والوحداتُ تُمسَح في ``api/`` و``core/`` معاً (W1-02).
    """
    known = set()
    for compose in ROOT.glob("docker-compose*.yml"):
        current = None
        for line in compose.read_text(encoding="utf-8").splitlines():
            key = re.match(r"^  ([a-z0-9-]+):\s*$", line)
            if key:
                current = key.group(1)
            elif current and re.match(r"^    build:", line):
                known.add(current)
    host = re.compile(r"https?://(sahool-[a-z0-9-]+)")
    expected = set()
    platform = ROOT / "services" / "sahool-platform"
    for base in (platform / "api", platform / "core"):
        for path in base.rglob("*.py"):
            if "__pycache__" in path.as_posix() or "tests" in path.relative_to(base).parts:
                continue
            if set(host.findall(path.read_text(encoding="utf-8", errors="ignore"))) & known:
                expected.add(path.relative_to(ROOT).as_posix())

    assert {
        "services/sahool-platform/core/field_intelligence_adapters.py",
        "services/sahool-platform/core/pest_escalation_flow.py",
        "services/sahool-platform/api/routers/compat_gateway.py",
    } <= expected, "المرجعُ المستقلّ لم يعد يرى وحداتِ core/ ومتعدّدةَ المضيفين"
    assert set(guard.discover_contracts()) == expected, "الحارسُ يرى غيرَ ما يراه المرجعُ المستقلّ"


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


def test_a_route_decorator_is_a_declaration_not_a_request():
    """موجِّهٌ هو أيضاً عميل (M4 · `routers/indicators.py`): مُزخرِفُه يُعلن ولا يطلب.

    والنداءُ نفسُه خارج موضع الزخرفة **يبقى طلباً** — فالاستثناءُ موضعيٌّ لا اسميّ،
    وإلّا صار `client.get("/v1/…")` داخل دالّةٍ مُزخرَفةٍ يفلت معه.
    """
    source = (
        'BASE = "http://sahool-indicators-service:8000"\n'
        'PATH = "/v1/fields/{field_id}/observations"\n'
        '@router.get("/api/v1/fields/{field_id}/indicator-observations/{view}")\n'
        "async def route(field_id):\n"
        '    return await client.get(f"{BASE}/v1/fields/{field_id}/observation-timeline")\n'
    )
    assert guard.requested_paths(source) == {
        "/v1/fields/{}/observations",
        "/v1/fields/{}/observation-timeline",
    }


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


# ── W1-02: ``core/`` · الوحدةُ متعدّدةُ المضيفين · كلُّ مضيفٍ في compose ───────────────
_PRE_W1_01_ADAPTERS = """
import os
WEATHER_URL = os.getenv("WEATHER_SERVICE_URL", "http://sahool-weather-service:8000")
SOIL_URL = os.getenv("SOIL_SERVICE_URL", "http://sahool-soil-service:8000")
GUARDRAILS_URL = os.getenv("GUARDRAILS_URL", "http://sahool-guardrails-engine:8000")

def weather_adapter(req):
    return _get_json(f"{WEATHER_URL}/v1/weather/current", {})

def soil_adapter(req):
    data = _get_json(f"{SOIL_URL}/api/v1/soil/{req.field_id}")
    return data

def guardrails_adapter(decision, state):
    return _post_json(f"{GUARDRAILS_URL}/v1/validate", {})
"""


def _known():
    return set(guard.compose_hosts()[0])


def test_every_audited_host_is_a_built_compose_service():
    """المضيفون الخمسة الذين كانوا خارج النطاق (W1-02) صاروا داخله بمجلّدات مصادرهم."""
    hosts, image_only = guard.compose_hosts()
    for name, folder in {
        "sahool-guardrails-engine": "guardrails-engine",
        "sahool-edge": "edge-inference",
        "sahool-field-segmentation": "field-segmentation",
        "sahool-scout-ingest": "scout-ingest-service",
        "sahool-vegetation-analysis": "vegetation-analysis-service",
    }.items():
        assert name in hosts, f"مضيفٌ مبنيٌّ في compose خارج النطاق: {name}"
        assert hosts[name] == (ROOT / "services" / folder).resolve(), (
            f"{name} يُحَلّ إلى {hosts[name]} لا إلى services/{folder}"
        )
    assert {"sahool-ollama", "sahool-vllm-jais"} <= image_only, (
        "صورٌ جاهزة بلا مصدر يجب أن تُعدّ خارجيّةً لا عقوداً"
    )
    assert guard.audit()["unknown_hosts"] == [], "عميلٌ ينادي مضيفاً لا يعرفه compose"


def test_a_multi_host_module_attributes_each_call_to_its_own_host():
    """وحدةٌ بأربعة مضيفين كانت تُسقَط كلُّها — فمرّ ``soil_adapter`` بمسارٍ لا يُعلَن."""
    scan = guard.scan_module(_PRE_W1_01_ADAPTERS, _known())
    assert scan["unattributed"] == [], f"نداءٌ لم يُنسَب: {scan['unattributed']}"
    assert scan["requested"] == {
        "sahool-weather-service": {"/v1/weather/current"},
        "sahool-soil-service": {"/api/v1/soil/{}"},
        "sahool-guardrails-engine": {"/v1/validate"},
    }, f"نسبةٌ خاطئة: {scan['requested']}"


def test_negative_control_the_pre_w1_01_soil_adapter_is_undeclared():
    """**الحارسُ يفشل على شكل ما قبل W1-01 ويمرّ بعده** (معيارُ قبول W1-02)."""
    scan = guard.scan_module(_PRE_W1_01_ADAPTERS, _known())
    declared = guard.declared_paths(ROOT / "services" / "soil-service")
    verdict = guard.classify("core/x.py", scan["requested"]["sahool-soil-service"], declared)
    assert verdict["undeclared"] == ["/api/v1/soil/{}"], (
        f"المسارُ الذي لا تُعلنه soil-service لم يُلتقَط: {verdict}"
    )
    live = guard.audit()["contracts"]
    key = "services/sahool-platform/core/field_intelligence_adapters.py → sahool-soil-service"
    assert key in live, "المحوّلاتُ الحيّةُ في core/ خارج النطاق"
    assert live[key]["undeclared"] == [], f"محوّلُ التربة الحاليّ ما زال منحرفاً: {live[key]}"


def test_an_unattributable_call_in_a_multi_host_module_fails_closed():
    """نداءٌ لا يُشير عنوانُه إلى مضيفٍ واحد في وحدةٍ متعدّدة المضيفين ⇒ يُبلَّغ لا يسقط."""
    source = _PRE_W1_01_ADAPTERS + 'x = weather_get_json("/v1/ambiguous")\n'
    assert guard.scan_module(source, _known())["unattributed"] == ["/v1/ambiguous"], (
        "طلبٌ بلا مضيفٍ قابلٍ للنسبة سقط صامتاً"
    )


def test_concatenated_and_reassigned_urls_are_read():
    """شكلان مقيسان في ``core/pest_escalation_flow`` و``compat_gateway``."""
    concatenated = (
        'D = "http://sahool-guardrails-engine:8000"\n'
        "def f(client):\n"
        '    url = os.getenv("GUARDRAILS_URL", D).rstrip("/") + "/v1/validate"\n'
        "    return client.post(url, json={})\n"
    )
    assert guard.requested_paths(concatenated) == {"/v1/validate"}, "جمعُ السلاسل لم يُقرأ"
    with_query = (
        "def g(client, q, base):\n"
        '    target = f"{base}/v1/analyze" + (f"?{q}" if q else "")\n'
        "    return client.get(target)\n"
    )
    assert guard.requested_paths(with_query) == {"/v1/analyze"}, "لاحقةُ الاستعلام كسرت القراءة"


def test_the_proxy_allowlists_are_checked_against_each_service():
    """المُمرِّرُ بلا مسارٍ ثابت، لكنّ قوائمَ سماحه تُقابَل بإعلان كلّ خدمة (W1-02)."""
    source = (ROOT / "services/sahool-platform/api/routers/service_proxy.py").read_text(
        encoding="utf-8"
    )
    coverage = guard.proxy_coverage(source, _known())
    assert set(coverage) == {
        "sahool-edge",
        "sahool-field-segmentation",
        "sahool-scout-ingest",
        "sahool-soil-service",
    }, f"مضيفٌ في المُمرِّر بلا قائمةٍ مقروءة: {sorted(coverage)}"
    assert "/v1/inference/pest-detect" in coverage["sahool-edge"], f"{coverage['sahool-edge']}"
    assert "/internal/field-forms/{}" in coverage["sahool-scout-ingest"], (
        f"{coverage['sahool-scout-ingest']}"
    )
    drifted = guard.proxied_undeclared(["/v1/inference/pest-detekt"], {"/v1/inference/pest-detect"})
    assert drifted == ["/v1/inference/pest-detekt"], "مسارٌ مكشوفٌ لا تُعلنه الخدمة لم يُلتقَط"
    assert (
        guard.proxied_undeclared(["/v1/fields/{}/soil/profile"], {"/v1/fields/{}/soil/profile"})
        == []
    ), "المسارُ المُعلَن عُدَّ منحرفاً"


def test_allowlist_patterns_expand_to_concrete_paths():
    assert guard.expand_pattern(r"v1/fields/[^/%\\?#]+/soil/(?:profile|profile/history)") == [
        "/v1/fields/{}/soil/profile",
        "/v1/fields/{}/soil/profile/history",
    ], "فكُّ البدائل والمقطع المتغيّر انكسر"
    assert guard.expand_pattern(r"v1/.*") is None, "نمطٌ لا يُفَكّ يجب ألّا يُدَّعى فكُّه"


# Two real owners share a helper name, but neither its signature nor its host.
_CLASS_TRANSPORTS = """
import httpx
import os
from urllib.parse import quote

class DecisionClient:
    def __init__(self, base_url, token):
        self.base_url, self.token = base_url.rstrip("/"), token

    @classmethod
    def from_env(cls):
        return cls(os.getenv("DECISION_URL", "http://sahool-decision-service:8160"), "token")

    async def _request(self, method, path, tenant):
        async with httpx.AsyncClient() as client:
            return await client.request(method, self.base_url + path)

    async def claim(self, request_id):
        return await self._request(
            "POST", "/v1/execution-requests/" + quote(request_id, safe="") + "/claim", "tenant"
        )

class OwnerClient:
    PREFIX = "/internal/field-inspection-execution-owner/"

    def __init__(self, base_url, token):
        self.base_url, self.token = base_url.rstrip("/"), token

    @classmethod
    def from_env(cls):
        return cls(os.getenv("OWNER_URL", "http://sahool-field-management:8000"), "token")

    async def _request(self, caller, operation, body):
        async with httpx.AsyncClient() as client:
            return await client.post(self.base_url + self.PREFIX + operation, json=body)

    async def readback(self, caller):
        return await self._request(caller, "readback", {})
"""

_CLASS_KNOWN = {"sahool-decision-service", "sahool-field-management"}
_OWNER_READBACK = "/internal/field-inspection-execution-owner/readback"
_DECISION_CLAIM = "/v1/execution-requests/{}/claim"


def test_class_local_wrappers_keep_their_own_transport_and_prefix():
    scan = guard.scan_module(_CLASS_TRANSPORTS, _CLASS_KNOWN)
    assert scan["requested"] == {
        "sahool-decision-service": {_DECISION_CLAIM},
        "sahool-field-management": {_OWNER_READBACK},
    }
    assert scan["unattributed"] == []


def test_the_inspection_adapter_exposes_exactly_both_owners_contracts():
    source = (ROOT / "services/sahool-platform/api/inspection_execution_adapter.py").read_text(
        encoding="utf-8"
    )
    scan = guard.scan_module(source, _CLASS_KNOWN)
    assert scan["requested"] == {
        "sahool-decision-service": {
            "/v1/execution-requests/recovery",
            "/v1/execution-requests",
            "/v1/decisions/{}/lineage",
            "/v1/execution-plans/{}",
            "/v1/execution-requests/{}/claim",
            "/v1/execution-requests/{}/receipt",
            "/v1/execution-requests/{}/observation-context",
            "/v1/execution-requests/{}/verify-outcome",
        },
        "sahool-field-management": {
            "/internal/field-inspection-execution-owner/require-field",
            "/internal/field-inspection-execution-owner/get-link",
            "/internal/field-inspection-execution-owner/list-links",
            "/internal/field-inspection-execution-owner/validate-binding",
            "/internal/field-inspection-execution-owner/ensure-task",
            "/internal/field-inspection-execution-owner/readback",
            "/internal/field-inspection-execution-owner/preview-confirmation",
            "/internal/field-inspection-execution-owner/prepare-confirmation",
            "/internal/field-inspection-execution-owner/save-outcome",
        },
    }
    assert scan["unattributed"] == []


def test_wrapper_keyword_arguments_follow_the_called_method_signature():
    source = _CLASS_TRANSPORTS.replace(
        'self._request(caller, "readback", {})',
        'self._request(body={}, operation="readback", caller=caller)',
    )
    assert guard.scan_module(source, _CLASS_KNOWN)["requested"]["sahool-field-management"] == {
        _OWNER_READBACK
    }


def test_wrapper_names_are_not_a_substitute_for_real_http_transport():
    renamed = _CLASS_TRANSPORTS.replace("_request", "_send_to_owner")
    assert guard.scan_module(renamed, _CLASS_KNOWN)["requested"]["sahool-field-management"] == {
        _OWNER_READBACK
    }
    no_transport = _CLASS_TRANSPORTS.replace(
        "return await client.post(self.base_url + self.PREFIX + operation, json=body)",
        "return {'operation': operation}",
    )
    assert (
        guard.scan_module(no_transport, _CLASS_KNOWN)["requested"]["sahool-field-management"]
        == set()
    )
    assert _OWNER_READBACK not in guard.requested_paths(no_transport)


@pytest.mark.parametrize(
    "replacement",
    [
        'os.getenv("OWNER_URL")',
        '("http://sahool-field-management:8000" if unknown else '
        '"http://sahool-decision-service:8160")',
    ],
)
def test_an_unresolved_or_ambiguous_class_host_cannot_borrow_another_class(replacement):
    source = _CLASS_TRANSPORTS.replace(
        'os.getenv("OWNER_URL", "http://sahool-field-management:8000")', replacement
    )
    scan = guard.scan_module(source, _CLASS_KNOWN)
    assert scan["requested"]["sahool-decision-service"] == {_DECISION_CLAIM}
    assert not scan["requested"].get("sahool-field-management")
    assert scan["unattributed"], "Unknown owner URL was silently accepted or dropped"


@pytest.mark.parametrize(
    "unused",
    [
        '    """Operator note: http://sahool-field-management:8000"""\n',
        '    UNUSED_URL = "http://sahool-field-management:8000"\n',
        '    def unused(self):\n        return "http://sahool-field-management:8000"\n',
    ],
)
def test_unused_host_literals_do_not_establish_the_transport_host(unused):
    source = _CLASS_TRANSPORTS.replace(
        'os.getenv("OWNER_URL", "http://sahool-field-management:8000")',
        'os.getenv("OWNER_URL")',
    ).replace("class OwnerClient:\n", "class OwnerClient:\n" + unused)
    scan = guard.scan_module(source, _CLASS_KNOWN)
    assert scan["requested"]["sahool-field-management"] == set()
    assert scan["unattributed"]


def test_one_resolved_class_request_does_not_hide_a_second_unresolved_request():
    source = (
        _CLASS_TRANSPORTS
        + """
    async def dynamic(self, caller, opaque_operation):
        return await self._request(caller, opaque_operation, {})
"""
    )
    scan = guard.scan_module(source, _CLASS_KNOWN)
    assert scan["requested"]["sahool-field-management"] == {_OWNER_READBACK}
    assert scan["unattributed"], "A resolved call hid another call with an unknown URL"


def test_a_class_prefix_typo_is_reported_against_its_actual_owner():
    source = _CLASS_TRANSPORTS.replace(
        'PREFIX = "/internal/field-inspection-execution-owner/"',
        'PREFIX = "/internal/field-inspection-owner-typo/"',
    )
    scan = guard.scan_module(source, _CLASS_KNOWN)
    assert scan["requested"]["sahool-decision-service"] == {_DECISION_CLAIM}
    verdict = guard.classify(
        "owner.py", scan["requested"]["sahool-field-management"], {_OWNER_READBACK}
    )
    assert verdict["undeclared"] == ["/internal/field-inspection-owner-typo/readback"]


def test_an_unresolved_direct_class_transport_is_not_hidden_by_a_known_wrapper():
    source = (
        _CLASS_TRANSPORTS
        + """
    async def direct(self, opaque_url):
        async with httpx.AsyncClient() as client:
            return await client.post(opaque_url)
"""
    )
    scan = guard.scan_module(source, _CLASS_KNOWN)
    assert scan["requested"]["sahool-field-management"] == {_OWNER_READBACK}
    assert scan["unattributed"]


@pytest.mark.parametrize(
    "source",
    [
        'operation = "readback"\n'
        + _CLASS_TRANSPORTS
        + """
    async def dynamic(self, caller, operation):
        return await self._request(caller, operation, {})
""",
        'base_url = "http://sahool-field-management:8000"\n'
        + _CLASS_TRANSPORTS.replace(
            'def from_env(cls):\n        return cls(os.getenv("OWNER_URL", '
            '"http://sahool-field-management:8000"), "token")',
            'def from_env(cls, base_url):\n        return cls(base_url, "token")',
        ),
        _CLASS_TRANSPORTS
        + """
    async def dynamic(self, caller, operation):
        def unused():
            operation = "readback"
        return await self._request(caller, operation, {})
""",
    ],
    ids=["caller-parameter", "factory-parameter", "nested-local"],
)
def test_lexical_parameters_cannot_borrow_globals_or_nested_assignments(source):
    scan = guard.scan_module(source, _CLASS_KNOWN)
    assert scan["requested"]["sahool-decision-service"] == {_DECISION_CLAIM}
    assert scan["unattributed"], "A different lexical scope supplied the unknown URL"


def test_literal_route_operations_are_expanded_without_accepting_a_typo(tmp_path):
    (tmp_path / "owner.py").write_text(
        """
from typing import Literal
Operation = Literal["readback", "ensure-task"]
@router.post("/internal/field-inspection-execution-owner/{operation}")
def execute(operation: Operation):
    pass
""",
        encoding="utf-8",
    )
    declared = guard.declared_paths(tmp_path)
    assert {_OWNER_READBACK, "/internal/field-inspection-execution-owner/ensure-task"} <= declared
    typo = "/internal/field-inspection-execution-owner/readbak"
    assert guard.classify("owner.py", {typo}, declared)["undeclared"] == [typo]


@pytest.mark.parametrize(
    "old,new",
    [
        (
            'return await self._request(caller, "readback", {})',
            'self.base_url = os.getenv("OPAQUE_URL")\n'
            '        return await self._request(caller, "readback", {})',
        ),
        (
            'return await self._request(caller, "readback", {})',
            'self.PREFIX = "/wrong-owner/"\n'
            '        return await self._request(caller, "readback", {})',
        ),
        (
            'self.base_url, self.token = base_url.rstrip("/"), token',
            'self.base_url, self.token = base_url.rstrip("/"), token\n'
            '        self.base_url: str = os.getenv("OPAQUE_URL")',
        ),
        (
            'self.base_url, self.token = base_url.rstrip("/"), token',
            'self.base_url, self.token = base_url.rstrip("/"), token\n'
            '        self.base_url += "/wrong"',
        ),
    ],
    ids=["method-url", "method-prefix", "annotated-member", "augmented-member"],
)
def test_member_writes_cannot_reuse_an_obsolete_constructor_value(old, new):
    decision, owner = _CLASS_TRANSPORTS.split("class OwnerClient:", 1)
    source = decision + "class OwnerClient:" + owner.replace(old, new, 1)
    scan = guard.scan_module(source, _CLASS_KNOWN)
    verdict = guard.classify(
        "owner.py", scan["requested"]["sahool-field-management"], {_OWNER_READBACK}
    )
    assert scan["unattributed"] or verdict["undeclared"]


def test_class_constant_aliases_keep_their_definition_scope():
    source = 'OWNER_PREFIX = "/wrong-owner/"\n' + _CLASS_TRANSPORTS.replace(
        'PREFIX = "/internal/field-inspection-execution-owner/"',
        "PREFIX = OWNER_PREFIX",
    ).replace(
        "async def _request(self, caller, operation, body):\n",
        "async def _request(self, caller, operation, body):\n"
        '        OWNER_PREFIX = "/internal/field-inspection-execution-owner/"\n',
    )
    scan = guard.scan_module(source, _CLASS_KNOWN)
    assert scan["requested"]["sahool-field-management"] == {"/wrong-owner/readback"}


def test_a_conditional_local_url_does_not_make_an_unknown_url_certain():
    source = (
        _CLASS_TRANSPORTS
        + """
    async def direct(self, opaque_url, override):
        url = opaque_url
        if override:
            url = self.base_url + self.PREFIX + "readback"
        async with httpx.AsyncClient() as client:
            return await client.post(url)
"""
    )
    scan = guard.scan_module(source, _CLASS_KNOWN)
    assert scan["unattributed"]


def test_literal_operations_do_not_allow_an_unknown_interpolation():
    source = (
        _CLASS_TRANSPORTS.replace(
            "self.base_url + self.PREFIX + operation",
            'f"{self.base_url}{self.PREFIX}{operation}"',
        )
        + """
    async def dynamic(self, caller, operation):
        return await self._request(caller, operation, {})
"""
    )
    scan = guard.scan_module(source, _CLASS_KNOWN)
    declared = guard.declared_paths(ROOT / "services/field-management-service")
    verdict = guard.classify("owner.py", scan["requested"]["sahool-field-management"], declared)
    assert scan["unattributed"] or verdict["undeclared"]


def test_literal_aliases_are_read_at_route_registration(tmp_path):
    (tmp_path / "owner.py").write_text(
        """
from typing import Literal
Operation = Literal["readback"]
@router.post("/internal/owner/{operation}")
def execute(operation: Operation):
    pass
Operation = Literal["delete"]
""",
        encoding="utf-8",
    )
    declared = guard.declared_paths(tmp_path)
    assert "/internal/owner/readback" in declared
    assert "/internal/owner/delete" not in declared
    assert "/internal/owner/{}" not in declared
