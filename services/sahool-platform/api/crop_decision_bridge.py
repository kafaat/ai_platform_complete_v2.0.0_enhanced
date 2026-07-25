"""WX-10.6 — Crop Intelligence → Decision Candidate boundary.

Ownership split: **Crop Intelligence interprets evidence; decision-service owns the
decision and its approval record.** This bridge builds a *reviewable candidate* — never
a final decision. It never approves, dispatches, executes, creates a task, or issues an
equipment command.

Two modes:
- ``submit=False`` → **preview only**, writes nothing (no network call).
- ``submit=True``  → records a ``pending_approval`` candidate in decision-service and is
  **fail-closed**: it reports ``pending_approval`` *only* when the service response proves
  ``persisted=true`` and ``authoritative=true``, and the candidate itself always carries
  ``status="pending_approval"`` + ``approval_required=True``.

Lineage invariant: the candidate (evidence bundle + ``candidate_lineage_id``) is built
**once, identically** for preview and submit — the submit path never rebuilds or mutates
the evidence. ``candidate_lineage_id`` is a deterministic hash of the evidence bundle: it
is stable for identical inputs and changes when the GDD product (accumulated GDD /
``gdd_lineage_id`` / contributing state ids) or any evidence changes.

Fail-closed refusals (never a fake success):
- missing evidence / empty evidence ids,
- missing ``recommendation_context`` or ``decision_boundary``,
- boundary that is already a final decision, or whose consumer is not decision-service,
- boundary that does not require approval,
- decision-service unavailable, or a response that does not prove authoritative
  persistence.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException

from api.decision_service_client import record_decision

_ENGINE_DOWN_CODES = {502, 503, 504}
CANDIDATE_DECISION_TYPE = "crop_decision_candidate"
CANDIDATE_STAGE = "candidate"


def _canonical_lineage_id(evidence: dict[str, Any]) -> str:
    """Deterministic candidate lineage id over the evidence bundle (last-input-stable)."""
    blob = json.dumps(evidence, sort_keys=True, separators=(",", ":"), default=str)
    return "cand/" + hashlib.sha1(blob.encode(), usedforsecurity=False).hexdigest()[:16]


def build_crop_decision_candidate(
    crop_intelligence: dict[str, Any],
    *,
    gdd_product: dict[str, Any] | None = None,
    spectral_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a reviewable decision candidate from a ``crop_intelligence_state.v2`` block.

    ``crop_intelligence`` is the engine's CI block (interpretation). ``gdd_product`` is the
    canonical weather GDD product — the authoritative source of accumulated GDD and GDD
    lineage. This function interprets/relays only; it never decides. Fail-closed on any
    missing/inconsistent evidence or boundary.

    ``spectral_provenance`` (DECISION-CENTER-UNIFY-01): declares the **trust basis** of the
    candidate's spectral evidence so the human/policy reviewer at decision-service sees
    whether it was read server-authoritatively (``source="raster-service"``) or supplied by
    the client (``source="client"``, i.e. unverified). It is a transparency relay only — no
    fabrication: when unknown/None it is recorded as ``source="unknown"``. When the spectral
    input is client-supplied-unverified, ``client_supplied_spectral_unverified`` is added to
    the candidate limitations (so it flows into ``candidate_lineage_id`` — an unverified
    candidate is cryptographically distinct from a server-authoritative one for identical
    agronomy). This is the substrate for a future provenance-based submit gate; it does NOT
    by itself allow submit (that gate stays fail-closed until server-authoritative context
    assembly covers the full contract).
    """
    if not isinstance(crop_intelligence, dict):
        raise ValueError("crop_intelligence state is required")

    context = crop_intelligence.get("recommendation_context")
    if not isinstance(context, dict):
        raise ValueError("crop recommendation context is missing")
    boundary = context.get("decision_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("recommendation context has no decision_boundary")
    if boundary.get("is_decision") is not False:
        raise ValueError("crop recommendation context must not be a final decision")
    if boundary.get("consumer") != "decision-service":
        raise ValueError("decision boundary consumer must be decision-service")
    if boundary.get("approval_required") is not True:
        raise ValueError("decision boundary must require approval")

    field_id = crop_intelligence.get("field_id")
    season_id = crop_intelligence.get("season_id")
    if not field_id or not season_id:
        raise ValueError("field_id and season_id are required")

    # gdd_product is the SOLE authoritative source of accumulated GDD + GDD lineage. It is
    # never re-derived from daily_gdd nor substituted from crop_intelligence. Fail-closed if
    # the canonical product or any of its three lineage anchors is missing, BEFORE any
    # candidate is built.
    if not isinstance(gdd_product, dict):
        raise ValueError("canonical gdd_product is required (fail-closed)")
    accumulated_gdd = gdd_product.get("accumulated_gdd")
    gdd_lineage_id = gdd_product.get("gdd_lineage_id")
    contributing_state_ids = gdd_product.get("contributing_state_ids")
    if accumulated_gdd is None:
        raise ValueError("gdd_product.accumulated_gdd is required (fail-closed)")
    if not gdd_lineage_id:
        raise ValueError("gdd_product.gdd_lineage_id is required (fail-closed)")
    if not contributing_state_ids:
        raise ValueError("gdd_product.contributing_state_ids is required (fail-closed)")
    # Preserve canonical order (contributing_state_ids are already canonically ordered).
    contributing_state_ids = list(contributing_state_ids)

    phenology = crop_intelligence.get("phenology") or {}
    # Spectral trust basis (transparency relay — no fabrication). ``unverified`` ⇒ a
    # limitation the reviewer sees AND that flows into candidate lineage.
    sp = spectral_provenance if isinstance(spectral_provenance, dict) else {}
    spectral_source = str(sp.get("source") or "unknown")
    spectral_unverified = bool(sp.get("unverified", False))
    limitations = list(
        dict.fromkeys(
            [
                *(crop_intelligence.get("limitations") or []),
                *(gdd_product.get("limitations") or []),
                *(["client_supplied_spectral_unverified"] if spectral_unverified else []),
            ]
        )
    )

    # Evidence ids: crop-intelligence evidence ⊕ context evidence ⊕ GDD lineage — lossless.
    evidence_ids = list(
        dict.fromkeys(
            [
                *(crop_intelligence.get("evidence_ids") or []),
                *(context.get("evidence_ids") or []),
                *contributing_state_ids,
                gdd_lineage_id,
            ]
        )
    )

    # Candidate lineage material — EXACTLY the fields specified for WX-10.6: stable for
    # identical inputs, GDD-sensitive (any change to gdd_lineage_id / ordered
    # contributing_state_ids / accumulated_gdd changes the candidate lineage).
    lineage_material = {
        "field_id": field_id,
        "season_id": season_id,
        "crop_schema": crop_intelligence.get("schema"),
        "engine_version": crop_intelligence.get("engine_version"),
        "recommendation_context": context,
        "gdd_lineage_id": gdd_lineage_id,
        "contributing_state_ids": contributing_state_ids,  # ordered
        "accumulated_gdd": accumulated_gdd,
        "limitations": limitations,
    }
    candidate_lineage_id = _canonical_lineage_id(lineage_material)

    # Evidence bundle — the scientific content the human/policy reviews (superset of the
    # lineage material; GDD anchors sourced only from gdd_product).
    evidence: dict[str, Any] = {
        "field_id": field_id,
        "season_id": season_id,
        "stage": context.get("stage") or phenology.get("stage") or phenology.get("current_stage"),
        "phenology": phenology,
        "accumulated_gdd": accumulated_gdd,
        "gdd_lineage_id": gdd_lineage_id,
        "contributing_state_ids": contributing_state_ids,
        "gdd_series_quality_status": gdd_product.get("series_quality_status"),
        "stress": {
            "active_codes": list(context.get("active_stress_codes") or []),
            "flags": list(crop_intelligence.get("stress_flags") or []),
            "memory_state": context.get("stress_memory_state"),
            "urgency": context.get("urgency"),
            "urgent_factors": list(context.get("urgent_factors") or []),
        },
        "confidence": crop_intelligence.get("confidence"),
        "limitations": limitations,
        "evidence_ids": evidence_ids,
        # DECISION-CENTER-UNIFY-01: the candidate declares its spectral trust basis so the
        # reviewer/policy at decision-service can gate on it. server-authoritative vs
        # client-supplied is now first-class + persisted (record_decision sends this evidence).
        "spectral_provenance": {"source": spectral_source, "unverified": spectral_unverified},
        "versions": {
            "engine_version": crop_intelligence.get("engine_version"),
            "schema": crop_intelligence.get("schema"),
            "gdd_calculation_version": gdd_product.get("calculation_version"),
            "gdd_series_quality_status": gdd_product.get("series_quality_status"),
            "stress_memory_version": (crop_intelligence.get("stress_memory") or {}).get(
                "product_version"
            ),
        },
    }

    return {
        "decision_type": CANDIDATE_DECISION_TYPE,
        "field_id": field_id,
        "season_id": season_id,
        "status": "pending_approval",
        "approval_required": True,
        "candidate_lineage_id": candidate_lineage_id,
        "evidence": evidence,
        "evidence_ids": evidence_ids,
        "confidence": crop_intelligence.get("confidence"),
        "limitations": limitations,
        "ownership": {
            "interpretation": "crop-intelligence-engine",
            "decision": "decision-service",
        },
        "calibrated": bool(crop_intelligence.get("calibrated", False)),
    }


def _preview(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval_state": "preview",
        "submitted": False,
        "persisted": False,
        "authoritative": False,
        "candidate_id": None,
        "candidate_lineage_id": candidate["candidate_lineage_id"],
        "candidate": candidate,
        "limitations": candidate["limitations"],
    }


async def submit_crop_decision_candidate(
    crop_intelligence: dict[str, Any],
    *,
    gdd_product: dict[str, Any] | None = None,
    spectral_provenance: dict[str, Any] | None = None,
    tenant_id: str | None,
    submit: bool = False,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Preview (no write) or submit a ``pending_approval`` candidate — fail-closed.

    The candidate is built **once**; preview and submit share the identical evidence and
    ``candidate_lineage_id``. Submit records the *same* candidate into decision-service and
    only returns ``pending_approval`` when the service proves authoritative persistence.
    ``spectral_provenance`` (trust basis) is relayed into the candidate evidence unchanged.
    """
    candidate = build_crop_decision_candidate(
        crop_intelligence, gdd_product=gdd_product, spectral_provenance=spectral_provenance
    )
    if not submit:
        return _preview(candidate)

    # DECISION-PATH: submit → record a reviewable candidate ONLY. decision-service owns
    # persistence + the approval record. No dispatch / execution / task / equipment command.
    record_payload = {
        "field_id": candidate["field_id"],
        "decision_type": candidate["decision_type"],
        "stage": CANDIDATE_STAGE,
        "decision_value": candidate,  # full candidate incl. lineage + evidence, unchanged
        "created_by": created_by,
    }
    try:
        result = await record_decision(record_payload, tenant_id=tenant_id)
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            # fail-closed: decision-service unavailable → no candidate, no fake success.
            raise HTTPException(
                status_code=503,
                detail="decision-service unavailable — candidate not submitted (fail-closed)",
            ) from exc
        raise

    # fail-closed proof. The record endpoint does not return a `status` field, so we do NOT
    # infer pending_approval locally from the response: instead we require the authoritative
    # response to point to the SAME record we submitted (non-empty decision_id + echoed
    # `stage == candidate`), while the persisted candidate itself carries
    # status=pending_approval + approval_required=True inside decision_value.
    candidate_id = result.get("decision_id") or result.get("id")
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and bool(candidate_id)
        and result.get("stage") == CANDIDATE_STAGE
        and candidate["status"] == "pending_approval"
        and candidate["approval_required"] is True
    )
    if not proven:
        raise HTTPException(
            status_code=502,
            detail=(
                "decision-service did not confirm authoritative persistence of the "
                "pending_approval candidate — fail-closed"
            ),
        )

    return {
        "approval_state": "pending_approval",
        "submitted": True,
        "persisted": True,
        "authoritative": True,
        "candidate_id": candidate_id,
        "candidate_lineage_id": candidate["candidate_lineage_id"],
        "candidate": candidate,
        "limitations": candidate["limitations"],
    }
