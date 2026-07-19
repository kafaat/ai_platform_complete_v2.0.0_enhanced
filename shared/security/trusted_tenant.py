"""Gateway-trusted tenant identity (SEC-3).

The nginx gateway verifies the JWT, clears any client-supplied ``X-Tenant-Id``,
then injects the AUTHENTICATED ``X-Tenant-Id`` from the verify response (see
``nginx/nginx.v9.conf`` R6 trust model). Inside internal services that header is
therefore the ONLY tenant source of truth. A ``tenant_id`` carried in the request
BODY is untrusted (spoofable) and may only ECHO the header — never override it.

This module is stdlib-only (no FastAPI) so the pure decision function is unit-
testable in the no-fastapi CI tier. The thin FastAPI ``Depends`` wrappers live in
``shared.security.gateway_deps`` (imported only by services that ship FastAPI).
"""

from __future__ import annotations

import hashlib
import hmac

# Stable error codes surfaced as the HTTP 403 ``detail`` by the FastAPI wrappers.
ERROR_MISSING_TENANT = "missing_tenant"
ERROR_TENANT_MISMATCH = "tenant_mismatch"

# SEASON-RECORD-ENTRY-01 §4-① — edge-attestation (HMAC) error codes.
ERROR_EDGE_UNATTESTED = "edge_unattested"  # missing key/attestation, or bad signature -> 401
ERROR_EDGE_STALE = "edge_attestation_stale"  # timestamp outside the replay window -> 401
ERROR_REVIEWER_ROLE_REQUIRED = "reviewer_role_required"  # attested but not a season-reviewer -> 403

EDGE_ATTESTATION_MAX_AGE_S = 120  # anti-replay window (nginx clock ~= service clock)
SEASON_REVIEWER_ROLE = "season-reviewer"


class TrustedTenantError(Exception):
    """Raised (fail-closed) when a gateway-trusted tenant cannot be established.

    ``code`` is a stable machine token (``missing_tenant`` / ``tenant_mismatch``)
    that the FastAPI wrapper maps onto the ``403`` response ``detail``.
    """

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def _clean(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_trusted_tenant(x_tenant_id: str | None, body_tenant_id: str | None = None) -> str:
    """Return the gateway-authenticated tenant, fail-closed.

    - Missing/blank ``X-Tenant-Id``           -> ``TrustedTenantError(missing_tenant)``.
    - body tenant present AND != header       -> ``TrustedTenantError(tenant_mismatch)``.
    - body tenant omitted OR equal to header  -> returns the header value.

    The body value is never trusted as an override; it may only echo the header.
    """
    header = _clean(x_tenant_id)
    if header is None:
        raise TrustedTenantError(ERROR_MISSING_TENANT, "X-Tenant-Id header is required")
    body = _clean(body_tenant_id)
    if body is not None and body != header:
        raise TrustedTenantError(ERROR_TENANT_MISMATCH, "tenant_mismatch")
    return header


def service_token_ok(provided: str | None, expected: str | None) -> bool:
    """Constant-time internal service-token check, fail-closed when unset.

    Returns ``False`` when the expected secret is empty/unset so a mis-provisioned
    service never silently accepts requests (mirrors the platform idiom in
    ``services/sahool-platform/api/main.py`` ``_require_service_token``).
    """
    expected_s = expected or ""
    if not expected_s:
        return False
    return hmac.compare_digest(str(provided or ""), str(expected_s))


# ── SEASON-RECORD-ENTRY-01 §4-① — edge attestation (HMAC) ──────────────────────
# The nginx gateway strips any client X-User-Id/X-Roles/X-Edge-Attestation, then
# re-injects the verified identity AND signs it: X-Edge-Attestation = HMAC(secret,
# user_id\nroles\ntimestamp). A container that bypasses nginx and POSTs a forged
# X-User-Id has no valid signature (shared key nginx<->service only) -> 401. This
# does NOT rely on the service port staying nginx-only (network config drift-proof).


def _edge_message(user_id: str, roles: str, timestamp: str) -> bytes:
    return f"{user_id}\n{roles}\n{timestamp}".encode()


def compute_edge_attestation(user_id: str, roles: str, timestamp: str, secret: str) -> str:
    """The signature nginx computes; the service recomputes and compares (pure)."""
    return hmac.new(
        secret.encode(), _edge_message(user_id, roles, timestamp), hashlib.sha256
    ).hexdigest()


def verify_edge_attestation(
    *,
    user_id: str | None,
    roles: str | None,
    timestamp: str | None,
    attestation: str | None,
    secret: str | None,
    now_epoch: float,
    max_age_s: int = EDGE_ATTESTATION_MAX_AGE_S,
) -> str:
    """Verify the edge HMAC (fail-closed). Returns the attested user_id, or raises.

    - Unset secret / missing user_id|timestamp|attestation -> ``edge_unattested`` (401).
    - Timestamp outside ``max_age_s`` (either direction) -> ``edge_attestation_stale`` (401).
    - Signature mismatch (constant-time) -> ``edge_unattested`` (401).
    """
    uid = _clean(user_id)
    ts = _clean(timestamp)
    att = _clean(attestation)
    key = secret or ""
    if not key or uid is None or ts is None or att is None:
        raise TrustedTenantError(ERROR_EDGE_UNATTESTED, "edge attestation required")
    try:
        ts_epoch = float(ts)
    except (TypeError, ValueError):
        raise TrustedTenantError(ERROR_EDGE_STALE, "edge timestamp malformed") from None
    if abs(now_epoch - ts_epoch) > max_age_s:
        raise TrustedTenantError(ERROR_EDGE_STALE, "edge attestation outside replay window")
    expected = compute_edge_attestation(uid, _clean(roles) or "", ts, key)
    if not hmac.compare_digest(expected, att):
        raise TrustedTenantError(ERROR_EDGE_UNATTESTED, "edge attestation signature mismatch")
    return uid


def has_reviewer_role(roles: str | None, required: str = SEASON_REVIEWER_ROLE) -> bool:
    """True if ``required`` is among the comma-separated attested roles."""
    parts = {r.strip() for r in (roles or "").split(",") if r.strip()}
    return required in parts
