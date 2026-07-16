"""FII chemical-intervention lineage audit guard — Increment 2 (Audit Hardening).

Audit-only and backward-compatible: violations are REPORTED (with stable reason
codes) but never rejected while the mode is ``audit`` (the default). ``enforce`` is
available only via the explicit ``FII_CHEMICAL_LINEAGE_MODE=enforce`` setting and is
NOT part of this increment.

Beyond field presence, the guard performs *server-side* validation of the diagnosis
reference **when the owning service is reachable** (via an injectable resolver):
existence, not-expired, not-superseded, allowed review state, sufficient evidence,
and tenant / field / season agreement with the authenticated context. Any resolver
failure is recorded as ``VALIDATION_UNAVAILABLE`` — it is NEVER silently treated as a
pass (no network failure may become an implicit success).

This module is intentionally dependency-free (stdlib only; httpx imported lazily
inside the default resolver) so it can be promoted to a shared package and imported
by decision-service / actuator-service / odoo-bridge for their own boundaries.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol

logger = logging.getLogger(__name__)


# ─────────────────────────────── modes & boundaries ──────────────────────────
class ChemicalLineageMode(str, Enum):
    OFF = "off"
    AUDIT = "audit"
    ENFORCE = "enforce"


class ChemicalBoundary(str, Enum):
    """The CHEMICAL_INTERVENTION capability spans these boundaries. Human approval
    gates EXECUTION, not draft creation; diagnosis validity is required from SUBMIT on."""

    DRAFT = "draft"  # recommendation/prescription draft creation
    SUBMIT = "submit"  # recommendation submission for decision
    APPROVE = "approve"  # decision approval
    DISPATCH = "dispatch"  # dispatch authorization
    EXECUTE = "execute"  # execution request
    WORK_ORDER = "work_order"  # work-order creation
    INVENTORY_RESERVE = "inventory_reserve"  # material/inventory reservation
    ACTUATOR_DISPATCH = "actuator_dispatch"  # machine/actuator dispatch


# Strength order: which boundaries require full server-side diagnosis validation
# (everything at SUBMIT and "stronger") and which require human approval.
_ORDER = {
    ChemicalBoundary.DRAFT: 0,
    ChemicalBoundary.SUBMIT: 1,
    ChemicalBoundary.WORK_ORDER: 2,
    ChemicalBoundary.APPROVE: 3,
    ChemicalBoundary.INVENTORY_RESERVE: 3,
    ChemicalBoundary.DISPATCH: 4,
    ChemicalBoundary.ACTUATOR_DISPATCH: 4,
    ChemicalBoundary.EXECUTE: 5,
}
_REQUIRES_VALIDATION_FROM = 1  # SUBMIT and stronger validate the diagnosis
_REQUIRES_APPROVAL_FROM = 3  # APPROVE and stronger require human approval


class ViolationCode(str, Enum):
    MISSING_FIELD_ID = "MISSING_FIELD_ID"
    MISSING_SEASON_ID = "MISSING_SEASON_ID"
    MISSING_DIAGNOSIS_REF = "MISSING_DIAGNOSIS_REF"
    MISSING_EVIDENCE_REF = "MISSING_EVIDENCE_REF"
    EVIDENCE_DIGEST_MISSING = "EVIDENCE_DIGEST_MISSING"
    DIAGNOSIS_NOT_FOUND = "DIAGNOSIS_NOT_FOUND"
    DIAGNOSIS_EXPIRED = "DIAGNOSIS_EXPIRED"
    DIAGNOSIS_SUPERSEDED = "DIAGNOSIS_SUPERSEDED"
    REVIEW_STATE_NOT_ALLOWED = "REVIEW_STATE_NOT_ALLOWED"
    DIAGNOSIS_INSUFFICIENT_EVIDENCE = "DIAGNOSIS_INSUFFICIENT_EVIDENCE"  # explicit flag
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"  # level < threshold
    TENANT_MISMATCH = "TENANT_MISMATCH"
    FIELD_MISMATCH = "FIELD_MISMATCH"
    SEASON_MISMATCH = "SEASON_MISMATCH"
    MISSING_HUMAN_APPROVAL = "MISSING_HUMAN_APPROVAL"
    VALIDATION_UNAVAILABLE = "VALIDATION_UNAVAILABLE"


# ─────────────────────────────── resolver contract ───────────────────────────
class ResolverUnavailable(Exception):
    """Raised when the diagnosis owner cannot be consulted (unset URL, timeout,
    5xx, connection error). MUST surface as VALIDATION_UNAVAILABLE — never a pass."""


@dataclass(frozen=True)
class DiagnosisFacts:
    """Authoritative facts about a diagnosis, fetched from its owning service."""

    found: bool
    tenant_id: str | None = None
    field_id: str | None = None
    season_id: str | None = None
    review_state: str | None = None
    evidence_level: int | None = None
    insufficient_evidence: bool = False
    valid_until: str | None = None  # ISO-8601; None ⇒ no expiry
    superseded_by: str | None = None  # non-empty ⇒ superseded


class DiagnosisResolver(Protocol):
    def resolve(self, *, tenant_id: str, diagnosis_ref: str) -> DiagnosisFacts:
        """Return authoritative facts, or raise ResolverUnavailable if the owner
        cannot be consulted. A genuinely-absent diagnosis returns found=False."""
        ...


class HttpDiagnosisResolver:
    """Default resolver: consults the diagnosis owner over HTTP with a service token.

    If ``DIAGNOSIS_SERVICE_URL`` is unset, or the request fails/errors/times out, it
    raises ResolverUnavailable so the audit records VALIDATION_UNAVAILABLE rather than
    silently passing. (The owning endpoint may not exist yet — that too is 'unavailable'.)
    """

    def resolve(self, *, tenant_id: str, diagnosis_ref: str) -> DiagnosisFacts:
        base = os.getenv("DIAGNOSIS_SERVICE_URL", "").rstrip("/")
        token = os.getenv("SAHOOL_AGENT_TOKEN", "")
        if not base or not token:
            raise ResolverUnavailable("diagnosis owner not configured")
        try:
            import httpx  # lazy: keep the module import-safe in the minimal unit env
        except Exception as exc:  # pragma: no cover - env-dependent
            raise ResolverUnavailable("httpx unavailable") from exc
        url = f"{base}/internal/diagnoses/{diagnosis_ref}"
        headers = {
            "X-Agent-Token": token,
            "X-Service-Name": "sahool-platform",
            "X-Tenant-Id": tenant_id,
        }
        try:
            resp = httpx.get(url, headers=headers, timeout=3.0)
        except Exception as exc:
            raise ResolverUnavailable(f"diagnosis owner request failed: {exc}") from exc
        if resp.status_code == 404:
            return DiagnosisFacts(found=False)
        if resp.status_code >= 500 or resp.status_code in (401, 403):
            raise ResolverUnavailable(f"diagnosis owner status {resp.status_code}")
        data = resp.json()
        return DiagnosisFacts(
            found=True,
            tenant_id=data.get("tenant_id"),
            field_id=data.get("field_id"),
            season_id=data.get("season_id"),
            review_state=data.get("review_state"),
            evidence_level=data.get("evidence_level"),
            insufficient_evidence=bool(data.get("insufficient_evidence", False)),
            valid_until=data.get("valid_until"),
            superseded_by=data.get("superseded_by"),
        )


# ─────────────────────────────── result ──────────────────────────────────────
@dataclass(frozen=True)
class ChemicalLineageAudit:
    mode: str
    boundary: str
    compliant: bool
    validated: bool  # True only when the diagnosis was actually consulted
    violations: tuple[str, ...]
    details: tuple[dict[str, object], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "boundary": self.boundary,
            "compliant": self.compliant,
            "validated": self.validated,
            "violations": list(self.violations),
            "details": list(self.details),
        }


# ─────────────────────────────── config helpers ──────────────────────────────
def configured_mode() -> ChemicalLineageMode:
    raw = os.getenv("FII_CHEMICAL_LINEAGE_MODE", "audit").strip().lower()
    try:
        return ChemicalLineageMode(raw)
    except ValueError:
        return ChemicalLineageMode.AUDIT


def _evidence_level_min() -> int:
    try:
        return int(os.getenv("FII_CHEMICAL_EVIDENCE_LEVEL_MIN", "2"))
    except ValueError:
        return 2


def _allowed_review_states() -> set[str]:
    raw = os.getenv("FII_CHEMICAL_ALLOWED_REVIEW_STATES", "supported")
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


_HEX64 = frozenset("0123456789abcdef")


def _has_digest(evidence_ref: str) -> bool:
    """A stable evidence reference must carry a sha256 digest. Accepts ``sha256:<64hex>``,
    ``<ref>@<64hex>``, or any 64-hex-char token embedded in the reference."""
    s = evidence_ref.strip().lower()
    for token in s.replace(":", " ").replace("@", " ").replace("/", " ").split():
        if len(token) == 64 and all(c in _HEX64 for c in token):
            return True
    return False


def _is_expired(valid_until: str | None, now: datetime) -> bool:
    if not valid_until:
        return False
    try:
        dt = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
    except ValueError:
        # Unparseable expiry is treated as expired (fail-closed at the field level).
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt < now


# ─────────────────────────────── the audit ───────────────────────────────────
def audit_chemical_lineage(
    *,
    field_id: str | None,
    season_id: str | None,
    diagnosis_ref: str | None,
    evidence_ref: str | None,
    tenant_id: str | None = None,
    boundary: ChemicalBoundary | str = ChemicalBoundary.DRAFT,
    human_approval: bool = False,
    resolver: DiagnosisResolver | None = None,
    now: datetime | None = None,
) -> ChemicalLineageAudit:
    """Audit a CHEMICAL_INTERVENTION at ``boundary``. Never raises; returns a result
    carrying stable ViolationCode strings. Callers decide what to do with it (log in
    audit mode; a caller may reject only when ``mode == enforce``)."""
    mode = configured_mode()
    try:
        b = ChemicalBoundary(boundary)
    except ValueError:
        b = ChemicalBoundary.DRAFT
    if mode is ChemicalLineageMode.OFF:
        return ChemicalLineageAudit(mode.value, b.value, True, False, ())

    now = now or datetime.now(UTC)
    violations: list[str] = []
    details: list[dict[str, object]] = []

    def add(code: ViolationCode, **info: object) -> None:
        violations.append(code.value)
        if info:
            details.append({"code": code.value, **info})

    # 1) presence + evidence digest
    if not (field_id and str(field_id).strip()):
        add(ViolationCode.MISSING_FIELD_ID)
    if not (season_id and str(season_id).strip()):
        add(ViolationCode.MISSING_SEASON_ID)
    if not (diagnosis_ref and str(diagnosis_ref).strip()):
        add(ViolationCode.MISSING_DIAGNOSIS_REF)
    if not (evidence_ref and str(evidence_ref).strip()):
        add(ViolationCode.MISSING_EVIDENCE_REF)
    elif not _has_digest(str(evidence_ref)):
        add(ViolationCode.EVIDENCE_DIGEST_MISSING)

    strength = _ORDER.get(b, 0)

    # 2) server-side diagnosis validation (SUBMIT and stronger)
    validated = False
    if strength >= _REQUIRES_VALIDATION_FROM and diagnosis_ref and str(diagnosis_ref).strip():
        r = resolver or HttpDiagnosisResolver()
        facts: DiagnosisFacts | None
        try:
            facts = r.resolve(tenant_id=str(tenant_id or ""), diagnosis_ref=str(diagnosis_ref))
        except ResolverUnavailable as exc:
            # NEVER a silent pass: record and (in audit) allow; (in enforce) the caller blocks.
            add(ViolationCode.VALIDATION_UNAVAILABLE, reason=str(exc))
            logger.warning(
                "chemical lineage validation unavailable diagnosis_ref=%s reason=%s",
                diagnosis_ref,
                exc,
            )
            facts = None
        if facts is not None:
            if not facts.found:
                add(ViolationCode.DIAGNOSIS_NOT_FOUND)
            else:
                validated = True
                if facts.superseded_by:
                    add(ViolationCode.DIAGNOSIS_SUPERSEDED, superseded_by=facts.superseded_by)
                if _is_expired(facts.valid_until, now):
                    add(ViolationCode.DIAGNOSIS_EXPIRED, valid_until=facts.valid_until)
                if facts.insufficient_evidence:
                    add(ViolationCode.DIAGNOSIS_INSUFFICIENT_EVIDENCE)
                if (facts.review_state or "").strip().lower() not in _allowed_review_states():
                    add(ViolationCode.REVIEW_STATE_NOT_ALLOWED, review_state=facts.review_state)
                if (
                    facts.evidence_level is not None
                    and facts.evidence_level < _evidence_level_min()
                ):
                    add(ViolationCode.EVIDENCE_INSUFFICIENT, evidence_level=facts.evidence_level)
                # server-side identity agreement (never trust the request body alone)
                if tenant_id and facts.tenant_id and str(facts.tenant_id) != str(tenant_id):
                    add(ViolationCode.TENANT_MISMATCH)
                if field_id and facts.field_id and str(facts.field_id) != str(field_id):
                    add(ViolationCode.FIELD_MISMATCH)
                if season_id and facts.season_id and str(facts.season_id) != str(season_id):
                    add(ViolationCode.SEASON_MISMATCH)

    # 3) human approval (APPROVE and stronger)
    if strength >= _REQUIRES_APPROVAL_FROM and not human_approval:
        add(ViolationCode.MISSING_HUMAN_APPROVAL)

    return ChemicalLineageAudit(
        mode=mode.value,
        boundary=b.value,
        compliant=not violations,
        validated=validated,
        violations=tuple(violations),
        details=tuple(details),
    )
