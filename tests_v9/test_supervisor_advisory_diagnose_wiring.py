"""W0-14: supervisor advisory names no pesticide and publishes no unchecked LLM prose.

scout-12: ``advisory_skill`` used a keyword table that turned one word ("أوراق صفراء",
"ثقوب في الأوراق", "بقع داكنة" …) into a named product (Mancozeb, Chlorpyrifos,
Imidacloprid …). Pest/disease questions now go to the single diagnosis owner, the
platform's ``POST /api/v1/diagnose`` (symptom rules), and the reply carries candidates
plus a confirmation step, never a product or a dose.

airuntime-9: a local-ai-rag answer was returned verbatim. It now passes the shared
structured-claims checker (``shared.ai.structured_advisory``) and is withheld unless the
checker rebuilds it from the owner's current canonical snapshot.

Pure logic, no services: the platform is an ``httpx.MockTransport`` that answers with
the platform's real rule engine (``api/disease_diagnosis.py``), loaded by file path.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

pytestmark = pytest.mark.unit

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SUPERVISOR = os.path.join(ROOT, "services", "supervisor-agent")
SKILL_PATH = os.path.join(SUPERVISOR, "skills", "advisory_skill.py")
DIAGNOSIS_PATH = os.path.join(ROOT, "services", "sahool-platform", "api", "disease_diagnosis.py")
if SUPERVISOR not in sys.path:
    sys.path.insert(0, SUPERVISOR)

from shared.ai.structured_advisory import SCHEMA, digest, evidence_fingerprint  # noqa: E402
from skills import advisory_skill as advisory  # noqa: E402

TENANT = "00000000-0000-0000-0000-000000000141"
FIELD = "field-w0-14"
BEARER = "verified-caller-token"

# Every product the removed tables named, plus their Arabic spellings and other common
# actives: none may appear in an advisory reply.
PRODUCT_NAMES = (
    "Mancozeb",
    "Chlorpyrifos",
    "Imidacloprid",
    "Abamectin",
    "Metalaxyl",
    "Copper oxychloride",
    "Propiconazole",
    "Iprodione",
    "Streptomycin",
    "Sulfur",
    "Bacillus thuringiensis",
    "Trichoderma",
    "Cypermethrin",
    "Deltamethrin",
    "Malathion",
    "مانكوزيب",
    "كلوربيريفوس",
    "إيميداكلوبريد",
    "أبامكتين",
    "ميتالاكسيل",
    "بيكربونات",
    "زيت النيم",
    "صابون زراعي",
)
# The former keyword-table entries (pest and disease) used as queries.
FORMER_KEYWORD_QUERIES = (
    "أوراق صفراء",
    "ثقوب في الأوراق",
    "بيض أبيض",
    "عناكب",
    "ذبول",
    "بقع داكنة",
    "بودرة بيضاء",
    "عفن رمادي",
    "تعفن",
)


def _named_products(value) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    return [name for name in PRODUCT_NAMES if name.lower() in text]


def _platform_rules():
    name = "w0_14_platform_diagnosis"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, DIAGNOSIS_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve annotations through sys.modules
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


def _route_platform(monkeypatch, seen, *, status=200):
    """Answer /api/v1/diagnose with the platform's real symptom-rule engine."""
    rules = _platform_rules()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"detail": "unavailable"})
        body = json.loads(request.content)
        # crop "" keeps the engine free of the platform's crop resolver import; the
        # wheat-only rules are not needed for these assertions.
        result = rules.diagnose("", body["symptoms"]).to_dict()
        result["crop"] = body["crop"]
        return httpx.Response(200, json=result)

    factory = httpx.AsyncClient
    monkeypatch.setattr(
        advisory.httpx,
        "AsyncClient",
        lambda **kw: factory(transport=httpx.MockTransport(handler), **kw),
    )


def _run(intent, query, *, context=None, field_id=None):
    skill = advisory.AdvisorySkill(mcp_client=None)
    ctx = {"_platform_bearer": BEARER} if context is None else context
    return asyncio.run(
        skill.execute(intent, query=query, field_id=field_id, tenant_id=TENANT, context=ctx)
    )


# ── scout-12: insect on wheat goes to the diagnosis owner, no product named ──────────
@pytest.mark.parametrize("query", ["حشرة على القمح", "insect on wheat"])
def test_insect_on_wheat_is_diagnosed_by_the_platform_without_a_product(monkeypatch, query):
    seen: list[httpx.Request] = []
    _route_platform(monkeypatch, seen)
    out = _run("pest_id", query)

    assert len(seen) == 1, f"expected one call to the diagnosis owner, saw {len(seen)}"
    request = seen[0]
    assert request.url.path == "/api/v1/diagnose", f"wrong owner path: {request.url.path}"
    assert request.headers["Authorization"] == f"Bearer {BEARER}", "caller bearer not forwarded"
    sent = json.loads(request.content)
    assert sent == {"crop": "wheat", "symptoms": ["insects_on_leaves"]}, f"bad body: {sent}"

    assert not _named_products(out), f"reply names products: {_named_products(out)}"
    assert out["type"] == "diagnosis_preliminary", f"unexpected type: {out['type']}"
    assert out["actionable"] is False, "a diagnosis must not be an executable proposal"
    assert "action_type" not in out, "a diagnosis must not carry a pesticide action type"
    assert out["calibrated"] is False, "rule-match scores are not calibrated"
    names = [c["name_ar"] for c in out["structured"]["candidates"]]
    assert "منّ" in names, f"platform aphid candidate missing: {names}"
    assert "منّ" in out["response"], "candidate must reach the farmer-facing text"
    assert "مهندس" in out["response"], "reply must route confirmation to an engineer"


@pytest.mark.parametrize("intent", ["pest_id", "disease_id"])
@pytest.mark.parametrize("query", FORMER_KEYWORD_QUERIES)
def test_former_keyword_queries_name_no_product(monkeypatch, intent, query):
    """Negative control: on the keyword-table code these returned Mancozeb, Chlorpyrifos…"""
    _route_platform(monkeypatch, [])
    out = _run(intent, query)
    assert not _named_products(out), f"{intent}/{query!r} names {_named_products(out)}"
    assert out.get("action_type") is None, f"{intent}/{query!r} still emits a pesticide action"


def test_skill_source_carries_no_product_table():
    with open(SKILL_PATH, encoding="utf-8") as handle:
        source = handle.read()
    named = [name for name in PRODUCT_NAMES if name.lower() in source.lower()]
    assert not named, f"advisory_skill.py names products again: {named}"
    assert '"action_type": "pesticide"' not in source, "skill emits pesticide proposals again"


def test_symptom_cues_only_use_codes_the_platform_catalog_defines():
    catalog = {item["code"] for item in _platform_rules().list_symptoms()}
    unknown = sorted(set(advisory._SYMPTOM_CUES) - catalog)
    assert not unknown, f"cue table drifted from /api/v1/diagnose/symptoms: {unknown}"


def test_description_without_known_symptoms_asks_for_detail_without_calling(monkeypatch):
    seen: list[httpx.Request] = []
    _route_platform(monkeypatch, seen)
    out = _run("pest_id", "ثقوب في الأوراق")
    assert seen == [], "no symptom code, so no diagnosis call is made"
    assert out["type"] == "pest_unknown", f"unexpected type: {out['type']}"
    assert out["sources"] == [], "nothing was consulted, nothing is cited"


def test_missing_bearer_is_unavailable_not_a_guess(monkeypatch):
    seen: list[httpx.Request] = []
    _route_platform(monkeypatch, seen)
    out = _run("pest_id", "حشرة على القمح", context={})
    assert seen == [], "no verified caller bearer, so the platform is not called"
    assert out["type"] == "unavailable", f"unexpected type: {out['type']}"
    assert not _named_products(out), "an unavailable reply names no product"


def test_platform_failure_propagates_for_the_degraded_route_reply(monkeypatch):
    _route_platform(monkeypatch, [], status=503)
    with pytest.raises(httpx.HTTPStatusError):
        _run("pest_id", "حشرة على القمح")


def test_owner_reply_is_whitelisted_even_if_it_carried_a_product(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "crop": "wheat",
                "observed_symptoms": ["insects_on_leaves"],
                "candidates": [{"issue_code": "wheat.aphid", "name_ar": "منّ", "score": 0.65}],
                "next_step_ar": "ثبّت بصورة قبل أيّ قرار.",
                "treatment": "Imidacloprid 0.5 l/ha",
            },
        )

    factory = httpx.AsyncClient
    monkeypatch.setattr(
        advisory.httpx,
        "AsyncClient",
        lambda **kw: factory(transport=httpx.MockTransport(handler), **kw),
    )
    out = _run("pest_id", "حشرة على القمح")
    assert not _named_products(out), f"unlisted owner keys leaked: {_named_products(out)}"


# ── airuntime-9: model prose is checked before publication ──────────────────────────
def _canonical_state():
    product = {
        "schema_version": "canonical_weather_state.v1",
        "quality_status": "validated",
        "operational_eligible": True,
        "limitations": [],
        "rain_mm": 4,
    }
    body = {
        "schema_version": "canonical_field_state.v1",
        "field_id": FIELD,
        "season_id": "season-1",
        "as_of_time": "2026-11-16T00:00:00+00:00",
        "weather": product,
        "soil": None,
        "water": None,
        "spectral": None,
        "availability": {"weather": True},
        "limitations": [],
        "evidence_digests": {"weather": digest(product)},
    }
    return {**body, "state_digest": digest(body)}, digest(product)


def _rag_answers(monkeypatch, answer):
    async def rag(question, token):
        return {"answer": answer, "model": "local-llm", "sources": [{"source": "kb.pdf"}]}

    monkeypatch.setattr(advisory, "LOCAL_AI_RAG_URL", "http://local-ai-rag.invalid")
    monkeypatch.setattr(advisory, "_query_local_rag", rag)


@pytest.mark.parametrize(
    "answer",
    [
        "رشّ Chlorpyrifos بمعدّل 2 لتر للهكتار فوراً.",
        "يُزرع القمح في نوفمبر حسب الأمطار.",
    ],
)
def test_unstructured_model_prose_is_withheld(monkeypatch, answer):
    _rag_answers(monkeypatch, answer)
    state, _ = _canonical_state()
    out = _run(
        "general_advice",
        "حشرة على القمح ماذا أرش",
        field_id=FIELD,
        context={"field_state": {"canonical_field_state": state}},
    )
    assert answer not in json.dumps(out, ensure_ascii=False), "unchecked model prose surfaced"
    assert not _named_products(out), f"reply names products: {_named_products(out)}"
    assert out["source"] == "template", f"withheld output must not be labelled {out['source']}"
    assert out["generation_status"] == "suppressed_unvalidated_output", out
    assert out.get("ai_generated") is not True, "a template reply is not AI output"


def test_structured_answer_without_owner_snapshot_is_withheld(monkeypatch):
    state, product_digest = _canonical_state()
    document = {
        "schema_version": SCHEMA,
        "field_id": FIELD,
        "evidence_fingerprint": evidence_fingerprint(state, field_id=FIELD),
        "claims": [{"path": "/weather/rain_mm", "value": 4, "product_digest": product_digest}],
        "candidate_ids": [],
    }
    _rag_answers(monkeypatch, json.dumps(document))
    out = _run("general_advice", "كم المطر؟", field_id=FIELD, context={})
    assert out["source"] == "template", "no server snapshot, so nothing can be verified"
    assert out["generation_status"] == "suppressed_unvalidated_output", out


def test_structured_answer_is_published_only_as_owner_reconstructed_facts(monkeypatch):
    state, product_digest = _canonical_state()
    document = {
        "schema_version": SCHEMA,
        "field_id": FIELD,
        "evidence_fingerprint": evidence_fingerprint(state, field_id=FIELD),
        "claims": [{"path": "/weather/rain_mm", "value": 4, "product_digest": product_digest}],
        "candidate_ids": [],
    }
    _rag_answers(monkeypatch, json.dumps(document))
    out = _run(
        "general_advice",
        "كم المطر؟",
        field_id=FIELD,
        context={"field_state": {"canonical_field_state": state}},
    )
    assert out["source"] == "llm-rag", f"verified facts should surface, got {out}"
    assert out["generation_status"] == "validated_structured_facts", out
    assert out["ai_generated"] is True, "verified model selection is still AI output"
    assert "/weather/rain_mm: 4" in out["response"], f"text not rebuilt: {out['response']}"
    assert out["sources"] == ["kb.pdf"], f"bad source labels: {out['sources']}"

    # The same document with a value the snapshot does not hold is an unsupported claim.
    document["claims"][0]["value"] = 40
    _rag_answers(monkeypatch, json.dumps(document))
    tampered = _run(
        "general_advice",
        "كم المطر؟",
        field_id=FIELD,
        context={"field_state": {"canonical_field_state": state}},
    )
    assert tampered["source"] == "template", "an unsupported claim must be withheld"
    assert "40" not in tampered["response"], "the unsupported value must not surface"


def test_cue_matching_respects_latin_word_starts():
    assert advisory._extract_symptoms("plants look fine") == [], "'ants' fired inside 'plants'"
    assert advisory._extract_symptoms("ants on the stem") == ["ants_present"], "ants missed"
    assert advisory._extract_crop("والقمح فيه حشرات", {}) == "wheat", "clitic-prefixed crop missed"
