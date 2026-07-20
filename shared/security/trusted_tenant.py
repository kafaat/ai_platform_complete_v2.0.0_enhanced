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

# ── SEASON-RECORD-ENTRY-01 slice 3b — who carries season-reviewer authority ──────
# The auth service is single-role RBAC (owner/admin/expert/farmer/viewer); there is no
# grantable multi-``roles`` claim yet (deferred — see gaps SHARED grant model). The auth
# edge-sign endpoint therefore DERIVES season-reviewer authority from that single role.
#
# **Declared derivation (owner slice-3 decision):** only {owner, expert} carry the
# authority — acceptance is an AGRONOMIC act (attesting yields/practices that feed
# scientific calibration), not an operational one.
#   • owner  — data owner; self-review is explicitly sanctioned for this phase (spec §5-2).
#   • expert — literally "المهندس الزراعيّ"; agronomic acceptance is stronger than the owner's.
#   • admin  — DELIBERATELY EXCLUDED: operational (users, settings), not agronomic. Letting a
#     sysadmin with no agronomic background attest yields that enter scientific calibration
#     would conflate operational privilege with agronomic authority. The exclusion is the
#     decision a future reader will ask about — it is intentional, not an oversight.
#   • farmer / viewer — never.
SEASON_REVIEWER_SOURCE_ROLES = frozenset({"owner", "expert"})


def season_reviewer_roles_for(role: str | None) -> str:
    """Derive the comma-separated ``roles`` string the auth edge-sign endpoint signs.

    Returns ``season-reviewer`` (plus the source role) iff the single JWT role is in
    :data:`SEASON_REVIEWER_SOURCE_ROLES`; otherwise just the role — so a downstream
    ``has_reviewer_role`` check yields 403 for admin/farmer/viewer (declared, not silent).
    """
    r = (role or "").strip().lower()
    if r in SEASON_REVIEWER_SOURCE_ROLES:
        return f"{r},{SEASON_REVIEWER_ROLE}"
    return r


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


# ── SEASON-RECORD-ENTRY-01 §4-① — edge attestation (HMAC), DESTINATION-BOUND ────
# The auth service (SEC-3.1 auth_request→verify) strips any client X-Edge-Attestation,
# verifies the JWT, then re-injects the verified identity AND signs it:
#   X-Edge-Attestation = HMAC(secret, user_id\nroles\nMETHOD\nPATH\nBODY_SHA256\ntimestamp).
# A container that bypasses the gateway and POSTs a forged X-User-Id has no valid
# signature (key held by auth<->consuming service only) -> 401. Network-drift-proof.
#
# **Destination-bound (owner slice-3 condition ①):** the signature also covers the HTTP
# method, the canonical path, and the sha-256 of the body — so an attestation minted for
# a benign path (e.g. a GET) CANNOT be replayed on ``.../accept`` (cross-path replay). The
# ±``max_age_s`` window guards time; binding method/path/body guards place & payload.


def edge_body_sha256(body: bytes | None) -> str:
    """Hex sha-256 of the request body (empty body -> sha256 of b'') for the signature."""
    return hashlib.sha256(body or b"").hexdigest()


def _edge_message(
    user_id: str, roles: str, method: str, path: str, body_sha256: str, timestamp: str
) -> bytes:
    return f"{user_id}\n{roles}\n{method}\n{path}\n{body_sha256}\n{timestamp}".encode()


def compute_edge_attestation(
    user_id: str,
    roles: str,
    method: str,
    path: str,
    body_sha256: str,
    timestamp: str,
    secret: str,
) -> str:
    """The signature auth computes; the consuming service recomputes and compares (pure).

    Destination-bound: identity + method + canonical path + body hash + timestamp. The
    signer (auth) and verifier (e.g. scout-ingest) must agree on the SAME canonical
    ``method``/``path`` string (wired in the gateway) — the pure function is agnostic.
    """
    return hmac.new(
        secret.encode(),
        _edge_message(user_id, roles, method, path, body_sha256, timestamp),
        hashlib.sha256,
    ).hexdigest()


def verify_edge_attestation(
    *,
    user_id: str | None,
    roles: str | None,
    method: str | None,
    path: str | None,
    body_sha256: str | None,
    timestamp: str | None,
    attestation: str | None,
    secret: str | None,
    now_epoch: float,
    max_age_s: int = EDGE_ATTESTATION_MAX_AGE_S,
) -> str:
    """Verify the destination-bound edge HMAC (fail-closed). Returns the user_id, or raises.

    - Unset secret / missing user_id|method|path|body_sha256|timestamp|attestation
      -> ``edge_unattested`` (401).
    - Timestamp outside ``max_age_s`` (either direction) -> ``edge_attestation_stale`` (401).
    - Signature mismatch — incl. a valid attestation for a DIFFERENT method/path/body
      (cross-path replay) -> ``edge_unattested`` (401).
    """
    uid = _clean(user_id)
    ts = _clean(timestamp)
    att = _clean(attestation)
    mth = _clean(method)
    pth = _clean(path)
    bsha = _clean(body_sha256)
    key = secret or ""
    if (
        not key
        or uid is None
        or ts is None
        or att is None
        or mth is None
        or pth is None
        or bsha is None
    ):
        raise TrustedTenantError(ERROR_EDGE_UNATTESTED, "edge attestation required")
    try:
        ts_epoch = float(ts)
    except (TypeError, ValueError):
        raise TrustedTenantError(ERROR_EDGE_STALE, "edge timestamp malformed") from None
    if abs(now_epoch - ts_epoch) > max_age_s:
        raise TrustedTenantError(ERROR_EDGE_STALE, "edge attestation outside replay window")
    expected = compute_edge_attestation(uid, _clean(roles) or "", mth, pth, bsha, ts, key)
    if not hmac.compare_digest(expected, att):
        raise TrustedTenantError(ERROR_EDGE_UNATTESTED, "edge attestation signature mismatch")
    return uid


def has_reviewer_role(roles: str | None, required: str = SEASON_REVIEWER_ROLE) -> bool:
    """True if ``required`` is among the comma-separated attested roles."""
    parts = {r.strip() for r in (roles or "").split(",") if r.strip()}
    return required in parts
