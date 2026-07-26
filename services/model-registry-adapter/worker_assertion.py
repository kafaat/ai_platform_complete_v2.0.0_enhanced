"""Worker-bound assertion signer for the model-lifecycle adapter (WORKER-IDENTITY-BINDING).

The adapter image is built from its own directory (its Dockerfile COPYs only the adapter modules —
no ``shared/`` in the build context), so this signer is vendored rather than imported. It MUST stay
byte-compatible with ``shared/security/service_tenant_assertion.py::verify_tenant_assertion`` — the
decision-service verifier the adapter's requests are checked against. That compatibility is pinned
by ``tests/test_worker_assertion_interop.py``, which signs here and verifies with the real shared
module (the test runs from the repo root where ``shared/`` is importable), so any format drift
(VERSION, field order, delimiter) fails CI rather than silently breaking auth at runtime.

Format (mirrors the shared module): VERSION ``v2``; newline-joined payload of
(VERSION, key_id, issued_at, nonce, service, subject, method, path, request_id); HMAC-SHA256 over
that payload; the wire assertion is those nine fields plus the hex signature, colon-joined.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

VERSION = "v2"


def _clean(value: str, name: str) -> str:
    value = str(value or "").strip()
    if not value or any(ch in value for ch in (":", "\n", "\r")):
        raise ValueError(f"invalid {name}")
    return value


def create_worker_assertion(
    key: str,
    service: str,
    subject: str,
    *,
    key_id: str = "current",
    method: str,
    path: str,
    request_id: str,
    nonce: str | None = None,
    issued_at: int | None = None,
) -> str:
    """Return a signed, request-scoped assertion binding ``subject`` (the worker_id) to the call."""
    if len(key) < 32:
        raise ValueError("assertion key must contain at least 32 characters")
    fields = (
        VERSION,
        _clean(key_id, "key_id"),
        str(int(time.time()) if issued_at is None else int(issued_at)),
        _clean(nonce or secrets.token_urlsafe(18), "nonce"),
        _clean(service, "service"),
        _clean(subject, "subject"),
        _clean(method.upper(), "method"),
        _clean(path, "path"),
        _clean(request_id, "request_id"),
    )
    signature = hmac.new(key.encode(), "\n".join(fields).encode(), hashlib.sha256).hexdigest()
    return ":".join((*fields, signature))
