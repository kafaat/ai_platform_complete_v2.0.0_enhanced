"""وحدة: سياسة سياق TLS المركزيّة (shared.security.tls_policy) + حارس ساكن على السكربتات.

تدقيق عميق رصد سكربتات E2E تُعطّل تحقّق TLS. الافتراض الآن: تحقّق مُفعَّل؛ التعطيل يُشرَّف
فقط لأهداف loopback مع INSECURE_TLS=1 (وللمضيف البعيد يلزم INSECURE_TLS_ALLOW_REMOTE=1).
الحارس يمنع أيّ سكربت يعطّل TLS دون المرور بالسياسة المركزيّة.

وحدة صرفة — ``pytest -m unit``.
"""

from __future__ import annotations

import re
import ssl
from pathlib import Path

import pytest

from shared.security.tls_policy import insecure_tls_permitted, tls_context

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]


def test_http_target_needs_no_context():
    assert tls_context("http://localhost:8080", env={}) is None
    assert tls_context("http://localhost:8080", env={"INSECURE_TLS": "1"}) is None


def test_https_default_verifies():
    ctx = tls_context("https://localhost", env={})
    assert ctx is not None and ctx.verify_mode == ssl.CERT_REQUIRED


def test_https_loopback_with_optin_is_insecure():
    ctx = tls_context("https://localhost:8443", env={"INSECURE_TLS": "1"})
    assert ctx is not None and ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_https_remote_optin_still_verifies_without_allow_remote():
    # loopback فقط: المضيف البعيد يبقى مُتحقَّقاً رغم INSECURE_TLS.
    ctx = tls_context("https://api.example.com", env={"INSECURE_TLS": "1"})
    assert ctx is not None and ctx.verify_mode == ssl.CERT_REQUIRED


def test_https_remote_requires_explicit_allow_remote():
    ctx = tls_context(
        "https://api.example.com",
        env={"INSECURE_TLS": "1", "INSECURE_TLS_ALLOW_REMOTE": "1"},
    )
    assert ctx is not None and ctx.verify_mode == ssl.CERT_NONE


def test_permitted_matrix():
    assert insecure_tls_permitted("https://127.0.0.1", env={"INSECURE_TLS": "1"}) is True
    assert insecure_tls_permitted("https://localhost", env={}) is False
    assert insecure_tls_permitted("https://remote.io", env={"INSECURE_TLS": "1"}) is False


def test_no_script_disables_tls_outside_central_policy():
    """حارس ساكن: أيّ سكربت يعطّل TLS (CERT_NONE/_create_unverified_context) يجب أن يستورد tls_policy."""
    disablers = re.compile(r"CERT_NONE|_create_unverified_context")
    uses_policy = re.compile(
        r"from shared\.security\.tls_policy import|shared\.security\.tls_policy"
    )
    offenders: list[str] = []
    for py in (_ROOT / "scripts").rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        if disablers.search(text) and not uses_policy.search(text):
            offenders.append(str(py.relative_to(_ROOT)))
    assert not offenders, (
        f"scripts disabling TLS must route through shared.security.tls_policy: {offenders}"
    )
