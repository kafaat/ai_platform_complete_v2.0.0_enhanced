"""Bounded, read-only publication of owner-verified numeric facts.

The model selects facts and EXISTING owner-issued candidate IDs. It cannot supply
free prose, doses, farm context, approval state, or a replacement tenant identity.
No function in this module writes a decision or dispatches an action.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

SCHEMA = "sahool.structured_advisory.v1"
MAX_BYTES = 32_768
MAX_CLAIMS = 24
MAX_CANDIDATES = 3
PRODUCTS = frozenset({"soil", "water", "weather", "spectral"})
HEALTHY = frozenset({"validated", "verified"})
HEX = re.compile(r"[a-f0-9]{64}\Z")
SEGMENT = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,79}\Z")
# These are declarations/metadata, not measurements to publish as field facts.
SKIP = frozenset(
    {
        "confidence",
        "provenance",
        "metadata",
        "quality",
        "limitations",
        "evidence",
        "sources",
        "source",
        "coverage",
        "availability",
    }
)
LABELS = {
    "irrigation": "مقترح ري",
    "fertilization": "مقترح تسميد",
    "pesticide": "مقترح معالجة آفة",
    "harvest": "مقترح حصاد",
}


class AdvisoryRejected(ValueError):
    """Stable error codes deliberately do not echo untrusted generated text."""


def digest(value: Any) -> str:
    """Same JSON digest convention used by the canonical field-state composer."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _number(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _keys(value: Any, keys: set[str], code: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise AdvisoryRejected(code)
    return value


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise AdvisoryRejected("duplicate_json_key")
        out[key] = value
    return out


def parse_model_output(text: str) -> dict:
    if not isinstance(text, str):
        raise AdvisoryRejected("output_size_or_type")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise AdvisoryRejected("output_encoding") from exc
    if size > MAX_BYTES:
        raise AdvisoryRejected("output_size_or_type")

    def invalid_constant(_: str):
        raise AdvisoryRejected("nonfinite_json_number")

    try:
        document = json.loads(
            text, object_pairs_hook=_unique_pairs, parse_constant=invalid_constant
        )
    except AdvisoryRejected:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise AdvisoryRejected("invalid_json") from exc
    _keys(
        document,
        {"schema_version", "field_id", "evidence_fingerprint", "claims", "candidate_ids"},
        "unexpected_document_shape",
    )
    if document["schema_version"] != SCHEMA:
        raise AdvisoryRejected("unsupported_advisory_schema")
    if not isinstance(document["field_id"], str) or not document["field_id"]:
        raise AdvisoryRejected("field_id_required")
    if not isinstance(document["evidence_fingerprint"], str) or not HEX.fullmatch(
        document["evidence_fingerprint"]
    ):
        raise AdvisoryRejected("evidence_fingerprint_required")
    claims, candidates = document["claims"], document["candidate_ids"]
    if not isinstance(claims, list) or len(claims) > MAX_CLAIMS:
        raise AdvisoryRejected("claim_limit")
    if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
        raise AdvisoryRejected("candidate_limit")
    if not claims and not candidates:
        raise AdvisoryRejected("empty_advisory")
    seen = set()
    for claim in claims:
        _keys(claim, {"path", "value", "product_digest"}, "unexpected_claim_shape")
        if not isinstance(claim["path"], str) or claim["path"] in seen:
            raise AdvisoryRejected("invalid_or_duplicate_claim")
        seen.add(claim["path"])
        if not _number(claim["value"]):
            raise AdvisoryRejected("claim_not_finite_numeric")
        if not isinstance(claim["product_digest"], str) or not HEX.fullmatch(
            claim["product_digest"]
        ):
            raise AdvisoryRejected("product_digest_required")
    if any(not isinstance(x, str) or not HEX.fullmatch(x) for x in candidates):
        raise AdvisoryRejected("invalid_candidate_id")
    if len(set(candidates)) != len(candidates):
        raise AdvisoryRejected("duplicate_candidate_id")
    return document


def fact_catalog(state: Mapping[str, Any], *, field_id: str) -> dict[str, dict]:
    """Only a fresh owner-loaded snapshot may be passed here, never request JSON.

    Labels are literal source paths, not inferred agronomic meaning or units.
    The canonical owner already judges age/fitness; no second freshness policy is
    invented here. Consumers must reload the owner state for every publication.
    """
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != "canonical_field_state.v1"
        or state.get("field_id") != field_id
        or not isinstance(state.get("state_digest"), str)
        or not HEX.fullmatch(state["state_digest"])
    ):
        raise AdvisoryRejected("canonical_scope_or_schema")
    body_keys = (
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
    if any(key not in state for key in body_keys):
        raise AdvisoryRejected("canonical_body_incomplete")
    if digest({key: state[key] for key in body_keys}) != state["state_digest"]:
        raise AdvisoryRejected("canonical_state_digest_mismatch")
    if not isinstance(state["evidence_digests"], dict):
        raise AdvisoryRejected("canonical_evidence_digests_invalid")
    catalog: dict[str, dict] = {}
    for product_name in sorted(PRODUCTS):
        product = state.get(product_name)
        if not isinstance(product, dict):
            continue
        if (
            not isinstance(product.get("quality_status"), str)
            or product.get("quality_status") not in HEALTHY
            or product.get("operational_eligible") is False
            or product.get("limitations")
        ):
            continue
        declared = (state.get("evidence_digests") or {}).get(product_name)
        actual = digest(product)
        if declared != actual:
            raise AdvisoryRejected("canonical_product_digest_mismatch")

        def walk(node: dict, path: str, depth: int = 0, actual=actual) -> None:
            if depth > 5 or len(catalog) >= 128:
                return
            for key in sorted(key for key in node if isinstance(key, str)):
                if len(catalog) >= 128:
                    return
                value = node[key]
                if (
                    not isinstance(key, str)
                    or not SEGMENT.fullmatch(key)
                    or key in SKIP
                    or key.endswith(("_id", "_digest", "_hash"))
                ):
                    continue
                pointer = path + "/" + key
                if _number(value):
                    catalog[pointer] = {"path": pointer, "value": value, "product_digest": actual}
                elif isinstance(value, dict):
                    walk(value, pointer, depth + 1)

        walk(product, "/" + product_name)
    return catalog


def evidence_fingerprint(state: dict, *, field_id: str) -> str:
    """Bind actual owner products, season and eligibility, not read-time alone.

    canonical_field_state.state_digest includes the composer's as_of_time.
    Reloading the same products can therefore produce a different state_digest.
    This separately named fingerprint excludes ONLY that envelope read timestamp;
    product digests (including their owner freshness declarations) stay intact.
    The original current state_digest is still returned for audit, never replaced.
    """
    fact_catalog(state, field_id=field_id)  # verifies the full current snapshot first
    keys = (
        "schema_version",
        "field_id",
        "season_id",
        "evidence_digests",
        "availability",
        "limitations",
        "eligibility",
    )
    return digest({key: state.get(key) for key in keys})


@dataclass(frozen=True)
class OwnerCandidate:
    """Construct only in the decision owner, from server-owned typed candidates."""

    tenant_id: str
    field_id: str
    evidence_fingerprint: str
    action_type: str
    action_data: dict
    farm_context: dict
    user_id: int
    required_tiers: frozenset[str]

    def validated_copy(self) -> OwnerCandidate:
        try:
            tenant = str(UUID(self.tenant_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise AdvisoryRejected("candidate_tenant_invalid") from exc
        if (
            not isinstance(self.field_id, str)
            or not 0 < len(self.field_id) <= 50
            or not isinstance(self.action_type, str)
            or self.action_type not in LABELS
            or not isinstance(self.evidence_fingerprint, str)
            or not HEX.fullmatch(self.evidence_fingerprint)
            or type(self.user_id) is not int
            or not 0 < self.user_id <= 2147483647
            or not isinstance(self.action_data, dict)
            or not self.action_data
            or not isinstance(self.farm_context, dict)
            or not self.farm_context
            or not isinstance(self.required_tiers, frozenset)
            or not self.required_tiers
            or not self.required_tiers <= {"chemical", "environmental", "economic"}
        ):
            raise AdvisoryRejected("owner_candidate_invalid")
        # Owner chooses required tiers according to its existing contract; it may
        # not omit chemical/environmental for the corresponding action kind.
        minimum = {"environmental"}
        if self.action_type in {"pesticide", "fertilization"}:
            minimum.add("chemical")
        if not minimum <= self.required_tiers:
            raise AdvisoryRejected("candidate_required_tiers_incomplete")
        for scope_key, expected in (("tenant_id", tenant), ("field_id", self.field_id)):
            for value in (self.action_data, self.farm_context):
                if scope_key in value and value[scope_key] != expected:
                    raise AdvisoryRejected("candidate_scope_mismatch")
        try:
            frozen = json.loads(
                json.dumps(
                    {"action": self.action_data, "context": self.farm_context}, allow_nan=False
                )
            )
        except (ValueError, TypeError, RecursionError) as exc:
            raise AdvisoryRejected("owner_candidate_nonjson") from exc
        return OwnerCandidate(
            tenant,
            self.field_id,
            self.evidence_fingerprint,
            self.action_type,
            frozen["action"],
            frozen["context"],
            self.user_id,
            self.required_tiers,
        )

    @property
    def candidate_id(self) -> str:
        return digest(
            {
                "tenant_id": self.tenant_id,
                "field_id": self.field_id,
                "evidence_fingerprint": self.evidence_fingerprint,
                "action_type": self.action_type,
                "action_data": self.action_data,
                "farm_context": self.farm_context,
                "user_id": self.user_id,
                "required_tiers": sorted(self.required_tiers),
            }
        )

    def evaluation_request(self) -> dict:
        # This flag requires the paired guardrails evaluation-only patch. The
        # owner must verify its echo; an old service is not accepted as evaluated.
        return {
            "action_type": self.action_type,
            "action_data": self.action_data,
            "farm_context": self.farm_context,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "request_source": "system",
            "auto_approve_low_risk": False,
            "evaluation_only": True,
        }


Evaluator = Callable[[dict], Awaitable[dict]]


async def preview_advisory(
    text: str,
    *,
    tenant_id: str,
    field_id: str,
    state: dict,
    candidates: list[OwnerCandidate],
    evaluate: Evaluator | None = None,
) -> dict:
    """Validate each selection against the CURRENT snapshot and its owner catalog.

    A passing safety evaluation never authorizes execution or creates a decision.
    A missing evaluator, missing tier, old guardrails server or workflow receipt
    produces a blocked candidate; verified numeric facts may still be published.
    """
    try:
        tenant_id = str(UUID(tenant_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise AdvisoryRejected("tenant_uuid_required") from exc
    if not isinstance(candidates, list) or len(candidates) > 100:
        raise AdvisoryRejected("owner_catalog_invalid")
    doc = parse_model_output(text)
    catalog = fact_catalog(state, field_id=field_id)
    fingerprint = evidence_fingerprint(state, field_id=field_id)
    if doc["field_id"] != field_id or doc["evidence_fingerprint"] != fingerprint:
        raise AdvisoryRejected("stale_or_wrong_field_state")
    facts = []
    for claim in doc["claims"]:
        authoritative = catalog.get(claim["path"])
        if authoritative is None or claim != authoritative:
            raise AdvisoryRejected("unsupported_claim")
        facts.append(dict(authoritative))  # reconstruct from owner, not model text
    owned = {}
    for source in candidates:
        if not isinstance(source, OwnerCandidate):
            raise AdvisoryRejected("owner_candidate_type_invalid")
        candidate = source.validated_copy()
        if (
            candidate.tenant_id != tenant_id
            or candidate.field_id != field_id
            or candidate.evidence_fingerprint != evidence_fingerprint(state, field_id=field_id)
        ):
            raise AdvisoryRejected("owner_catalog_scope_mismatch")
        if candidate.candidate_id in owned:
            raise AdvisoryRejected("owner_catalog_duplicate")
        owned[candidate.candidate_id] = candidate
    if any(key not in owned for key in doc["candidate_ids"]):
        raise AdvisoryRejected("unknown_candidate")
    previews = []
    state_permits_proposal = (state.get("eligibility") or {}).get("propose", {}).get(
        "allowed"
    ) is True
    for key in doc["candidate_ids"]:
        candidate = owned[key]
        record = {
            "candidate_id": key,
            "action_type": candidate.action_type,
            "status": "blocked",
            "reason": "canonical_propose_not_allowed",
            "requires_human_approval": True,
            "executable": False,
        }
        if state_permits_proposal:
            record["reason"] = "guardrails_unavailable"
            if evaluate is not None:
                try:
                    response = await asyncio.wait_for(
                        evaluate(candidate.evaluation_request()), timeout=10.0
                    )
                    record.update(_evaluation_summary(response, candidate.required_tiers))
                except Exception:  # evaluation failure cannot release a candidate
                    record["reason"] = "guardrails_unavailable"
        previews.append(record)
    lines = [f"القيمة المعلنة من مالك البيانات {f['path']}: {f['value']}" for f in facts]
    for record in previews:
        if record["status"] == "review_required":
            lines.append(
                LABELS[record["action_type"]]
                + ": اجتاز التقييم الأولي؛ يحتاج موافقة بشرية وقراراً من مالك الخدمة، ولم يُنفّذ."
            )
        else:
            lines.append(
                LABELS[record["action_type"]] + ": محجوب؛ لم تكتمل شروط التقييم، ولم يُنفّذ."
            )
    return {
        "schema_version": SCHEMA,
        "field_id": field_id,
        "tenant_id": tenant_id,
        "state_digest": state["state_digest"],
        "evidence_fingerprint": fingerprint,
        "claims": facts,
        "candidate_previews": previews,
        "answer_ar": "\n".join(lines),
        "executes_action": False,
        "creates_decision": False,
        "validation_scope": "numeric_equality_to_owner_snapshot_not_scientific_certification",
    }


def _evaluation_summary(response: Any, required: frozenset[str]) -> dict:
    blocked = {"status": "blocked", "reason": "guardrails_contract_invalid"}
    if (
        not isinstance(response, dict)
        or response.get("evaluation_only") is not True
        or response.get("allowed") is not False
        or response.get("approval_workflow_id")
        or response.get("requires_human_approval") is not True
    ):
        return blocked
    checks = response.get("tier_checks")
    if not isinstance(checks, list):
        return blocked
    tiers = {}
    for check in checks:
        if (
            not isinstance(check, dict)
            or check.get("tier") not in {"chemical", "environmental", "economic"}
            or check["tier"] in tiers
        ):
            return blocked
        tiers[check["tier"]] = check
    if not required <= set(tiers) or any(
        check.get("passed") is not True for check in tiers.values()
    ):
        return {"status": "blocked", "reason": "guardrails_checks_not_passed"}
    if response.get("overall_risk") != "LOW":
        return {"status": "blocked", "reason": "guardrails_risk_not_low"}
    return {"status": "review_required", "reason": "evaluated_not_authorized"}


def model_selection_context(
    *, tenant_id: str, field_id: str, state: dict, candidates: list[OwnerCandidate]
) -> dict:
    """Bounded context for generation AFTER the existing tenant/provider gates.

    No raw action bodies, user identifiers or economic records are sent to the
    model. It can name an existing candidate; it cannot invent or edit its dose.
    The owner must reload state before calling preview_advisory after generation.
    """
    try:
        tenant = str(UUID(tenant_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise AdvisoryRejected("tenant_uuid_required") from exc
    facts = fact_catalog(state, field_id=field_id)
    if not isinstance(candidates, list) or len(candidates) > 100:
        raise AdvisoryRejected("owner_catalog_invalid")
    selections = []
    seen = set()
    for value in candidates:
        if not isinstance(value, OwnerCandidate):
            raise AdvisoryRejected("owner_candidate_type_invalid")
        candidate = value.validated_copy()
        if (
            candidate.tenant_id != tenant
            or candidate.field_id != field_id
            or candidate.evidence_fingerprint != evidence_fingerprint(state, field_id=field_id)
        ):
            raise AdvisoryRejected("owner_catalog_scope_mismatch")
        key = candidate.candidate_id
        if key in seen:
            raise AdvisoryRejected("owner_catalog_duplicate")
        seen.add(key)
        selections.append({"candidate_id": key, "action_type": candidate.action_type})
    return {
        "schema_version": SCHEMA,
        "field_id": field_id,
        "evidence_fingerprint": evidence_fingerprint(state, field_id=field_id),
        "available_claims": list(facts.values()),
        "available_candidates": selections,
        "max_selected_claims": MAX_CLAIMS,
        "max_selected_candidates": MAX_CANDIDATES,
        "instructions": "Return one JSON object with schema_version, field_id, evidence_fingerprint, claims, candidate_ids. "
        "Select exact available claims and existing IDs only. No prose, action_data, units or approval. "
        "If no evidence is available, generation must not be attempted.",
    }
