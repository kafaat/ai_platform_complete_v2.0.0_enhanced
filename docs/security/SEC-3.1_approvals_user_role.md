# SEC-3.1 — User/role authorization for AI approvals (IMPLEMENTED)

**Status:** implemented — the auth emission, nginx injection, and service
requirement (the 3 atomic steps in §3) all landed together, so the human
approval flow is never left fail-closed on a header the gateway isn't yet
injecting. The original blocker (auth surfaced the user only in the JSON body,
which `auth_request` discards) is resolved by emitting `X-User-Id`/`X-User-Role`
as response headers from the already-JWT-verified payload.

**As-shipped deviations from the proposal below (both simplifications, no weaker):**
- The fail-closed user check is inlined in `require_authenticated_user`
  (`shared/security/gateway_deps.py`) rather than adding a separate
  `resolve_authenticated_user` to `trusted_tenant.py` — one place, same 403.
- The **approver of record** is now bound to the authenticated `X-User-Id`, not
  the JSON body's `approver` field: `approve`/`deny` pass `approver=user_id`, so a
  caller cannot spoof *who* approved by editing the payload (the core intent of
  "require user/role, not just a JSON body").

---

## 1. Goal (the follow-up to SEC-3)

SEC-3 made `/v1/approvals/approve|deny|resume` on `ai_agronomist` require the
gateway-authenticated `X-Tenant-Id` (closing the spoofable-body-tenant gap).

Approvals are **human governance decisions**, so they should *additionally*
require an authenticated **user identity** (user id / role), not just a tenant.
That requires the gateway to inject an authenticated `X-User-Id` (and optionally
`X-User-Role`) for the AI path, exactly the way it already injects `X-Tenant-Id`.

---

## 2. Why this is blocked today (the deciding fact)

nginx `auth_request` consumes **response headers** from the verify subrequest
(`$upstream_http_x_<header>`), **not** the JSON body.

- `GET /v1/auth/verify` (`services/auth/routers/email_verify.py:96-103`) returns
  `user_id` / `role` / `tenant_id` **in the JSON body** — which `auth_request`
  discards.
- The **only** response header the auth service emits is `X-Tenant-ID`, set by
  `tenant_header_middleware` (`services/auth/main.py:340-357`) from the
  JWT-verified payload. The JWT payload already carries `sub` (user id) and
  `role` (`services/auth/main.py:519-524`).
- There is **no** `X-User-Id` / `X-User-Role` / `X-Roles` response header today,
  so nginx `auth_request_set $uid $upstream_http_x_user_id;` would resolve to an
  empty value.

**Conclusion:** the authenticated user id/role exist and are verified inside the
auth service, but they are not surfaced as a response header. Until step 1 lands,
nginx cannot inject them and the service cannot require them without breaking the
human approval flow.

### Plumbing already pre-staged (only the 3 additive steps below remain)

- `nginx/proxy_params.conf:13` already clears any client-supplied `X-User-Id`
  (`proxy_set_header X-User-Id "";`) — the safe default is in place.
- The internal `/_auth_verify` subrequest already clears inbound `X-User-Id`
  (`nginx/nginx.v9.conf:164`).

So no spoofing window is opened by the change; only emission + capture +
requirement are missing.

---

## 3. The exact 3-step change (auth emits → nginx injects → service requires)

### Step 1 — auth `/verify` emits the authenticated user id/role as response headers

The identity is already JWT-verified in `tenant_header_middleware`
(`services/auth/main.py:340-357`). Emit two more headers from the **same**
verified payload — this is not fabricated; it is the authenticated `sub`/`role`:

```python
# inside tenant_header_middleware, after the issuer check passes:
response.headers["X-Tenant-ID"] = payload.get("tenant_id", "")
response.headers["X-User-Id"] = str(payload.get("sub", ""))
response.headers["X-User-Role"] = payload.get("role", "")
```

Notes:
- Keep this inside the `iss in _ALLOWED_ISS` branch so an unknown-issuer token
  never yields identity headers (mirrors the existing tenant behaviour).
- No CORS `expose_headers` change is needed — these headers are consumed by the
  internal `auth_request` subrequest, not the browser.

### Step 2 — nginx injects the authenticated headers on the AI path

In the `/api/ai-agronomist/` location (`nginx/nginx.v9.conf:308-314`), mirror the
`X-Tenant-Id` pattern:

```nginx
location /api/ai-agronomist/ {
    limit_req zone=agent_limit burst=10 nodelay;
    auth_request /_auth_verify;
    proxy_pass http://ai_agronomist_backend/v1/;
    include    /etc/nginx/proxy_params.conf;                 # clears client X-Tenant-Id / X-User-Id first
    auth_request_set $tenant $upstream_http_x_tenant_id;
    proxy_set_header X-Tenant-Id $tenant;
    auth_request_set $uid   $upstream_http_x_user_id;        # SEC-3.1
    proxy_set_header X-User-Id $uid;                          # SEC-3.1
    auth_request_set $urole $upstream_http_x_user_role;      # SEC-3.1 (optional role authz)
    proxy_set_header X-User-Role $urole;                     # SEC-3.1
    proxy_read_timeout 120s;
}
```

Also clear any client-supplied `X-User-Role` in `nginx/proxy_params.conf`
(the safe default; `X-User-Id` is already cleared there at line 13):

```nginx
proxy_set_header X-User-Role "";
```

### Step 3 — ai_agronomist requires the authenticated user on approvals

Add a fail-closed dependency alongside the existing trusted-tenant guard.

Pure decision helper (stdlib, unit-testable in the no-fastapi tier) in
`shared/security/trusted_tenant.py`:

```python
ERROR_MISSING_USER = "missing_user"

def resolve_authenticated_user(x_user_id: str | None) -> str:
    """Return the gateway-authenticated user id, fail-closed."""
    user = _clean(x_user_id)
    if user is None:
        raise TrustedTenantError(ERROR_MISSING_USER, "X-User-Id header is required")
    return user
```

FastAPI wrapper in `shared/security/gateway_deps.py`:

```python
def require_authenticated_user(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    try:
        return resolve_authenticated_user(x_user_id)
    except TrustedTenantError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from exc
```

Layer it onto each approval endpoint in `services/ai_agronomist/main.py`
(`/v1/approvals/approve` L135, `/v1/approvals/deny` L182, `/v1/approvals/resume` L223),
**in addition to** `require_trusted_tenant` (do not weaken SEC-3):

```python
@app.post("/v1/approvals/approve")
async def approve_tool_request(
    req: ApprovalDecisionRequest,
    _tenant: str = Depends(require_trusted_tenant),
    _user: str = Depends(require_authenticated_user),  # SEC-3.1
) -> dict[str, Any]:
    ...
```

(For role-gated approvals, add a `require_role`-style dependency reading
`X-User-Role` — optional; the user-id requirement is the minimum for SEC-3.1.)

---

## 4. Tests to add/update with the change

- Update the SEC-3 approval happy-path tests in
  `tests_v9/test_gateway_trusted_identity_sec3.py` to also send
  `headers={"X-Tenant-Id": "tenant-1", "X-User-Id": "user-1"}`.
- Add: approval with `X-Tenant-Id` but **missing** `X-User-Id` → `403`,
  `detail == "missing_user"`.
- Add pure-unit tests for `resolve_authenticated_user` (missing/blank → raises,
  present → returns trimmed value) in the no-fastapi tier.
- Keep the existing missing-tenant `403` tests green (SEC-3 not weakened).

---

## 5. Rollout ordering (must be atomic per environment)

Deploy the auth-service header emission (step 1) **before or with** the service
requirement (step 3), because the service becomes fail-closed on `X-User-Id`:

1. auth `/verify` emits `X-User-Id` (step 1) — backward compatible, additive.
2. nginx injects it on the AI path (step 2).
3. ai_agronomist requires it on approvals (step 3).

If step 3 ships before steps 1-2 reach production, **all human approvals return
`403 missing_user`**. Ship them together.

---

## 6. Source references

- `nginx/nginx.v9.conf:308-314` — `/api/ai-agronomist/` (injects only `X-Tenant-Id`).
- `nginx/nginx.v9.conf:154-164` — `/_auth_verify` internal subrequest.
- `nginx/proxy_params.conf:12-14` — clears client `X-Tenant-Id` / `X-User-Id`.
- `services/auth/routers/email_verify.py:96-103` — `GET /v1/auth/verify` (body only).
- `services/auth/main.py:340-357` — `tenant_header_middleware` (emits `X-Tenant-ID`).
- `services/auth/main.py:519-524` — JWT payload carries `sub` + `role`.
- `services/ai_agronomist/main.py:135,182,223` — approval endpoints (`require_trusted_tenant`).
- `shared/security/gateway_deps.py` / `shared/security/trusted_tenant.py` — dep + pure logic.
