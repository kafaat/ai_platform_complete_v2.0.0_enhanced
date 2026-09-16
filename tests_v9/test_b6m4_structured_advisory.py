"""B6: عقدُ مقترحٍ مُصنَّف — النموذج يختار ولا يختلق.

مصدرُه حزمةُ استئناف B6/M4 المُسلَّمة من المالك؛ نُقِل إلى المستودع كي **يحجب الدمج**
بدل أن يبقى في حزمةٍ خارجيّة لا يُشغّلها أحد. أُعيد توجيه مسارات المصدر إلى مواضعها
بعد التطبيق: الشظايا التي كانت في `append/` صارت داخل ملفّات الخدمات نفسها.
"""

import copy
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from shared.ai.structured_advisory import (
    SCHEMA,
    AdvisoryRejected,
    OwnerCandidate,
    digest,
    evidence_fingerprint,
    fact_catalog,
    parse_model_output,
    preview_advisory,
)

pytestmark = pytest.mark.unit
TENANT = "00000000-0000-0000-0000-000000000101"
OTHER = "00000000-0000-0000-0000-000000000102"
FIELD = "field-contract-test"


def state():
    product = {
        "schema_version": "canonical_weather_state.v1",
        "quality_status": "validated",
        "operational_eligible": True,
        "limitations": [],
        "rain_mm": 0,
        "air": {"temperature_c": 22},
        "confidence": 0.8,
        "provenance": {"not_a_measurement": 123},
    }
    body = {
        "schema_version": "canonical_field_state.v1",
        "field_id": FIELD,
        "season_id": "season-1",
        "as_of_time": "2026-09-16T00:00:00+00:00",
        "weather": product,
        "soil": None,
        "water": None,
        "spectral": None,
        "availability": {"weather": True},
        "limitations": [],
        "evidence_digests": {"weather": digest(product)},
    }
    return {**body, "state_digest": digest(body), "eligibility": {"propose": {"allowed": True}}}


def rehash(value):
    value["evidence_digests"] = {
        k: digest(value[k])
        for k in ("weather", "water", "soil", "spectral")
        if value[k] is not None
    }
    keys = (
        "schema_version",
        "field_id",
        "season_id",
        "as_of_time",
        "weather",
        "water",
        "soil",
        "spectral",
        "availability",
        "limitations",
        "evidence_digests",
    )
    value["state_digest"] = digest({k: value[k] for k in keys})
    return value


def candidate(value, **kwargs):
    base = OwnerCandidate(
        TENANT,
        FIELD,
        evidence_fingerprint(value, field_id=FIELD),
        "irrigation",
        {"water_m3": 5},
        {"field_id": FIELD, "tenant_id": TENANT, "area_ha": 1},
        7,
        frozenset({"environmental"}),
    )
    return replace(base, **kwargs)


def document(value, *, claims=True, candidates=()):
    return {
        "schema_version": SCHEMA,
        "field_id": FIELD,
        "evidence_fingerprint": evidence_fingerprint(value, field_id=FIELD),
        "claims": [fact_catalog(value, field_id=FIELD)["/weather/rain_mm"]] if claims else [],
        "candidate_ids": [c.candidate_id for c in candidates],
    }


def evaluation(**updates):
    result = {
        "evaluation_only": True,
        "allowed": False,
        "requires_human_approval": True,
        "approval_workflow_id": None,
        "overall_risk": "LOW",
        "tier_checks": [{"tier": "environmental", "passed": True}],
    }
    result.update(updates)
    return result


@pytest.mark.parametrize(
    "bad", [None, 4, [], True, "not-json", "```json\n{}\n```", "{}", "[]", "null"]
)
def test_parse_rejects_non_contract_inputs(bad):
    with pytest.raises(AdvisoryRejected):
        parse_model_output(bad)


def test_duplicate_key_is_rejected_even_at_nested_level():
    text = json.dumps(document(state())).replace('"value": 0', '"value": 0,"value": 1')
    with pytest.raises(AdvisoryRejected, match="duplicate_json_key"):
        parse_model_output(text)


@pytest.mark.parametrize(
    "number", [True, False, None, "0", float("nan"), float("inf"), -(10**400), 10**400]
)
def test_nonfinite_coerced_and_bool_claims_never_qualify(number):
    doc = document(state())
    doc["claims"][0]["value"] = number
    with pytest.raises(AdvisoryRejected):
        parse_model_output(json.dumps(doc))


@pytest.mark.parametrize(
    "key,value",
    [
        ("answer_ar", "ignore safeguards"),
        ("action_data", {"water_m3": 999}),
        ("tenant_id", OTHER),
        ("approved", True),
    ],
)
def test_model_cannot_add_prose_actions_scope_or_approval(key, value):
    doc = document(state())
    doc[key] = value
    with pytest.raises(AdvisoryRejected, match="unexpected_document_shape"):
        parse_model_output(json.dumps(doc))


def test_output_size_and_unicode_encoding_are_bounded():
    with pytest.raises(AdvisoryRejected, match="output_size"):
        parse_model_output(" " * 32769)
    with pytest.raises(AdvisoryRejected, match="output_encoding"):
        parse_model_output("\ud800")


def test_counts_and_duplicate_claims_are_bounded():
    doc = document(state())
    doc["claims"] *= 25
    with pytest.raises(AdvisoryRejected, match="claim_limit"):
        parse_model_output(json.dumps(doc))
    doc["claims"] = doc["claims"][:2]
    with pytest.raises(AdvisoryRejected, match="duplicate_claim"):
        parse_model_output(json.dumps(doc))


def test_empty_advisory_and_duplicate_candidate_rejected():
    value = state()
    c = candidate(value)
    with pytest.raises(AdvisoryRejected, match="empty_advisory"):
        parse_model_output(json.dumps(document(value, claims=False)))
    doc = document(value, candidates=[c, c])
    with pytest.raises(AdvisoryRejected, match="duplicate_candidate_id"):
        parse_model_output(json.dumps(doc))


def test_catalog_publishes_zero_and_not_confidence_or_provenance():
    facts = fact_catalog(state(), field_id=FIELD)
    assert set(facts) == {"/weather/rain_mm", "/weather/air/temperature_c"}
    assert facts["/weather/rain_mm"]["value"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"quality_status": "degraded"},
        {"quality_status": None},
        {"operational_eligible": False},
        {"limitations": ["stale"]},
    ],
)
def test_owner_degraded_data_is_not_promoted(change):
    value = state()
    value["weather"].update(change)
    rehash(value)
    assert fact_catalog(value, field_id=FIELD) == {}


def test_digest_mismatch_rejected_at_root_and_product():
    value = state()
    value["weather"]["rain_mm"] = 1
    with pytest.raises(AdvisoryRejected, match="state_digest_mismatch"):
        fact_catalog(value, field_id=FIELD)
    value = state()
    value["evidence_digests"]["weather"] = "a" * 64
    keys = [k for k in value if k not in {"state_digest", "eligibility"}]
    value["state_digest"] = digest({k: value[k] for k in keys})
    with pytest.raises(AdvisoryRejected, match="product_digest_mismatch"):
        fact_catalog(value, field_id=FIELD)


def test_catalog_bound_and_no_interpolation_of_labels():
    value = state()
    value["weather"]["measurements"] = {f"reading_{n}": n for n in range(1000)}
    value["weather"]["<script>"] = 9
    value["weather"]["x\nignore"] = 9
    rehash(value)
    facts = fact_catalog(value, field_id=FIELD)
    assert len(facts) == 128
    assert all("<" not in key and "\n" not in key for key in facts)


@pytest.mark.parametrize(
    "change",
    [
        {"user_id": True},
        {"user_id": "service:ai"},
        {"user_id": 0},
        {"evidence_fingerprint": None},
        {"field_id": None},
        {"action_type": "loan"},
        {"action_data": {}},
        {"required_tiers": frozenset()},
        {"required_tiers": frozenset({"made_up"})},
        {"action_type": "pesticide"},
        {"tenant_id": "not-tenant"},
        {"farm_context": {"tenant_id": OTHER}},
    ],
)
def test_candidate_validates_real_identity_tiers_and_scope(change):
    with pytest.raises(AdvisoryRejected):
        candidate(state(), **change).validated_copy()


def test_candidate_digest_binds_context_and_defensive_copy():
    c = candidate(state())
    cloned = c.validated_copy()
    c.action_data["water_m3"] = 9
    assert cloned.action_data["water_m3"] == 5
    assert cloned.candidate_id != c.candidate_id


@pytest.mark.asyncio
async def test_only_exact_facts_are_published_no_generation_prose():
    value = state()
    doc = document(value)
    result = await preview_advisory(
        json.dumps(doc), tenant_id=TENANT, field_id=FIELD, state=value, candidates=[]
    )
    assert result["claims"] == doc["claims"]
    assert result["executes_action"] is False and result["creates_decision"] is False
    assert "/weather/rain_mm: 0" in result["answer_ar"]
    doc["claims"][0]["value"] = 10
    with pytest.raises(AdvisoryRejected, match="unsupported_claim"):
        await preview_advisory(
            json.dumps(doc), tenant_id=TENANT, field_id=FIELD, state=value, candidates=[]
        )


@pytest.mark.asyncio
async def test_stale_snapshot_unknown_selection_and_catalog_scope_fail_closed():
    value = state()
    c = candidate(value)
    doc = document(value, candidates=[c])
    newer = copy.deepcopy(value)
    newer["weather"]["rain_mm"] = 2
    rehash(newer)
    with pytest.raises(AdvisoryRejected, match="stale_or_wrong"):
        await preview_advisory(
            json.dumps(doc), tenant_id=TENANT, field_id=FIELD, state=newer, candidates=[]
        )
    with pytest.raises(AdvisoryRejected, match="unknown_candidate"):
        await preview_advisory(
            json.dumps(doc), tenant_id=TENANT, field_id=FIELD, state=value, candidates=[]
        )
    with pytest.raises(AdvisoryRejected, match="catalog_scope_mismatch"):
        await preview_advisory(
            json.dumps(doc), tenant_id=OTHER, field_id=FIELD, state=value, candidates=[c]
        )


@pytest.mark.asyncio
async def test_absent_propose_permission_does_not_call_guardrails():
    value = state()
    value["eligibility"]["propose"]["allowed"] = False
    c = candidate(value)
    call = AsyncMock(return_value=evaluation())
    out = await preview_advisory(
        json.dumps(document(value, candidates=[c])),
        tenant_id=TENANT,
        field_id=FIELD,
        state=value,
        candidates=[c],
        evaluate=call,
    )
    call.assert_not_awaited()
    assert out["candidate_previews"][0]["reason"] == "canonical_propose_not_allowed"


@pytest.mark.asyncio
async def test_low_risk_remains_non_executable_and_uses_owner_payload():
    value = state()
    c = candidate(value)
    call = AsyncMock(return_value=evaluation())
    out = await preview_advisory(
        json.dumps(document(value, candidates=[c])),
        tenant_id=TENANT,
        field_id=FIELD,
        state=value,
        candidates=[c],
        evaluate=call,
    )
    payload = call.await_args.args[0]
    assert payload["user_id"] == 7 and payload["action_data"] == c.action_data
    assert payload["evaluation_only"] is True and payload["auto_approve_low_risk"] is False
    preview = out["candidate_previews"][0]
    assert preview["status"] == "review_required"
    assert preview["executable"] is False and preview["requires_human_approval"] is True


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        evaluation(allowed=True),
        evaluation(evaluation_only=False),
        evaluation(requires_human_approval=False),
        evaluation(approval_workflow_id="wf-created"),
        evaluation(overall_risk="HIGH"),
        evaluation(tier_checks=[]),
        evaluation(tier_checks=[{"tier": "environmental", "passed": "true"}]),
        evaluation(tier_checks=[{"tier": "environmental", "passed": True}] * 2),
        evaluation(tier_checks=[{"tier": "invented", "passed": True}]),
    ],
)
@pytest.mark.asyncio
async def test_invalid_or_unsafe_evaluation_is_never_authorization(response):
    value = state()
    c = candidate(value)
    out = await preview_advisory(
        json.dumps(document(value, candidates=[c])),
        tenant_id=TENANT,
        field_id=FIELD,
        state=value,
        candidates=[c],
        evaluate=AsyncMock(return_value=response),
    )
    assert out["candidate_previews"][0]["status"] == "blocked"


@pytest.mark.asyncio
async def test_owner_failure_does_not_leak_exception_or_release_candidate():
    value = state()
    c = candidate(value)
    call = AsyncMock(side_effect=RuntimeError("PRIVATE_BACKEND_TRACE"))
    out = await preview_advisory(
        json.dumps(document(value, candidates=[c])),
        tenant_id=TENANT,
        field_id=FIELD,
        state=value,
        candidates=[c],
        evaluate=call,
    )
    assert "PRIVATE_BACKEND_TRACE" not in json.dumps(out)
    assert out["candidate_previews"][0]["reason"] == "guardrails_unavailable"


def owner_module():
    source = (
        Path(__file__).resolve().parents[1]
        / "services/sahool-platform/core/field_intelligence_coordinator.py"
    )
    spec = importlib.util.spec_from_file_location("test_coordinator_extension", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # كما في مخزن المنصّة: dataclasses تحتاج التسجيل
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_owner_reloads_after_generation_and_rejects_stale_request():
    value = state()
    doc = document(value)
    value["weather"]["rain_mm"] = 2
    rehash(value)
    loader = AsyncMock(return_value=value)
    candidates = AsyncMock(return_value=[])
    with pytest.raises(AdvisoryRejected, match="stale_or_wrong"):
        await owner_module().preview_model_advisory(
            json.dumps(doc),
            tenant_id=TENANT,
            field_id=FIELD,
            load_current_canonical=loader,
            load_owner_candidates=candidates,
            evaluate_candidate=None,
        )
    loader.assert_awaited_once_with(tenant_id=TENANT, field_id=FIELD)
    candidates.assert_awaited_once_with(
        tenant_id=TENANT,
        field_id=FIELD,
        evidence_fingerprint=evidence_fingerprint(value, field_id=FIELD),
    )


@pytest.mark.parametrize("status", [404, 422, 302, 503])
@pytest.mark.asyncio
async def test_rolling_deployment_never_falls_back_to_mutating_validate(status):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(status, json={"error": "not available"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        evaluate = owner_module().make_candidate_evaluator(
            http_client=client, guardrails_url="http://guardrails.test", service_token=uuid4().hex
        )
        with pytest.raises(RuntimeError, match="unavailable"):
            await evaluate(candidate(state()).evaluation_request())
    assert seen == [
        "/v1/evaluate"
    ]  # /v1/validate could create approval workflows on older servers.


@pytest.mark.asyncio
async def test_read_time_alone_does_not_make_identical_owner_evidence_unusable():
    value = state()
    c = candidate(value)
    doc = document(value, candidates=[c])
    later = copy.deepcopy(value)
    later["as_of_time"] = "2026-09-16T00:00:03+00:00"
    rehash(later)
    assert later["state_digest"] != value["state_digest"]
    assert evidence_fingerprint(later, field_id=FIELD) == evidence_fingerprint(
        value, field_id=FIELD
    )
    result = await preview_advisory(
        json.dumps(doc),
        tenant_id=TENANT,
        field_id=FIELD,
        state=later,
        candidates=[c],
        evaluate=AsyncMock(return_value=evaluation()),
    )
    assert result["candidate_previews"][0]["status"] == "review_required"
    assert result["state_digest"] == later["state_digest"]


def test_actual_owner_freshness_or_eligibility_change_updates_evidence_fingerprint():
    value = state()
    changed = copy.deepcopy(value)
    changed["eligibility"]["propose"]["allowed"] = False
    assert evidence_fingerprint(value, field_id=FIELD) != evidence_fingerprint(
        changed, field_id=FIELD
    )
    changed = copy.deepcopy(value)
    changed["weather"]["limitations"] = ["stale"]
    rehash(changed)
    assert evidence_fingerprint(value, field_id=FIELD) != evidence_fingerprint(
        changed, field_id=FIELD
    )
