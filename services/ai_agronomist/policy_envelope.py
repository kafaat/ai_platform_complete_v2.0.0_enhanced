"""Tenant AI Policy Envelope — consumer enforcement (v52).

``ai_agronomist`` is a **policy consumer**, not the policy authority. The platform
authors a trusted policy envelope (``core/ai_policy_envelope.py``) and stamps it into
the AI context pack under ``ai_policy_envelope``. This service enforces that envelope
and **never opens the database for tenant policy**.

Fail-closed contract:
  • A request whose pack carries no valid envelope is *refused* — a structured decision,
    never a raw exception (``enforce_request``).
  • ``local_only`` blocks any external-LLM/provider call
    (decision reason ``local_only_blocks_external_provider``).
  • ``redacted_external`` permits an external call *only after redaction*.
  • ``full_external`` is permitted only when the envelope explicitly says
    ``external_llm_allowed=True``.
  • Tool execution must additionally pass the envelope's ``allowed_tools`` allow-list —
    this *composes* with (does not replace) capability/risk/approval governance.

Pure stdlib; unit-testable with plain dicts (no DB, no providers, no network).
"""

from __future__ import annotations

from typing import Any

ENVELOPE_KEY = "ai_policy_envelope"
ENVELOPE_VERSION = "v52"

POLICY_MODE_LOCAL_ONLY = "local_only"
POLICY_MODE_REDACTED_EXTERNAL = "redacted_external"
POLICY_MODE_FULL_EXTERNAL = "full_external"
POLICY_MODES: frozenset[str] = frozenset(
    (POLICY_MODE_LOCAL_ONLY, POLICY_MODE_REDACTED_EXTERNAL, POLICY_MODE_FULL_EXTERNAL)
)

# Decision verbs surfaced to the harness/transparency layer.
DECISION_ALLOWED = "allowed"
DECISION_BLOCKED = "blocked"

# Reason codes (stable strings — asserted by tests and shown in audit/transparency).
REASON_ENVELOPE_MISSING = "policy_envelope_missing"
REASON_ENVELOPE_MALFORMED = "policy_envelope_malformed"
REASON_INVALID_POLICY_MODE = "policy_envelope_invalid_mode"
REASON_LOCAL_PROVIDER = "local_provider_no_external_gate"
REASON_LOCAL_ONLY_BLOCKS_EXTERNAL = "local_only_blocks_external_provider"
REASON_EXTERNAL_LLM_NOT_ALLOWED = "external_llm_not_allowed"
REASON_REDACTED_REQUIRES_REDACTION = "redacted_external_requires_redaction"
REASON_FULL_EXTERNAL_ALLOWED = "full_external_allowed"
REASON_TOOL_NOT_ALLOWED = "tool_not_in_allowed_tools"

_REQUIRED_KEYS = ("policy_mode", "allowed_tools", "external_llm_allowed", "version")


def extract_envelope(pack: Any) -> dict[str, Any] | None:
    """Return the envelope embedded in an AI context pack, or ``None`` if absent."""
    if not isinstance(pack, dict):
        return None
    env = pack.get(ENVELOPE_KEY)
    return env if isinstance(env, dict) else None


def validate_envelope(envelope: Any) -> tuple[bool, str | None]:
    """(ok, reason). Missing ⇒ (False, envelope_missing); malformed/illegal ⇒ (False, reason)."""
    if not isinstance(envelope, dict) or not envelope:
        return False, REASON_ENVELOPE_MISSING
    for key in _REQUIRED_KEYS:
        if key not in envelope:
            return False, REASON_ENVELOPE_MALFORMED
    if envelope.get("policy_mode") not in POLICY_MODES:
        return False, REASON_INVALID_POLICY_MODE
    if not isinstance(envelope.get("external_llm_allowed"), bool):
        return False, REASON_ENVELOPE_MALFORMED
    if not isinstance(envelope.get("allowed_tools"), list):
        return False, REASON_ENVELOPE_MALFORMED
    if not str(envelope.get("version") or "").strip():
        return False, REASON_ENVELOPE_MALFORMED
    return True, None


def _decision(
    decision: str, reason: str, envelope: dict[str, Any] | None, **extra: Any
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "decision": decision,
        "reason": reason,
        "policy_mode": (envelope or {}).get("policy_mode"),
        "version": (envelope or {}).get("version") or ENVELOPE_VERSION,
    }
    out.update(extra)
    return out


def refusal(reason: str, envelope: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    """Structured fail-closed refusal (never raised — returned as data)."""
    return _decision(DECISION_BLOCKED, reason, envelope, refused=True, **extra)


def enforce_request(pack: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Gate an incoming AI request by its pack envelope.

    Returns ``(envelope, decision)``:
      • valid envelope ⇒ ``(envelope, None)`` — request may proceed (subject to further,
        provider/tool-level gates below);
      • missing/invalid ⇒ ``(None, refusal(...))`` — the request is refused fail-closed.
    """
    envelope = extract_envelope(pack)
    ok, reason = validate_envelope(envelope)
    if not ok:
        return None, refusal(reason or REASON_ENVELOPE_MISSING, envelope)
    return envelope, None


def gate_generation(envelope: dict[str, Any] | None, *, external: bool) -> dict[str, Any]:
    """Decide whether a generation call may proceed and how.

    ``external`` is True when the resolved provider ships context outside the tenant
    boundary. Local providers are never blocked by data-sharing mode (the data does not
    leave); external providers are gated by ``policy_mode`` + ``external_llm_allowed``.
    ``redacted_external`` ⇒ allowed with ``requires_redaction=True``.
    """
    if not external:
        return _decision(
            DECISION_ALLOWED, REASON_LOCAL_PROVIDER, envelope, requires_redaction=False
        )

    ok, reason = validate_envelope(envelope)
    if not ok:
        # Fail-closed: an external provider requires a valid, platform-authored envelope.
        return refusal(reason or REASON_ENVELOPE_MISSING, envelope, requires_redaction=False)

    assert envelope is not None  # validated above
    mode = envelope.get("policy_mode")
    if mode == POLICY_MODE_LOCAL_ONLY:
        return refusal(REASON_LOCAL_ONLY_BLOCKS_EXTERNAL, envelope, requires_redaction=False)
    if not envelope.get("external_llm_allowed"):
        return refusal(REASON_EXTERNAL_LLM_NOT_ALLOWED, envelope, requires_redaction=False)
    if mode == POLICY_MODE_REDACTED_EXTERNAL:
        return _decision(
            DECISION_ALLOWED, REASON_REDACTED_REQUIRES_REDACTION, envelope, requires_redaction=True
        )
    if mode == POLICY_MODE_FULL_EXTERNAL:
        return _decision(
            DECISION_ALLOWED, REASON_FULL_EXTERNAL_ALLOWED, envelope, requires_redaction=False
        )
    # Unreachable given validate_envelope, but stay fail-closed on any surprise.
    return refusal(REASON_INVALID_POLICY_MODE, envelope, requires_redaction=False)


def allowed_tools_set(envelope: dict[str, Any] | None) -> set[str] | None:
    """The envelope's tool allow-list as a set (or ``None`` if there is no valid envelope).

    ``None`` means *no envelope gate is available* — callers treat that fail-closed at the
    request level (``enforce_request``); this helper only exposes the set when present.
    """
    if not isinstance(envelope, dict):
        return None
    tools = envelope.get("allowed_tools")
    if not isinstance(tools, list):
        return None
    return {str(t) for t in tools}


def tool_allowed(envelope: dict[str, Any] | None, tool_name: str) -> bool:
    """Is ``tool_name`` permitted by the envelope's allow-list? Absent list ⇒ False (fail-closed)."""
    allowed = allowed_tools_set(envelope)
    if allowed is None:
        return False
    return str(tool_name) in allowed
