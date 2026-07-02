"""Tenant AI Policy Envelope (v52) — the platform is the policy authority.

The platform reads the durable tenant AI policy (table ``tenant_ai_policies`` —
migration ``v124_tenant_ai_policies.sql``) and stamps a **trusted policy envelope**
into the AI context pack. The ``ai_agronomist`` consumer never opens the database
for tenant policy; it enforces the envelope carried inside the pack.

Envelope shape (a plain, JSON-serialisable dict — a data contract, not a class)::

    {
      "policy_mode":          "local_only" | "redacted_external" | "full_external",
      "allowed_tools":        [...tool names the tenant may invoke...],
      "allowed_data_classes": [...data classes that may leave the tenant boundary...],
      "redaction_profile":    "default",
      "max_context_bytes":    int,   # upper bound on context shipped to a provider
      "external_llm_allowed": bool,  # may an *external* LLM be called at all?
      "tenant_id":            "...",
      "version":              "v52",
    }

Fail-closed contract: when no policy row exists (or a field is missing/illegal) the
builder returns the **most restrictive** envelope — ``local_only``,
``external_llm_allowed=False``, read-only tools. It never fabricates a permissive
default. This is a pure builder: it takes an already-fetched policy row (or ``None``),
so it is unit-testable without a database. ``load_tenant_ai_policy_row`` is the thin,
RLS-scoped reader used by the context-pack router.
"""

from __future__ import annotations

from typing import Any

ENVELOPE_VERSION = "v52"

POLICY_MODE_LOCAL_ONLY = "local_only"
POLICY_MODE_REDACTED_EXTERNAL = "redacted_external"
POLICY_MODE_FULL_EXTERNAL = "full_external"
POLICY_MODES: tuple[str, ...] = (
    POLICY_MODE_LOCAL_ONLY,
    POLICY_MODE_REDACTED_EXTERNAL,
    POLICY_MODE_FULL_EXTERNAL,
)

DEFAULT_REDACTION_PROFILE = "default"
# Whole-pack budget cap (mirror of ``field_ai_context._CONTEXT_MAX_BYTES``); the
# redacted path is capped tighter (mirror of ``ai_generation.redact`` 6000-char cap).
DEFAULT_MAX_CONTEXT_BYTES = 36_000
REDACTED_MAX_CONTEXT_BYTES = 6_000

# ``allowed_tools`` composes with — does not replace — the existing capability/risk/
# approval governance (``shared/ai/tool_registry`` + ``ai_agronomist.tool_governance``).
# The envelope's default allow-list is the read-only (non-mutating) tool set: mutating
# tools always additionally require an explicit capability grant + human approval, so
# they are intentionally omitted from the fail-closed default. Derived from the single
# source of truth (the registry) so the two never drift; a hardcoded mirror is used only
# if the shared package is unavailable at import time (still fail-closed & functional).
try:  # pragma: no cover - import shape depends on runtime sys.path
    from shared.ai.tool_registry import TOOLS as _TOOLS

    _READ_ONLY_TOOLS: tuple[str, ...] = tuple(t.name for t in _TOOLS if not t.mutating)
except Exception:  # noqa: BLE001 - never let policy construction fail on an import
    _READ_ONLY_TOOLS = (
        "get_field_state",
        "get_truecolor_scene",
        "get_index_timeline",
        "get_weather_history",
        "get_operation_windows",
        "get_alerts",
        "get_drawings_and_zones",
        "open_map_layer",
        "detect_field_boundaries",
        "generate_productivity_zones",
        "plan_soil_sampling",
        "generate_vra_prescription",
    )

# Data classes that may leave the tenant boundary at each mode (increasingly permissive).
_DATA_CLASSES_BY_MODE: dict[str, tuple[str, ...]] = {
    POLICY_MODE_LOCAL_ONLY: ("field_local",),
    POLICY_MODE_REDACTED_EXTERNAL: ("field_local", "redacted_external"),
    POLICY_MODE_FULL_EXTERNAL: ("field_local", "redacted_external", "full_external"),
}


def normalize_policy_mode(raw: Any) -> str:
    """Coerce any stored/legacy sharing level to a legal mode; unknown ⇒ ``local_only``."""
    mode = str(raw or "").strip().lower()
    return mode if mode in POLICY_MODES else POLICY_MODE_LOCAL_ONLY


def most_restrictive_envelope(tenant_id: Any) -> dict[str, Any]:
    """The fail-closed default: local-only, no external LLM, read-only tools."""
    return {
        "policy_mode": POLICY_MODE_LOCAL_ONLY,
        "allowed_tools": list(_READ_ONLY_TOOLS),
        "allowed_data_classes": list(_DATA_CLASSES_BY_MODE[POLICY_MODE_LOCAL_ONLY]),
        "redaction_profile": DEFAULT_REDACTION_PROFILE,
        "max_context_bytes": DEFAULT_MAX_CONTEXT_BYTES,
        "external_llm_allowed": False,
        "tenant_id": str(tenant_id),
        "version": ENVELOPE_VERSION,
    }


def build_ai_policy_envelope(
    tenant_id: Any, policy_row: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build the trusted envelope for ``tenant_id`` from a (already fetched) policy row.

    ``policy_row`` is a dict shaped like a ``tenant_ai_policies`` record (or ``None``
    when the tenant has no row). Absent/illegal input ⇒ most-restrictive default. A
    permissive envelope is only ever produced from an explicit, legal policy row.
    """
    if not isinstance(policy_row, dict) or not policy_row:
        return most_restrictive_envelope(tenant_id)

    mode = normalize_policy_mode(
        policy_row.get("external_data_sharing_level")
        if policy_row.get("external_data_sharing_level") is not None
        else policy_row.get("data_sharing_level")
    )
    # Fail-closed on the generation flag: a row that does not explicitly say True is False.
    generation_allowed = policy_row.get("ai_generation_allowed") is True
    external_llm_allowed = generation_allowed and mode in (
        POLICY_MODE_REDACTED_EXTERNAL,
        POLICY_MODE_FULL_EXTERNAL,
    )
    redaction_profile = (
        str(policy_row.get("redaction_profile") or DEFAULT_REDACTION_PROFILE).strip()
        or DEFAULT_REDACTION_PROFILE
    )
    max_bytes = (
        REDACTED_MAX_CONTEXT_BYTES
        if mode == POLICY_MODE_REDACTED_EXTERNAL
        else DEFAULT_MAX_CONTEXT_BYTES
    )
    return {
        "policy_mode": mode,
        "allowed_tools": list(_READ_ONLY_TOOLS),
        "allowed_data_classes": list(_DATA_CLASSES_BY_MODE[mode]),
        "redaction_profile": redaction_profile,
        "max_context_bytes": max_bytes,
        "external_llm_allowed": external_llm_allowed,
        "tenant_id": str(tenant_id),
        "version": ENVELOPE_VERSION,
    }


# Columns selected from ``tenant_ai_policies`` (migration v124). Selected explicitly so a
# future schema change surfaces here rather than silently widening the envelope.
_POLICY_SELECT_SQL = (
    "SELECT tenant_id, ai_generation_allowed, allowed_providers, allowed_models, "
    "external_data_sharing_level, redaction_profile "
    "FROM tenant_ai_policies WHERE tenant_id = $1::uuid"
)


async def load_tenant_ai_policy_row(conn: Any, tenant_id: Any) -> dict[str, Any] | None:
    """Read the tenant's AI policy row over an RLS-scoped connection (or ``None``).

    Any read failure ⇒ ``None`` (⇒ builder falls back to the most restrictive envelope):
    a policy lookup problem must never widen access nor break the context pack.
    """
    try:
        row = await conn.fetchrow(_POLICY_SELECT_SQL, str(tenant_id))
    except Exception:  # noqa: BLE001 - fail closed: unreadable policy ⇒ restrictive default
        return None
    return dict(row) if row is not None else None
