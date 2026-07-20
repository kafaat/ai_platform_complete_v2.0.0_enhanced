"""Central TLS context policy for E2E/live scripts — insecure only against loopback.

Deep-audit finding: several ``scripts/e2e/*`` and ``scripts/smoke_e2e.py`` build an
``ssl`` context with ``check_hostname=False`` + ``CERT_NONE`` behind an ``INSECURE_TLS``
opt-in (default off, so verification is on by default — good). The residual gap is that
the opt-in disables verification for *any* target host, so a script accidentally pointed
at a real remote host with ``INSECURE_TLS=1`` would silently skip verification.

This helper narrows the blast radius: ``INSECURE_TLS`` is honored only when the target
host is loopback (localhost / 127.0.0.1 / ::1), which is where self-signed dev certs live.
Disabling verification against a non-loopback host additionally requires the explicit
``INSECURE_TLS_ALLOW_REMOTE=1`` override — otherwise the context verifies normally.

Pure logic (only ``ssl``/``os``/``urllib.parse`` from stdlib) — unit-testable, importable
by scripts that add the repo root to ``sys.path``.
"""

from __future__ import annotations

import os
import ssl
from urllib.parse import urlparse

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", ""})

_TRUE = frozenset({"1", "true", "yes", "on"})


def _is_loopback(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in _LOOPBACK_HOSTS or h.endswith(".localhost")


def insecure_tls_permitted(base_url: str, *, env: dict[str, str] | None = None) -> bool:
    """True iff verification may be disabled for ``base_url`` given the environment.

    Requires ``INSECURE_TLS`` truthy AND (loopback host OR ``INSECURE_TLS_ALLOW_REMOTE``).
    """
    e = os.environ if env is None else env
    if e.get("INSECURE_TLS", "").strip().lower() not in _TRUE:
        return False
    host = urlparse(base_url).hostname or ""
    if _is_loopback(host):
        return True
    return e.get("INSECURE_TLS_ALLOW_REMOTE", "").strip().lower() in _TRUE


def tls_context(base_url: str, *, env: dict[str, str] | None = None) -> ssl.SSLContext | None:
    """Return the ``ssl`` context an HTTPS client should use for ``base_url``.

    * ``http://`` target -> ``None`` (no TLS context needed).
    * ``https://`` with verification permitted (loopback + opt-in) -> unverified context.
    * ``https://`` otherwise -> a normal verifying default context (fail-safe).
    """
    if not base_url.lower().startswith("https://"):
        return None
    if insecure_tls_permitted(base_url, env=env):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()
