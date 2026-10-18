"""عقدُ سياسة الذكاء بين المنصّة (المزوِّد) وTTS (المستهلك) — اختبارُ تعاقدٍ عابرٌ للخدمتين.

يبني الغلافَ **بدالّة المنصّة نفسها** (``core/ai_policy_envelope.build_ai_policy_envelope``)
ويُمرّره **كما هو** إلى قارئ TTS (``tts_tenant_policy.policy_from_me``) ثمّ إلى اختيار
المزوّد (``providers.select_provider_for_policy``). فلا نسخةَ يدويّة من شكل العقد في الاختبار:
إن غيّر أحدُ الطرفين الشكلَ دون الآخر احمرّ هنا.

المصفوفة (قرار المالك 2026-10-12): فقدانُ الحقل · توكنُ مستأجِرٍ مختلف · انقطاعُ المنصّة ·
رفضُ مشاركة النصّ · توفّرُ المزوّد المحلّيّ — مع فصل إذن TTS الخارجيّ عن إذن LLM الخارجيّ.
v2 هو العقدُ الوحيد: غلافٌ بلا رقم عقد مرفوض (أُزيل مسارُ التوافق القديم بقرار المالك).
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
_TENANT = "00000000-0000-0000-0000-0000000000c7"
_OTHER = "00000000-0000-0000-0000-0000000000c8"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ENV = _load(
    "_contract_platform_envelope", ROOT / "services/sahool-platform/core/ai_policy_envelope.py"
)
TTS = _load("_contract_tts_policy", ROOT / "services/tts-service/tts_tenant_policy.py")


def _row(mode: str, providers=(), generation=True) -> dict:
    return {
        "tenant_id": _TENANT,
        "ai_generation_allowed": generation,
        "allowed_providers": list(providers),
        "allowed_models": [],
        "external_data_sharing_level": mode,
        "redaction_profile": "default",
    }


def _me(envelope: dict | None, tenant: str = _TENANT) -> dict:
    payload = {"user_id": "u1", "tenant_id": tenant, "role": "worker"}
    if envelope is not None:
        payload["ai_policy_envelope"] = envelope
    return payload


def _decide(row) -> TTS.TTSPolicy:
    return TTS.policy_from_me(_me(ENV.build_ai_policy_envelope(_TENANT, row)), _TENANT)


# ── المزوِّد: شكلُ العقد ─────────────────────────────────────────────────────
def test_the_platform_stamps_contract_v2_on_every_envelope():
    for envelope in (
        ENV.most_restrictive_envelope(_TENANT),
        ENV.build_ai_policy_envelope(_TENANT, _row("full_external")),
    ):
        assert envelope["contract"] == "sahool.ai_policy_envelope"
        assert envelope["contract_version"] == TTS.TTS_CONTRACT_VERSION == 2
        assert envelope["version"] == "v52", (
            "رقمُ السياسة القائم لا يتغيّر — المستهلكون القدامى يقرؤونه"
        )


_MATRIX = [
    (None, False, []),  # لا صفّ ⇒ الأشدّ
    (_row("local_only", ["tts:edge_tts"]), False, []),
    (_row("redacted_external", ["tts:edge_tts"]), False, []),  # النصُّ الخام لا يُنقَّح
    (_row("full_external"), False, []),  # قائمةٌ فارغة لا تمنح شيئاً هنا
    (_row("full_external", ["anthropic"]), False, []),  # مزوّدُ LLM ليس مزوّدَ صوت
    (_row("full_external", ["tts:unknown"]), False, []),  # اسمٌ مجهول لا يمنح شيئاً
    (_row("full_external", ["TTS:Edge_TTS"]), True, ["edge_tts"]),
    (_row("full_external", ["tts:edge_tts"], generation=False), True, ["edge_tts"]),
]
_GRANT_ROWS = [row for row, _allowed, _providers in _MATRIX]


@pytest.mark.parametrize(("row", "allowed", "providers"), _MATRIX)
def test_external_tts_is_granted_only_by_an_explicit_speech_provider(row, allowed, providers):
    envelope = ENV.build_ai_policy_envelope(_TENANT, row)
    assert envelope["external_tts_allowed"] is allowed
    assert envelope["external_tts_providers"] == providers


# ── فصلُ الإذنين: LLM لا يمنح TTS، وTTS لا يمنح LLM ───────────────────────────
def test_an_external_llm_grant_does_not_open_external_tts():
    row = _row("full_external", ["anthropic"], generation=True)
    envelope = ENV.build_ai_policy_envelope(_TENANT, row)
    assert envelope["external_llm_allowed"] is True
    assert _decide(row) == TTS.LOCAL_ONLY_POLICY


def test_an_external_tts_grant_does_not_open_external_llm():
    row = _row("full_external", ["tts:edge_tts"], generation=False)
    envelope = ENV.build_ai_policy_envelope(_TENANT, row)
    assert envelope["external_llm_allowed"] is False
    decision = _decide(row)
    assert decision.external_allowed and decision.external_providers == frozenset({"edge_tts"})


# ── المستهلك: الفشلُ المغلق ───────────────────────────────────────────────────
@pytest.mark.parametrize("field", ["external_tts_allowed", "external_tts_providers"])
def test_a_v2_envelope_missing_a_tts_field_is_local_only(field):
    envelope = ENV.build_ai_policy_envelope(_TENANT, _row("full_external", ["tts:edge_tts"]))
    envelope.pop(field)
    assert TTS.policy_from_me(_me(envelope), _TENANT) == TTS.LOCAL_ONLY_POLICY


@pytest.mark.parametrize("version", ["2", 1, 0, None, True, 2.0])
def test_a_malformed_contract_version_is_local_only(version):
    envelope = ENV.build_ai_policy_envelope(_TENANT, _row("full_external", ["tts:edge_tts"]))
    envelope["contract_version"] = version
    assert TTS.policy_from_me(_me(envelope), _TENANT) == TTS.LOCAL_ONLY_POLICY


@pytest.mark.parametrize("contract", [None, "", "other.policy", 2, True])
def test_a_missing_or_wrong_contract_identity_is_local_only(contract):
    envelope = ENV.build_ai_policy_envelope(_TENANT, _row("full_external", ["tts:edge_tts"]))
    if contract is None:
        envelope.pop("contract")
    else:
        envelope["contract"] = contract
    assert TTS.policy_from_me(_me(envelope), _TENANT) == TTS.LOCAL_ONLY_POLICY


def test_the_old_platform_me_without_an_envelope_is_local_only():
    """منصّةُ الإنتاج اليوم (``/api/v1/me`` بلا ``ai_policy_envelope``) ⇒ الأشدّ."""
    assert TTS.policy_from_me(_me(None), _TENANT) == TTS.LOCAL_ONLY_POLICY


@pytest.mark.parametrize("strip", [("contract_version",), ("contract", "external_tts")])
def test_an_envelope_without_a_contract_version_is_local_only(strip):
    """لا رجوعَ إلى ``external_llm_allowed``: غلافٌ بلا رقم عقد ⇒ الأشدّ ولو منح كلَّ شيء."""
    full = ENV.build_ai_policy_envelope(
        _TENANT, _row("full_external", ["anthropic", "tts:edge_tts"])
    )
    assert full["external_llm_allowed"] is True and full["external_tts_allowed"] is True
    legacy = {k: v for k, v in full.items() if not k.startswith(strip)}
    assert TTS.policy_from_me(_me(legacy), _TENANT) == TTS.LOCAL_ONLY_POLICY


@pytest.mark.parametrize("row", _GRANT_ROWS)
def test_every_envelope_the_local_platform_builds_is_read_as_v2(row):
    """المنصّةُ المحلّيّة تُصدر v2 دائماً، وTTS المحلّيّ يقرؤه v2: نزعُ رقم العقد وحده يُسقط
    أيَّ منحٍ إلى الأشدّ — فالقرارُ معلَّقٌ بالعقد لا بحقلٍ قديم."""
    envelope = ENV.build_ai_policy_envelope(_TENANT, row)
    assert envelope["contract_version"] == TTS.TTS_CONTRACT_VERSION
    stripped = {k: v for k, v in envelope.items() if k != "contract_version"}
    assert TTS.policy_from_me(_me(stripped), _TENANT) == TTS.LOCAL_ONLY_POLICY


def test_the_tts_reader_never_consults_the_llm_permission():
    """قارئُ TTS لا يقرأ ``external_llm_allowed`` في أيّ موضعٍ من شيفرته (لا من التعليقات)."""
    import ast

    tree = ast.parse(
        (ROOT / "services/tts-service/tts_tenant_policy.py").read_text(encoding="utf-8")
    )
    used = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and n.value == "external_llm_allowed"
    ]
    assert used == []


@pytest.mark.parametrize(
    ("payload_tenant", "envelope_tenant"), [(_OTHER, _TENANT), (_TENANT, _OTHER)]
)
def test_a_token_for_another_tenant_is_local_only(payload_tenant, envelope_tenant):
    envelope = ENV.build_ai_policy_envelope(
        envelope_tenant, _row("full_external", ["tts:edge_tts"])
    )
    assert (
        TTS.policy_from_me(_me(envelope, tenant=payload_tenant), _TENANT) == TTS.LOCAL_ONLY_POLICY
    )


def test_platform_unreachable_or_unset_is_local_only(monkeypatch):
    user = {"tenant_id": _TENANT}

    async def down(_url, _auth):
        raise OSError("platform unreachable")

    monkeypatch.setenv("PLATFORM_API_URL", "http://platform.internal")
    assert asyncio.run(TTS.resolve_policy(user, "Bearer t", fetch=down)) == TTS.LOCAL_ONLY_POLICY
    monkeypatch.delenv("PLATFORM_API_URL")
    assert asyncio.run(TTS.resolve_policy(user, "Bearer t")) == TTS.LOCAL_ONLY_POLICY


def test_the_full_chain_through_resolve_policy(monkeypatch):
    seen = {}

    async def me(url, auth):
        seen["url"], seen["auth"] = url, auth
        return _me(ENV.build_ai_policy_envelope(_TENANT, _row("full_external", ["tts:edge_tts"])))

    monkeypatch.setenv("PLATFORM_API_URL", "http://platform.internal/")
    decision = asyncio.run(TTS.resolve_policy({"tenant_id": _TENANT}, "Bearer t", fetch=me))
    assert seen == {"url": "http://platform.internal/api/v1/me", "auth": "Bearer t"}
    assert decision == TTS.TTSPolicy("full_external", frozenset({"edge_tts"}))


# ── اختيارُ المزوّد: توفّرُ المحلّيّ، وحصرُ الخارجيّ فيما سمّاه المستأجِر ──────────
class _P:
    def __init__(self, name, external, available=True):
        self.name, self.external, self._available = name, external, available

    def available(self):
        return self._available


@pytest.fixture()
def providers(monkeypatch):
    path = ROOT / "services/tts-service"
    monkeypatch.syspath_prepend(str(path))
    sys.modules.pop("providers", None)
    module = _load("_contract_tts_providers", path / "providers.py")
    monkeypatch.setattr(module, "_default_provider", lambda registry: registry[0])
    return module


def _choose(providers, decision, registry, requested=None):
    return providers.select_provider_for_policy(
        requested, registry, decision.external_allowed, decision.external_providers
    )


def test_local_only_uses_an_available_local_provider_else_none(providers):
    edge, piper = _P("edge_tts", True), _P("piper", False)
    assert _choose(providers, TTS.LOCAL_ONLY_POLICY, [edge, piper]) is piper
    assert _choose(providers, TTS.LOCAL_ONLY_POLICY, [edge, _P("piper", False, False)]) is None


def test_v2_external_is_limited_to_the_named_provider(providers):
    edge, other = _P("edge_tts", True), _P("other_cloud", True)
    named = TTS.TTSPolicy("full_external", frozenset({"edge_tts"}))
    assert _choose(providers, named, [other, edge], requested="other_cloud") is edge
    assert _choose(providers, TTS.TTSPolicy("full_external", frozenset({"x"})), [edge]) is None


def test_an_external_grant_naming_no_provider_selects_only_local(providers):
    """لا مسارَ «أيّ مزوّدٍ خارجيّ» بعد الآن: منحٌ بلا اسمٍ لا يصل إلى edge."""
    edge, piper = _P("edge_tts", True), _P("piper", False)
    unnamed = TTS.TTSPolicy("full_external")
    assert _choose(providers, unnamed, [edge]) is None
    assert _choose(providers, unnamed, [edge, piper]) is piper
