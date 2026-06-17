"""حُرّاس أمنيّة لملفّات compose من التدقيق الخارجيّ (FINDING-003 + المتوسّطة).

• FINDING-003: خدمة guardrails-engine يجب أن تُحقَن SAHOOL_AGENT_TOKEN، وإلّا
  تُرجِع /validate الحوكمة 503 (مغلقة بأمان لكنّها معطّلة).
• MEDIUM (منافذ): التخزين الداخليّ (MinIO) والخدمات الداخليّة (raster) يجب ألّا
  تُكشَف على 0.0.0.0 — حصرها على 127.0.0.1 (loopback). بوّابة nginx (80/443) عامّة عمداً.
"""

from __future__ import annotations

import glob
import os

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

yaml = pytest.importorskip("yaml")

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _docs():
    for f in sorted(glob.glob(os.path.join(ROOT, "docker-compose*.yml"))):
        with open(f, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        if isinstance(doc, dict):
            yield os.path.basename(f), doc


def _env_dict(svc):
    env = svc.get("environment", {}) or {}
    if isinstance(env, list):
        return dict(e.split("=", 1) for e in env if isinstance(e, str) and "=" in e)
    return env


def _guardrails_services():
    out = []
    for fname, doc in _docs():
        for name, svc in (doc.get("services") or {}).items():
            if not isinstance(svc, dict):
                continue
            df = (
                str(svc.get("build", {}).get("dockerfile", ""))
                if isinstance(svc.get("build"), dict)
                else ""
            )
            if "guardrails-engine" in name or "guardrails-engine" in df:
                out.append((fname, name, svc))
    return out


def test_guardrails_services_found():
    assert _guardrails_services(), "لم تُكتشَف خدمة guardrails-engine — التحليل مكسور"


@pytest.mark.parametrize("fname,svc_name,svc", _guardrails_services())
def test_guardrails_has_agent_token(fname, svc_name, svc):
    """FINDING-003: guardrails يجب أن يُحقَن SAHOOL_AGENT_TOKEN (وإلّا 503 على /validate)."""
    env = _env_dict(svc)
    assert "SAHOOL_AGENT_TOKEN" in env, (
        f"{fname}:{svc_name} بلا SAHOOL_AGENT_TOKEN ⇒ /validate الحوكمة تُرجِع 503 (معطّلة)."
    )


# خدمات داخليّة يجب حصر منافذها على loopback (لا تُكشَف على الشبكة).
_INTERNAL_PORT_SERVICES = ("minio", "raster")


def _internal_port_cases():
    out = []
    for fname, doc in _docs():
        for name, svc in (doc.get("services") or {}).items():
            if not isinstance(svc, dict):
                continue
            if not any(k in name for k in _INTERNAL_PORT_SERVICES):
                continue
            for p in svc.get("ports", []) or []:
                out.append((fname, name, str(p)))
    return out


@pytest.mark.parametrize("fname,svc_name,port", _internal_port_cases())
def test_internal_ports_bound_loopback(fname, svc_name, port):
    """MEDIUM: منافذ MinIO/raster الداخليّة محصورة على 127.0.0.1 لا مكشوفة على 0.0.0.0."""
    # شكل النشر المكشوف: "9000:9000" (بلا IP) أو "0.0.0.0:9000:9000". الآمن: "127.0.0.1:..".
    assert port.startswith("127.0.0.1:"), (
        f"{fname}:{svc_name} يكشف المنفذ {port} على 0.0.0.0 — احصره على 127.0.0.1 (داخليّ)."
    )
